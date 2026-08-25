"""Sprint 21: separates embedding-backend measurement noise from real
retrieval instability, then makes a pre-committed non-inferiority
decision between qwen3-0.6b@768 (efficiency candidate) and
qwen3-4b@1024 (quality candidate) — the two configs Sprint 20 narrowed
down to. Does NOT add a new model, reranker, or chunking change, and
does NOT touch the production embedding default.

    python -m scripts.benchmark_stability

Reuses scripts/benchmark_embeddings.py's config parsing, corpus
building, and Qdrant/registry isolation rather than duplicating them —
this script is additive infrastructure on top of Sprint 18-20's, not a
rewrite (see docs/sprint-21-plan.md).

Five real, separated measurements:

1. Embedding nondeterminism (app/llm/ollama_client.py's backend is NOT
   bit-deterministic — confirmed in Sprint 20) — how much do repeated
   embeddings of the SAME query actually differ, and does that flow
   through to a different top-k ranking?
2. Retrieval determinism — with the embedding held FROZEN (cached), is
   Qdrant/RRF's own ranking stable across repeated identical queries?
3. Multi-run live quality stability — 10 independent live query passes
   per config against the SAME indexed collection (embedding
   nondeterminism is the only source of run-to-run difference here,
   since indexing happens once).
4. Pre-committed non-inferiority test (paired bootstrap, correct-
   direction CI interpretation, spelled out in
   app/evaluation/non_inferiority.py) between the two configs.
5. Approximate power analysis — if the data still can't decide, how
   much MORE data would actually be needed (not "let's just add more
   and see").

Writes results.json, stability.json, non_inferiority.json,
power_analysis.json, and report.md to
artifacts/embedding-benchmark-sprint21/ — Sprint 18/19/20's artifact
folders are never touched.
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.bootstrap import paired_bootstrap_ci
from app.evaluation.dataset_fingerprint import corpus_fingerprint, golden_set_fingerprint
from app.evaluation.embedding_cache import EmbeddingCache, cache_key
from app.evaluation.non_inferiority import (
    evaluate_non_inferiority,
    power_analysis,
    production_decision,
)
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.citation_location import location_for
from app.llm.embedding_models import parse_config_token
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from scripts.benchmark_embeddings import (
    _measure_real_collection_disk_bytes,
    _percentile,
    _sanitize_label,
    _stop_ollama_model,
    build_corpus,
    collection_name_for,
    load_golden_questions,
    probe_dimension_support,
)
from tests.fixtures.golden_api_reference_en import GOLDEN_API_REFERENCE_EN_TEXT
from tests.fixtures.golden_enterprise_faq_tr import GOLDEN_ENTERPRISE_FAQ_TR_TEXT
from tests.fixtures.golden_markdown_source import GOLDEN_MARKDOWN_TEXT
from tests.fixtures.golden_source import PAGES as PDF_PAGES

GOLDEN_SET_PATH = "tests/fixtures/embedding_benchmark_golden_v2.json"
CONFIG_TOKENS = ["qwen3-0.6b@768", "qwen3-4b@1024"]
SMALL_LABEL = "qwen3-0.6b@768"
LARGE_LABEL = "qwen3-4b@1024"
NOMIC_HISTORICAL_LABEL = "nomic@768"  # historical reference only — not benchmarked this sprint

WORK_DIR = Path("artifacts/embedding-benchmark-sprint21/work")
OUTPUT_DIR = Path("artifacts/embedding-benchmark-sprint21")
CACHE_DIR = OUTPUT_DIR / "cache"

# Sprint 21's own rules — coded before any result was known.
NUM_LIVE_RUNS = 10
NONDETERMINISM_SAMPLE_SIZE = 50
NONDETERMINISM_REPEATS = 10
RETRIEVAL_DETERMINISM_REPEATS = 5
BOOTSTRAP_SEED = 20210101
BOOTSTRAP_ITERATIONS = 10000
NON_INFERIORITY_MARGINS = {
    "cross_recall_at_5": 0.04,
    "cross_mrr": 0.04,
    "mono_recall_at_5": 0.02,
}
PRIMARY_METRIC = "recall_at_5"
PRIMARY_SUBSET = "cross_lingual"
MATERIAL_MARGIN = NON_INFERIORITY_MARGINS["cross_recall_at_5"]


def compute_dataset_and_corpus_fingerprints(golden_questions: list[dict]) -> dict:
    """Sprint 21 rule: every artifact this script writes carries these
    two fingerprints, so an independent rerun (or a rerun months later)
    can prove it used the IDENTICAL evaluation set — not just a file
    with the same name. PDF content is fingerprinted via its real source
    text (PAGES, the actual strings golden_source.py renders into the
    PDF) since the PDF itself is binary.
    """
    dataset_fp = golden_set_fingerprint(golden_questions)
    corpus_fp = corpus_fingerprint({
        "nimbus_handbook.pdf": "\n".join(p for page in PDF_PAGES for p in page),
        "nimbus_cli.md": GOLDEN_MARKDOWN_TEXT,
        "nimbus_api_reference.md": GOLDEN_API_REFERENCE_EN_TEXT,
        "nimbus_kurumsal_sss.md": GOLDEN_ENTERPRISE_FAQ_TR_TEXT,
    })
    return {"dataset_fingerprint": dataset_fp, "corpus_fingerprint": corpus_fp}


def stratified_sample(golden_questions: list[dict], n: int) -> list[dict]:
    """Deterministic stratified sample across the 4 language-pair cells,
    proportional to each cell's real size, excluding not-found questions
    (which have no expected_locations to measure ranking impact
    against). Sorted by id within each cell before slicing — no
    randomness at all, so the same golden set always yields the same
    sample.
    """
    real_questions = [q for q in golden_questions if not q.get("expect_not_found")]
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in real_questions:
        by_cell[(q["query_lang"], q["content_lang"])].append(q)
    for cell in by_cell:
        by_cell[cell] = sorted(by_cell[cell], key=lambda q: q["id"])

    total = len(real_questions)
    sample: list[dict] = []
    for cell, questions in sorted(by_cell.items()):
        count = max(1, round(n * len(questions) / total))
        sample.extend(questions[:count])

    # Proportional rounding can land 1-2 short of n (e.g. 49 instead of
    # 50) — top up deterministically from the largest cell's remaining,
    # unused questions (sorted by id) rather than silently under-
    # shooting the stated minimum.
    if len(sample) < n:
        sampled_ids = {q["id"] for q in sample}
        largest_cell = max(by_cell.values(), key=len)
        for q in largest_cell:
            if len(sample) >= n:
                break
            if q["id"] not in sampled_ids:
                sample.append(q)
                sampled_ids.add(q["id"])

    return sorted(sample, key=lambda q: q["id"])[:n]


async def index_config(config, settings_obj, golden_questions: list[dict]) -> dict:
    """Indexes ONCE per config — the corpus/chunk set never changes
    across this sprint's repeated query passes, so re-indexing per pass
    would waste time and wouldn't isolate the thing being measured
    (query-embedding nondeterminism, not indexing).
    """
    collection_name = collection_name_for(config)
    registry_path = WORK_DIR / f"registry_{_sanitize_label(config.label())}.db"
    docs_dir = WORK_DIR / "corpus"
    if not docs_dir.exists():
        build_corpus(docs_dir)

    _stop_ollama_model(config.ollama_model)
    probe_ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    supported, actual_dimension = await probe_dimension_support(probe_ollama, config)
    await probe_ollama.aclose()
    if not supported:
        raise RuntimeError(
            f"{config.label()} is not supported in this environment "
            f"(requested {config.dimension}, got {actual_dimension}) — Sprint 21 assumes "
            "both configs are supported, as confirmed in Sprint 19/20."
        )

    qdrant_client = QdrantClient(url=settings_obj.qdrant_url)
    if qdrant_client.collection_exists(collection_name):
        qdrant_client.delete_collection(collection_name)
    store = QdrantStore(
        client=qdrant_client, collection_name=collection_name, dense_dimension=config.dimension
    )
    if registry_path.exists():
        registry_path.unlink()
    registry = DocumentRegistry(registry_path)
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()
    fingerprint = build_pipeline_fingerprint(config)

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=config.ollama_model, prefix=config.document_prefix(),
            dimensions=config.output_dimension,
        )

    connector = LocalFilesystemConnector(str(docs_dir))
    index_start = time.perf_counter()
    stats = await ingest_connector(
        connector, store, registry, embed_fn, sparse_encoder, pipeline_fingerprint=fingerprint,
    )
    indexing_seconds = time.perf_counter() - index_start
    await ollama.aclose()

    real_bytes = _measure_real_collection_disk_bytes(collection_name)
    if real_bytes is not None:
        storage_bytes, storage_measurement = real_bytes, "real"
    else:
        info = qdrant_client.get_collection(collection_name)
        storage_bytes = (info.points_count or 0) * (config.dimension * 4 + 2048)
        storage_measurement = "estimate"

    return {
        "collection_name": collection_name,
        "fingerprint_digest": fingerprint.digest(),
        "chunks_indexed": stats.chunks_upserted,
        "indexing_seconds": indexing_seconds,
        "chunks_per_second": (
            stats.chunks_upserted / indexing_seconds if indexing_seconds > 0 else 0.0
        ),
        "storage_bytes": storage_bytes,
        "storage_measurement": storage_measurement,
    }


async def _embed_query(
    ollama: OllamaClient, config, query: str, fingerprint_digest: str,
    cache: EmbeddingCache | None, embedding_mode: str,
) -> list[float]:
    if embedding_mode == "live":
        return await ollama.embed(
            query, model=config.ollama_model, prefix=config.query_prefix(),
            dimensions=config.output_dimension,
        )
    # frozen — cache MUST already be populated under the CURRENT
    # fingerprint; a mismatch raises StaleCacheError rather than
    # silently falling back to a live call (Sprint 21 rule).
    key = cache_key(
        config.ollama_model, config.revision, config.dimension, config.query_prefix(),
        query, fingerprint_digest,
    )
    vector = cache.get(key, expected_fingerprint=fingerprint_digest)
    if vector is None:
        raise KeyError(
            f"No frozen embedding cached for query {query!r} under config {config.label()} — "
            "populate the cache with --embedding-mode live first."
        )
    return vector


async def run_query_pass(
    config, settings_obj, golden_questions: list[dict], collection_name: str,
    fingerprint_digest: str, embedding_mode: str = "live",
    cache: EmbeddingCache | None = None, populate_cache: bool = False,
) -> dict:
    """A query-ONLY pass against an ALREADY-indexed collection — no
    re-indexing. live: fresh embed call per query (real serving
    variability). frozen: reuses a cached vector, zero embedding calls,
    isolating Qdrant/RRF behavior. populate_cache=True (only meaningful
    with embedding_mode="live") writes each live embedding into the
    cache as it's computed, building the frozen cache from real calls.
    """
    qdrant_client = QdrantClient(url=settings_obj.qdrant_url)
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()

    query_embed_ms: list[float] = []
    retrieval_ms: list[float] = []
    per_question: dict[str, dict] = {}
    per_question_ranked_ids: dict[str, list[str]] = {}
    not_found_hits = 0
    not_found_total = 0

    for question in golden_questions:
        query = question["query"]
        is_not_found = question.get("expect_not_found", False)

        embed_start = time.perf_counter()
        dense_vector = await _embed_query(
            ollama, config, query, fingerprint_digest, cache, embedding_mode
        )
        query_embed_ms.append((time.perf_counter() - embed_start) * 1000)
        if populate_cache and cache is not None:
            key = cache_key(
                config.ollama_model, config.revision, config.dimension, config.query_prefix(),
                query, fingerprint_digest,
            )
            cache.put(key, dense_vector, fingerprint=fingerprint_digest)

        # search() re-embeds internally in live mode; to genuinely honor
        # frozen mode (zero embedding calls), we bypass search() and
        # call hybrid_search directly with the already-obtained vector.
        from app.retrieval.hybrid_search import hybrid_search

        retrieval_start = time.perf_counter()
        sparse_vector = sparse_encoder.embed_query(query)
        results = hybrid_search(
            qdrant_client, collection_name, dense_vector, sparse_vector, top_k=20
        )
        results = results[:5]
        retrieval_ms.append((time.perf_counter() - retrieval_start) * 1000)

        ranked_locations: list[Location] = [
            (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
            for r in results
        ]
        per_question_ranked_ids[question["id"]] = [
            f"{loc[0]}:{loc[1]}:{loc[2]}" for loc in ranked_locations
        ]

        if is_not_found:
            not_found_total += 1
            if not results:
                not_found_hits += 1
            continue

        expected_locations: list[Location] = [tuple(loc) for loc in question["expected_locations"]]
        metrics = compute_rank_metrics(ranked_locations, expected_locations)
        per_question[question["id"]] = {
            "recall_at_1": metrics.recall_at_1,
            "recall_at_3": metrics.recall_at_3,
            "recall_at_5": metrics.recall_at_5,
            "mrr": metrics.reciprocal_rank,
            "ndcg_at_5": metrics.ndcg_at_5,
        }

    await ollama.aclose()

    return {
        "per_question": per_question,
        "per_question_ranked_ids": per_question_ranked_ids,
        "query_embed_ms": query_embed_ms,
        "retrieval_ms": retrieval_ms,
        "not_found_hits": not_found_hits,
        "not_found_total": not_found_total,
    }


def aggregate_pass(pass_result: dict, golden_questions: list[dict]) -> dict:
    """Turns one run_query_pass() result into the same
    overall/by_cell/cross_lingual/mono_lingual shape
    scripts/benchmark_embeddings.py's results use, for consistent
    reporting."""
    by_id = {q["id"]: q for q in golden_questions}
    per_cell = defaultdict(list)
    all_metrics = []
    for qid, m in pass_result["per_question"].items():
        from app.evaluation.rank_metrics import RankMetrics

        rm = RankMetrics(
            recall_at_1=m["recall_at_1"], recall_at_3=m["recall_at_3"],
            recall_at_5=m["recall_at_5"], reciprocal_rank=m["mrr"], ndcg_at_5=m["ndcg_at_5"],
        )
        all_metrics.append(rm)
        q = by_id[qid]
        per_cell[(q["query_lang"], q["content_lang"])].append(rm)

    by_cell = {
        f"{ql}_query_{cl}_content": aggregate_rank_metrics(ms) | {"question_count": len(ms)}
        for (ql, cl), ms in sorted(per_cell.items())
    }

    def cell_mean(cells, key):
        values = [by_cell[c][key] for c in cells if c in by_cell]
        return sum(values) / len(values) if values else None

    cross_cells = ["tr_query_en_content", "en_query_tr_content"]
    mono_cells = ["tr_query_tr_content", "en_query_en_content"]
    return {
        "overall": aggregate_rank_metrics(all_metrics),
        "by_cell": by_cell,
        "cross_lingual": {
            "recall_at_1": cell_mean(cross_cells, "recall_at_1"),
            "recall_at_5": cell_mean(cross_cells, "recall_at_5"),
            "mrr": cell_mean(cross_cells, "mrr"),
            "ndcg_at_5": cell_mean(cross_cells, "ndcg_at_5"),
        },
        "mono_lingual": {
            "recall_at_5": cell_mean(mono_cells, "recall_at_5"),
        },
        "not_found_accuracy": (
            pass_result["not_found_hits"] / pass_result["not_found_total"]
            if pass_result["not_found_total"] else None
        ),
        "query_embed_p50_ms": _percentile(pass_result["query_embed_ms"], 50),
        "query_embed_p95_ms": _percentile(pass_result["query_embed_ms"], 95),
        "retrieval_p50_ms": _percentile(pass_result["retrieval_ms"], 50),
        "retrieval_p95_ms": _percentile(pass_result["retrieval_ms"], 95),
    }


def vector_delta_stats(vectors: list[list[float]]) -> dict:
    """Pure math, extracted for direct unit testing: given N repeated
    embeddings of the SAME query, how much do they differ from the
    first one (max/mean absolute per-dimension delta, mean cosine
    similarity)? Identical vectors -> zero delta, cosine similarity 1.0.
    """
    ref = vectors[0]
    ref_norm = sum(x * x for x in ref) ** 0.5
    max_abs_deltas = []
    mean_abs_deltas = []
    cosine_sims = []
    for v in vectors[1:]:
        diffs = [abs(a - b) for a, b in zip(ref, v)]
        max_abs_deltas.append(max(diffs) if diffs else 0.0)
        mean_abs_deltas.append(sum(diffs) / len(diffs) if diffs else 0.0)
        v_norm = sum(x * x for x in v) ** 0.5
        dot = sum(a * b for a, b in zip(ref, v))
        cosine_sims.append(dot / (ref_norm * v_norm) if ref_norm and v_norm else 1.0)
    if not max_abs_deltas:  # single vector, nothing to compare
        return {"max_abs_delta": 0.0, "mean_abs_delta": 0.0, "mean_cosine_similarity": 1.0}
    return {
        "max_abs_delta": max(max_abs_deltas),
        "mean_abs_delta": sum(mean_abs_deltas) / len(mean_abs_deltas),
        "mean_cosine_similarity": sum(cosine_sims) / len(cosine_sims),
    }


def ranking_flip_flags(
    ranked_lists: list[list[Location]], recalls5: list[float], rrs: list[float]
) -> dict:
    """Pure logic, extracted for direct unit testing: given the ranked
    result lists (and their derived recall@5/reciprocal-rank values)
    from N repeats of the SAME query, did the ranking actually CHANGE in
    a way that matters? Bit-level embedding noise with zero ranking
    impact should show every flag as False.
    """
    top1_ids = [r[0] if r else None for r in ranked_lists]
    top3_sets = [frozenset(r[:3]) for r in ranked_lists]
    top5_sets = [frozenset(r[:5]) for r in ranked_lists]
    return {
        "top1_flip": len(set(top1_ids)) > 1,
        "top3_set_change": len(set(top3_sets)) > 1,
        "top5_set_change": len(set(top5_sets)) > 1,
        "mrr_impacting_flip": len(set(rrs)) > 1,
        "recall_at_5_impacting_flip": len(set(recalls5)) > 1,
    }


def is_retrieval_stable(ranked_lists: list[tuple]) -> bool:
    """Pure logic, extracted for direct unit testing: are ALL repeated
    retrievals of the SAME (frozen) query byte-identical? Used by
    measure_retrieval_determinism to isolate Qdrant/RRF-level
    determinism from embedding-model nondeterminism entirely (no
    embedding calls are involved once inputs are frozen).
    """
    return len(set(ranked_lists)) == 1


async def measure_embedding_nondeterminism(
    config, settings_obj, sample_questions: list[dict], collection_name: str,
) -> dict:
    """For each of the sampled queries: embed it NONDETERMINISM_REPEATS
    times (real, live calls — no caching), measure how much the raw
    vectors differ, THEN feed every repeat through the real retrieval
    pipeline and check whether the resulting top-k ranking actually
    changes. Bit-level float noise and rank-level instability are
    reported as two SEPARATE numbers — Sprint 21's core question.
    """
    from app.retrieval.hybrid_search import hybrid_search

    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    qdrant_client = QdrantClient(url=settings_obj.qdrant_url)
    sparse_encoder = SparseEncoder()

    per_query_vector_stats = []
    top1_flips = 0
    top3_set_changes = 0
    top5_set_changes = 0
    mrr_impacting_flips = 0
    recall5_impacting_flips = 0

    for question in sample_questions:
        query = question["query"]
        expected_locations: list[Location] = [tuple(loc) for loc in question["expected_locations"]]
        sparse_vector = sparse_encoder.embed_query(query)

        vectors = []
        for _ in range(NONDETERMINISM_REPEATS):
            v = await ollama.embed(
                query, model=config.ollama_model, prefix=config.query_prefix(),
                dimensions=config.output_dimension,
            )
            vectors.append(v)

        vstats = vector_delta_stats(vectors)
        per_query_vector_stats.append({"id": question["id"], **vstats})

        ranked_lists: list[list[Location]] = []
        recalls5, rrs = [], []
        for v in vectors:
            results = hybrid_search(qdrant_client, collection_name, v, sparse_vector, top_k=20)[:5]
            ranked: list[Location] = [
                (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
                for r in results
            ]
            ranked_lists.append(ranked)
            m = compute_rank_metrics(ranked, expected_locations)
            recalls5.append(m.recall_at_5)
            rrs.append(m.reciprocal_rank)

        flags = ranking_flip_flags(ranked_lists, recalls5, rrs)
        top1_flips += flags["top1_flip"]
        top3_set_changes += flags["top3_set_change"]
        top5_set_changes += flags["top5_set_change"]
        mrr_impacting_flips += flags["mrr_impacting_flip"]
        recall5_impacting_flips += flags["recall_at_5_impacting_flip"]

    await ollama.aclose()
    n = len(sample_questions)
    return {
        "config": config.label(),
        "sample_size": n,
        "repeats_per_query": NONDETERMINISM_REPEATS,
        "vector_stats": {
            "max_abs_delta": max(s["max_abs_delta"] for s in per_query_vector_stats),
            "mean_abs_delta": statistics.mean(s["mean_abs_delta"] for s in per_query_vector_stats),
            "mean_cosine_similarity": statistics.mean(
                s["mean_cosine_similarity"] for s in per_query_vector_stats
            ),
        },
        "ranking_impact": {
            "top1_flip_rate": top1_flips / n,
            "top3_set_change_rate": top3_set_changes / n,
            "top5_set_change_rate": top5_set_changes / n,
            "mrr_impacting_flip_rate": mrr_impacting_flips / n,
            "recall_at_5_impacting_flip_rate": recall5_impacting_flips / n,
        },
        "per_query_vector_stats": per_query_vector_stats,
    }


async def measure_retrieval_determinism(
    config, settings_obj, golden_questions: list[dict], collection_name: str,
    fingerprint_digest: str, cache: EmbeddingCache,
) -> dict:
    """With embeddings held FROZEN (from cache — zero embedding calls),
    repeat the exact same retrieval RETRIEVAL_DETERMINISM_REPEATS times
    per query and check whether Qdrant/RRF's own ranking is stable. This
    isolates Qdrant/RRF/tie-breaking determinism from embedding
    nondeterminism entirely.
    """
    from app.retrieval.hybrid_search import hybrid_search

    qdrant_client = QdrantClient(url=settings_obj.qdrant_url)
    sparse_encoder = SparseEncoder()
    unstable_questions = []

    real_questions = [q for q in golden_questions if not q.get("expect_not_found")]
    for question in real_questions:
        query = question["query"]
        key = cache_key(
            config.ollama_model, config.revision, config.dimension, config.query_prefix(),
            query, fingerprint_digest,
        )
        vector = cache.get(key, expected_fingerprint=fingerprint_digest)
        if vector is None:
            continue
        sparse_vector = sparse_encoder.embed_query(query)

        ranked_lists = []
        for _ in range(RETRIEVAL_DETERMINISM_REPEATS):
            results = hybrid_search(qdrant_client, collection_name, vector, sparse_vector, top_k=20)
            ranked_lists.append(tuple(r.payload["source_id"] + str(r.score) for r in results[:5]))

        if not is_retrieval_stable(ranked_lists):
            unstable_questions.append(question["id"])

    return {
        "config": config.label(),
        "questions_checked": len(real_questions),
        "repeats_per_query": RETRIEVAL_DETERMINISM_REPEATS,
        "unstable_question_count": len(unstable_questions),
        "unstable_question_ids": unstable_questions,
        "is_fully_deterministic": len(unstable_questions) == 0,
    }


def canonical_per_question_metrics(multi_run_passes: list[dict]) -> dict[str, dict]:
    """Averages per-question metrics ACROSS the NUM_LIVE_RUNS independent
    live passes — Sprint 21's canonical per-question value for the
    non-inferiority test and power analysis. Averaging across repeated
    live runs reduces embedding-nondeterminism noise in the per-question
    signal while still keeping the result genuinely PAIRED per question
    (every question still gets exactly one canonical value per config).
    """
    ids = set()
    for pass_result in multi_run_passes:
        ids.update(pass_result["per_question"].keys())

    canonical = {}
    for qid in ids:
        values = [
            p["per_question"][qid] for p in multi_run_passes if qid in p["per_question"]
        ]
        canonical[qid] = {
            metric: statistics.mean(v[metric] for v in values)
            for metric in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr", "ndcg_at_5")
        }
    return canonical


def _subset_ids(golden_questions: list[dict], subset: str) -> set[str]:
    if subset == "overall":
        return {q["id"] for q in golden_questions if not q.get("expect_not_found")}
    if subset == "cross_lingual":
        return {
            q["id"] for q in golden_questions
            if q.get("content_lang") and q["query_lang"] != q["content_lang"]
        }
    if subset == "mono_lingual":
        return {
            q["id"] for q in golden_questions
            if q.get("content_lang") and q["query_lang"] == q["content_lang"]
        }
    raise ValueError(f"Unknown subset {subset!r}")


def run_distribution(per_run_values: list[float]) -> dict:
    return {
        "mean": statistics.mean(per_run_values),
        "median": statistics.median(per_run_values),
        "stddev": statistics.stdev(per_run_values) if len(per_run_values) > 1 else 0.0,
        "min": min(per_run_values),
        "max": max(per_run_values),
        "p5": _percentile(per_run_values, 5),
        "p95": _percentile(per_run_values, 95),
        "n_runs": len(per_run_values),
    }


async def main_async(args: argparse.Namespace) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    golden_questions = sorted(load_golden_questions(GOLDEN_SET_PATH), key=lambda q: q["id"])
    fingerprints = compute_dataset_and_corpus_fingerprints(golden_questions)
    print(f"Dataset fingerprint: {fingerprints['dataset_fingerprint'][:16]}...")
    print(f"Corpus fingerprint: {fingerprints['corpus_fingerprint'][:16]}...")

    configs = {token: parse_config_token(token, settings) for token in CONFIG_TOKENS}
    label_to_config = {config.label(): config for config in configs.values()}

    index_info = {}
    for token, config in configs.items():
        print(f"Indexing {config.label()}...")
        index_info[config.label()] = await index_config(config, settings, golden_questions)

    print("Measuring embedding nondeterminism...")
    sample = stratified_sample(golden_questions, NONDETERMINISM_SAMPLE_SIZE)
    nondeterminism = {}
    for token, config in configs.items():
        nondeterminism[config.label()] = await measure_embedding_nondeterminism(
            config, settings, sample, index_info[config.label()]["collection_name"]
        )

    print("Populating frozen embedding cache (real live calls)...")
    caches = {}
    for token, config in configs.items():
        cache_path = CACHE_DIR / _sanitize_label(config.label()) / "embeddings.json"
        cache = EmbeddingCache(cache_path)
        await run_query_pass(
            config, settings, golden_questions, index_info[config.label()]["collection_name"],
            index_info[config.label()]["fingerprint_digest"], embedding_mode="live",
            cache=cache, populate_cache=True,
        )
        cache.save()
        caches[config.label()] = cache

    print("Checking retrieval determinism (frozen embeddings)...")
    retrieval_determinism = {}
    for token, config in configs.items():
        retrieval_determinism[config.label()] = await measure_retrieval_determinism(
            config, settings, golden_questions, index_info[config.label()]["collection_name"],
            index_info[config.label()]["fingerprint_digest"], caches[config.label()],
        )

    print(f"Running {NUM_LIVE_RUNS} independent live quality passes per config...")
    multi_run_passes: dict[str, list[dict]] = defaultdict(list)
    for run_idx in range(NUM_LIVE_RUNS):
        for token, config in configs.items():
            print(f"  run {run_idx + 1}/{NUM_LIVE_RUNS}: {config.label()}")
            pass_result = await run_query_pass(
                config, settings, golden_questions, index_info[config.label()]["collection_name"],
                index_info[config.label()]["fingerprint_digest"], embedding_mode="live",
            )
            multi_run_passes[config.label()].append(pass_result)

    # ---- run-to-run distributions ----
    distributions = {}
    for label, passes in multi_run_passes.items():
        aggregated_runs = [aggregate_pass(p, golden_questions) for p in passes]
        distributions[label] = {
            "cross_lingual_recall_at_5": run_distribution(
                [a["cross_lingual"]["recall_at_5"] for a in aggregated_runs]
            ),
            "cross_lingual_mrr": run_distribution(
                [a["cross_lingual"]["mrr"] for a in aggregated_runs]
            ),
            "ndcg_at_5": run_distribution([a["overall"]["ndcg_at_5"] for a in aggregated_runs]),
        }

    delta_distribution = {
        "cross_lingual_recall_at_5": [
            large_run["cross_lingual"]["recall_at_5"] - small_run["cross_lingual"]["recall_at_5"]
            for large_run, small_run in zip(
                [aggregate_pass(p, golden_questions) for p in multi_run_passes[LARGE_LABEL]],
                [aggregate_pass(p, golden_questions) for p in multi_run_passes[SMALL_LABEL]],
            )
        ],
    }

    # ---- operational metrics: aggregated across ALL live runs' real timing samples ----
    operational = {}
    for label, passes in multi_run_passes.items():
        all_embed_ms = [ms for p in passes for ms in p["query_embed_ms"]]
        all_retrieval_ms = [ms for p in passes for ms in p["retrieval_ms"]]
        operational[label] = {
            "query_embed_p50_ms": _percentile(all_embed_ms, 50),
            "query_embed_p95_ms": _percentile(all_embed_ms, 95),
            "retrieval_p50_ms": _percentile(all_retrieval_ms, 50),
            "retrieval_p95_ms": _percentile(all_retrieval_ms, 95),
            "sample_count": len(all_embed_ms),
            "dimension": label_to_config[label].dimension,
            "indexing_seconds": index_info[label]["indexing_seconds"],
            "chunks_per_second": index_info[label]["chunks_per_second"],
            "storage_bytes": index_info[label]["storage_bytes"],
            "storage_measurement": index_info[label]["storage_measurement"],
        }

    # ---- non-inferiority ----
    canonical = {
        label: canonical_per_question_metrics(passes)
        for label, passes in multi_run_passes.items()
    }
    subset_ids = sorted(_subset_ids(golden_questions, PRIMARY_SUBSET))
    shared_ids = [
        qid for qid in subset_ids
        if qid in canonical[LARGE_LABEL] and qid in canonical[SMALL_LABEL]
    ]

    non_inferiority_results = []
    for metric, margin in [
        ("recall_at_5", NON_INFERIORITY_MARGINS["cross_recall_at_5"]),
        ("mrr", NON_INFERIORITY_MARGINS["cross_mrr"]),
    ]:
        values_large = [canonical[LARGE_LABEL][qid][metric] for qid in shared_ids]
        values_small = [canonical[SMALL_LABEL][qid][metric] for qid in shared_ids]
        ci = paired_bootstrap_ci(
            values_large, values_small, metric=metric, subset=PRIMARY_SUBSET,
            seed=BOOTSTRAP_SEED, iterations=BOOTSTRAP_ITERATIONS,
        )
        non_inferiority_results.append(evaluate_non_inferiority(ci, margin=margin))

    mono_ids = sorted(_subset_ids(golden_questions, "mono_lingual"))
    mono_shared_ids = [
        qid for qid in mono_ids if qid in canonical[LARGE_LABEL] and qid in canonical[SMALL_LABEL]
    ]
    mono_values_large = [canonical[LARGE_LABEL][qid]["recall_at_5"] for qid in mono_shared_ids]
    mono_values_small = [canonical[SMALL_LABEL][qid]["recall_at_5"] for qid in mono_shared_ids]
    mono_ci = paired_bootstrap_ci(
        mono_values_large, mono_values_small, metric="recall_at_5", subset="mono_lingual",
        seed=BOOTSTRAP_SEED, iterations=BOOTSTRAP_ITERATIONS,
    )
    non_inferiority_results.append(
        evaluate_non_inferiority(mono_ci, margin=NON_INFERIORITY_MARGINS["mono_recall_at_5"])
    )

    primary_ni = non_inferiority_results[0]  # cross-lingual recall_at_5 — the primary metric

    # ---- power analysis (primary metric, cross-lingual subset) ----
    power = power_analysis(
        [canonical[LARGE_LABEL][qid][PRIMARY_METRIC] for qid in shared_ids],
        [canonical[SMALL_LABEL][qid][PRIMARY_METRIC] for qid in shared_ids],
        margin=NON_INFERIORITY_MARGINS["cross_recall_at_5"],
    )

    decision = production_decision(
        primary_ni, material_margin=MATERIAL_MARGIN,
        small_label=SMALL_LABEL, large_label=LARGE_LABEL,
    )

    # ---- write artifacts ----
    results = {
        "fingerprints": fingerprints,
        "configs": {label: {"dimension": operational[label]["dimension"]} for label in operational},
        "index_info": index_info,
        "operational": operational,
        "num_live_runs": NUM_LIVE_RUNS,
        "golden_set_path": GOLDEN_SET_PATH,
        "question_count": len(golden_questions),
        "historical_nomic_reference": {
            "note": (
                "nomic@768 was NOT benchmarked this sprint (out of scope) — figures below are "
                "carried over from Sprint 20's real measurement for context only."
            ),
            "label": NOMIC_HISTORICAL_LABEL,
            "cross_recall_at_5": 0.569,
            "cross_mrr": 0.416,
            "mono_recall_at_5": 0.920,
            "query_embed_p95_ms": 43.3,
            "dimension": 768,
            "source": "artifacts/embedding-benchmark-sprint20/report.md",
        },
    }
    (OUTPUT_DIR / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))

    stability = {
        "embedding_nondeterminism": nondeterminism,
        "retrieval_determinism": retrieval_determinism,
        "run_to_run_distributions": distributions,
        "delta_distribution_large_minus_small": delta_distribution,
    }
    (OUTPUT_DIR / "stability.json").write_text(json.dumps(stability, indent=2, ensure_ascii=False))

    non_inferiority_json = {
        "delta_convention": "large (qwen3-4b@1024) - small (qwen3-0.6b@768)",
        "small_label": SMALL_LABEL,
        "large_label": LARGE_LABEL,
        "margins": NON_INFERIORITY_MARGINS,
        "results": [
            {
                "metric": r.metric,
                "subset": "mono_lingual" if is_mono else "cross_lingual",
                "margin": r.margin,
                "observed_delta": r.observed_delta,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
                "is_non_inferior": r.is_non_inferior,
                "seed": r.seed,
                "iterations": r.iterations,
                "sample_size": len(mono_shared_ids) if is_mono else len(shared_ids),
            }
            for is_mono, r in zip(
                [False, False, True], non_inferiority_results, strict=True
            )
        ],
        "production_decision": decision,
    }
    (OUTPUT_DIR / "non_inferiority.json").write_text(
        json.dumps(non_inferiority_json, indent=2, ensure_ascii=False)
    )

    power_json = {
        "primary_metric": PRIMARY_METRIC,
        "primary_subset": PRIMARY_SUBSET,
        "current_n": power.current_n,
        "margin": power.margin,
        "observed_paired_stddev": power.observed_paired_stddev,
        "power_80_required_n": power.required_n_80_power,
        "power_90_required_n": power.required_n_90_power,
        "method": power.method,
        "limitations": power.limitations,
        "sufficient_at_80_power": power.current_n >= power.required_n_80_power,
        "sufficient_at_90_power": power.current_n >= power.required_n_90_power,
    }
    (OUTPUT_DIR / "power_analysis.json").write_text(
        json.dumps(power_json, indent=2, ensure_ascii=False)
    )

    report = render_report(
        fingerprints, operational, nondeterminism, retrieval_determinism, distributions,
        non_inferiority_results, decision, power,
    )
    (OUTPUT_DIR / "report.md").write_text(report)
    print(report)
    print(f"\nWritten to {OUTPUT_DIR}/{{results,stability,non_inferiority,power_analysis}}.json "
          f"and {OUTPUT_DIR}/report.md")


def render_report(
    fingerprints: dict, operational: dict, nondeterminism: dict, retrieval_determinism: dict,
    distributions: dict, non_inferiority_results: list, decision: dict, power,
) -> str:
    lines = [
        "# Embedding Benchmark Sprint 21: Non-Inferiority & Stability Decision",
        "",
        f"Dataset fingerprint: `{fingerprints['dataset_fingerprint']}`",
        "",
        f"Corpus fingerprint: `{fingerprints['corpus_fingerprint']}`",
        "",
        f"Only 2 configurations tested this sprint: {SMALL_LABEL} (efficiency candidate), "
        f"{LARGE_LABEL} (quality candidate). nomic@768 shown below as a historical reference "
        "from Sprint 20 only — not re-benchmarked.",
        "",
        "## Embedding nondeterminism (bit-level) vs. ranking impact",
        "",
        "Floating-point nondeterminism in the embedding backend is NOT the same thing as "
        "retrieval-level instability — a vector can differ slightly between repeated calls "
        "while every top-k ranking it produces stays identical. Both are measured and reported "
        "separately below.",
        "",
        "| Config | Max abs vector delta | Mean abs delta | Mean cosine sim | Top1 flip rate | "
        "Top3 set change | Top5 set change | MRR-impacting flips | Recall@5-impacting flips |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, nd in nondeterminism.items():
        vs = nd["vector_stats"]
        ri = nd["ranking_impact"]
        lines.append(
            f"| {label} | {vs['max_abs_delta']:.2e} | {vs['mean_abs_delta']:.2e} | "
            f"{vs['mean_cosine_similarity']:.6f} | {ri['top1_flip_rate']:.3f} | "
            f"{ri['top3_set_change_rate']:.3f} | {ri['top5_set_change_rate']:.3f} | "
            f"{ri['mrr_impacting_flip_rate']:.3f} | {ri['recall_at_5_impacting_flip_rate']:.3f} |"
        )

    lines += [
        "",
        f"(n={NONDETERMINISM_SAMPLE_SIZE} stratified queries x {NONDETERMINISM_REPEATS} "
        "repeated live embeddings each.)",
        "",
        "## Retrieval determinism (frozen embeddings, Qdrant/RRF only)",
        "",
        "| Config | Questions checked | Repeats | Unstable questions | Fully deterministic? |",
        "|---|---|---|---|---|",
    ]
    for label, rd in retrieval_determinism.items():
        lines.append(
            f"| {label} | {rd['questions_checked']} | {rd['repeats_per_query']} | "
            f"{rd['unstable_question_count']} | {rd['is_fully_deterministic']} |"
        )

    lines += [
        "",
        "## Run-to-run distributions (10 independent live runs per config)",
        "",
        "| Config | Metric | Mean | Median | Stddev | Min | Max | P5 | P95 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, dist in distributions.items():
        for metric_name, d in dist.items():
            lines.append(
                f"| {label} | {metric_name} | {d['mean']:.4f} | {d['median']:.4f} | "
                f"{d['stddev']:.4f} | {d['min']:.4f} | {d['max']:.4f} | {d['p5']:.4f} | "
                f"{d['p95']:.4f} |"
            )

    lines += [
        "",
        "## Operational comparison",
        "",
        "| Config | Dim | Query p50/p95 (ms) | Retrieval p50/p95 (ms) | Index chunks/s | "
        "Storage (bytes) |",
        "|---|---|---|---|---|---|",
    ]
    for label, op in operational.items():
        lines.append(
            f"| {label} | {op['dimension']} | {op['query_embed_p50_ms']:.1f}/"
            f"{op['query_embed_p95_ms']:.1f} | {op['retrieval_p50_ms']:.1f}/"
            f"{op['retrieval_p95_ms']:.1f} | {op['chunks_per_second']:.2f} | "
            f"{op['storage_bytes']} ({op['storage_measurement']}) |"
        )
    lines += [
        "",
        "Historical reference (Sprint 20, NOT re-benchmarked): nomic@768 query p95 ~43ms, "
        "dimension 768. Note: qwen3-4b@1024's smaller dimension reduces Qdrant "
        "storage/index footprint vs. qwen3-4b@native, but the underlying model is STILL the "
        "4B-parameter model — its embedding INFERENCE latency does not drop to 0.6B levels "
        "just because the output vector was truncated. qwen3-0.6b@768 is a genuinely "
        "different, smaller model, so it differs in BOTH inference compute AND vector "
        "dimension — these are two independent cost axes, not one.",
        "",
        "## Pre-committed non-inferiority results",
        "",
        f"delta = {LARGE_LABEL} - {SMALL_LABEL} (positive = large scored higher). "
        f"Non-inferior iff the CI's UPPER bound stays under the margin.",
        "",
        "| Metric | Subset | Margin | Observed delta | CI lower | CI upper | Non-inferior? |",
        "|---|---|---|---|---|---|---|",
    ]
    ni_subsets = ["cross_lingual", "cross_lingual", "mono_lingual"]
    for r, subset in zip(non_inferiority_results, ni_subsets, strict=True):
        lines.append(
            f"| {r.metric} | {subset} | {r.margin} | {r.observed_delta:.4f} | "
            f"{r.ci_lower:.4f} | {r.ci_upper:.4f} | {r.is_non_inferior} |"
        )

    lines += [
        "",
        "## Power analysis",
        "",
        f"Current cross-lingual n: {power.current_n}. Observed paired stddev: "
        f"{power.observed_paired_stddev:.4f}. Estimated n needed for 80% power: "
        f"{power.required_n_80_power}. For 90% power: {power.required_n_90_power}.",
        "",
        power.method,
        "",
        f"Limitations: {power.limitations}",
        "",
        "## Production decision",
        "",
        f"**Verdict: {decision['verdict']}**",
        "",
        decision["reason"],
        "",
        "`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the actual "
        "production default. This is a decision sprint; an actual migration is a separate, "
        "later action.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sprint 21: non-inferiority and stability benchmark "
        "(qwen3-0.6b@768 vs qwen3-4b@1024)"
    )
    parser.parse_args()
    asyncio.run(main_async(argparse.Namespace()))


if __name__ == "__main__":
    main()
