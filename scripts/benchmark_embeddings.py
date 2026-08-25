"""Sprint 18/19: real, isolated benchmark comparing embedding model
configurations on multilingual/cross-lingual retrieval quality AND
operational cost — against native Ollama + docker-compose Qdrant, not
mocked.

    python -m scripts.benchmark_embeddings --configs nomic@native qwen3-4b@native

Sprint 19 generalized Sprint 18's baseline-vs-challenger script into a
multi-candidate one: any number of "model@dimension" configs (see
app/llm/embedding_models.py::parse_config_token) can be compared in one
run, each in its own isolated Qdrant collection
(kb_benchmark_{model}_{dimension}) and its own SQLite registry under
--work-dir. Neither touches settings.qdrant_collection_name/
registry_db_path — this script never opens the production collection.

Single variable per comparison: chunking, sparse encoding, RRF fusion,
top_k/top_n, and reranker (off) are IDENTICAL across every config — all
go through the exact same app/retrieval/search.py::search() call, which
is also production's own retrieval path.

A config whose requested output dimension isn't actually honored by the
backend (Ollama silently CLAMPS an out-of-range dimensions request
instead of erroring — see app/llm/ollama_client.py::OllamaClient.embed)
is marked unsupported=True and skipped, never silently substituted.

Writes results.json (full machine-readable data, every config's
quality/language-pair/operational metrics, support state) and report.md
(the human-readable table, Pareto frontier, and production
recommendation) to --output-dir. Any metric this environment can't
reliably measure (see OperationalMetrics.ram_mb) is recorded as
None / "not measured" — never guessed.
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.bootstrap import paired_bootstrap_ci
from app.evaluation.golden_set_validation import language_pair_counts
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.citation_location import location_for
from app.llm.embedding_models import EmbeddingModelConfig, parse_config_token
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from tests.fixtures.golden_api_reference_en import build_golden_api_reference_en
from tests.fixtures.golden_enterprise_faq_tr import build_golden_enterprise_faq_tr
from tests.fixtures.golden_markdown_source import build_golden_markdown_source
from tests.fixtures.golden_source import build_golden_source_pdf

DEFAULT_GOLDEN_SET = "tests/fixtures/embedding_benchmark_golden.json"
DEFAULT_WORK_DIR = "artifacts/embedding-benchmark-sprint19/work"
DEFAULT_OUTPUT_DIR = "artifacts/embedding-benchmark-sprint19"
QDRANT_CONTAINER_NAME = "kb-rag-qdrant"

# Sprint 19's exact configuration matrix — every one of these was
# verified with a real /api/embed call before being defaulted here (see
# docs/sprint-19-plan.md): all 6 are genuinely supported by this
# environment's Ollama 0.32.6.
DEFAULT_CONFIGS = [
    "nomic@native",
    "qwen3-0.6b@native",
    "qwen3-4b@native",
    "qwen3-4b@1024",
    "qwen3-0.6b@1024",
    "qwen3-0.6b@768",
]

WARMUP_CALLS = 3
CROSS_LINGUAL_CELLS = ["tr_query_en_content", "en_query_tr_content"]
MONO_LINGUAL_CELLS = ["tr_query_tr_content", "en_query_en_content"]

# The Sprint 18 "quality ceiling" reference every smaller/truncated
# config's acceptance is measured against.
QUALITY_CEILING_LABEL = "qwen3-4b@native"

# Sprint 19's acceptance thresholds (docs/sprint-19-plan.md /
# user-specified) — a smaller/cheaper config is a production CANDIDATE
# over the quality-ceiling model only if it stays within these losses.
# These are not statistically derived (68 questions is too small for
# that — see the report's Statistical caution section); they encode a
# judgment call about how much quality a real deployment could tolerate
# losing for a meaningful cost win, stated explicitly rather than left
# implicit in code.
MAX_CROSS_RECALL_LOSS = 0.05
MAX_CROSS_MRR_LOSS = 0.05
MAX_MONO_RECALL_REGRESSION = 0.02

# Sprint 20: exactly the 3 configurations this sprint compares (does NOT
# replace DEFAULT_CONFIGS above — Sprint 19's own invocation/tests still
# use that 6-config list unchanged). nomic@768 is the same collection
# nomic@native ends up in (nomic's native dimension IS 768), just named
# by the literal dimension per this sprint's own naming convention.
SPRINT20_CONFIGS = ["nomic@768", "qwen3-0.6b@768", "qwen3-4b@1024"]
SPRINT20_GOLDEN_SET = "tests/fixtures/embedding_benchmark_golden_v2.json"

# Sprint 20's acceptance thresholds — pre-committed here, BEFORE any
# result was known, per this sprint's own rule ("thresholdları... sonuç
# çıktıktan sonra winner'a göre değiştirme"). Distinct from Sprint 19's
# thresholds above (which compared against qwen3-4b@native, the 2560-dim
# quality ceiling): Sprint 20 compares qwen3-0.6b@768 against
# qwen3-4b@1024 specifically, the two candidates Sprint 19 found closest
# together — tighter thresholds here reflect that Sprint 19 already
# established both configs are reasonably strong, so this sprint is
# arbitrating a SMALLER gap, not asking "is any loss acceptable."
SPRINT20_MAX_CROSS_RECALL_LOSS = 0.03
SPRINT20_MAX_CROSS_MRR_LOSS = 0.04
SPRINT20_MAX_MONO_RECALL_LOSS = 0.01
SPRINT20_BOOTSTRAP_SEED = 20200601
SPRINT20_BOOTSTRAP_ITERATIONS = 5000
# Below this, a Qwen candidate's cross-lingual quality is considered
# broken enough that nomic could win on quality/feasibility grounds
# regardless of cost — arbitrary but explicit, and NOT expected to
# trigger given Sprint 18/19's own measured numbers (both Qwen configs
# were consistently well above 0.5 cross-lingual Recall@5 in every
# prior run).
SPRINT20_CRISIS_CROSS_RECALL_FLOOR = 0.5
# How far below the BEST supported config's cross-lingual Recall@5 a
# config may fall and still be considered for EFFICIENCY WINNER — this
# is what stops a fast-but-weak config (nomic, real measured
# cross-lingual Recall@5 ~0.58-0.61 across Sprint 18/19/20 — well above
# the crisis floor but ~0.35-0.4 below both Qwen candidates) from
# winning "efficiency" purely on latency while being clearly worse in
# quality than every other option. Not the same guard as the crisis
# floor above (that one is absolute, this one is relative to whichever
# config actually won on quality this run).
EFFICIENCY_QUALITY_MARGIN = 0.15


def _sanitize_label(label: str) -> str:
    return label.replace("@", "_").replace(".", "").replace("-", "_")


def collection_name_for(config: EmbeddingModelConfig) -> str:
    return f"kb_benchmark_{_sanitize_label(config.label())}"


def build_corpus(docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    build_golden_source_pdf(str(docs_dir / "nimbus_handbook.pdf"))
    build_golden_markdown_source(str(docs_dir / "nimbus_cli.md"))
    build_golden_api_reference_en(str(docs_dir / "nimbus_api_reference.md"))
    build_golden_enterprise_faq_tr(str(docs_dir / "nimbus_kurumsal_sss.md"))


def load_golden_questions(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def _stop_ollama_model(model: str) -> None:
    """Best-effort model eviction so the first embed call of a phase is a
    genuine cold load, not warm from a previous phase/manual testing.
    Failure here is non-fatal — model_load_seconds just becomes less
    meaningful, not a crash.
    """
    try:
        subprocess.run(["ollama", "stop", model], capture_output=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _measure_real_collection_disk_bytes(collection_name: str) -> int | None:
    """Best-effort REAL disk measurement (Sprint 19 upgrade over Sprint
    18's formula-only estimate) via `docker exec du` on the Qdrant
    container's own storage volume. Returns None (not an exception) if
    docker/the container/the path isn't available — the caller falls
    back to the formula estimate and labels it as such. Never raises.

    Uses `-sk` (block-based KB), NOT `-sb`/--apparent-size — verified for
    real against this environment's actual collections: Qdrant
    preallocates its dense-vector storage and WAL as large, mostly-empty
    SPARSE mmap files (e.g. a 32MB logical WAL segment for a 32-chunk
    collection), and `-sb` reports that full logical/apparent size,
    which was nearly IDENTICAL (~211MB) across every config regardless
    of real dimension — not a real per-config storage signal. `-sk`
    reports actual disk blocks consumed, which genuinely differed by
    config when checked directly (nomic@native 2444KB vs
    qwen3-4b@native 2944KB) — see docs/sprint-19-plan.md.
    """
    try:
        result = subprocess.run(
            [
                "docker", "exec", QDRANT_CONTAINER_NAME,
                "du", "-sk", f"/qdrant/storage/collections/{collection_name}",
            ],
            capture_output=True, timeout=15, check=False, text=True,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.split()[0]) * 1024
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


@dataclass
class OperationalMetrics:
    embedding_dimension: int
    indexing_seconds: float
    chunks_indexed: int
    chunks_per_second: float
    model_load_seconds: float | None
    query_embed_p50_ms: float
    query_embed_p95_ms: float
    total_retrieval_p50_ms: float
    total_retrieval_p95_ms: float
    query_sample_count: int
    storage_bytes: int
    storage_measurement: str  # "real" (docker exec du) or "estimate"
    ram_mb: None = None  # not measured — see module docstring
    vram_mb: None = None  # not measured — see module docstring

    def as_dict(self) -> dict:
        d = asdict(self)
        d["ram_mb"] = "not measured"
        d["vram_mb"] = "not measured"
        if self.model_load_seconds is None:
            d["model_load_seconds"] = "not measured"
        return d


async def probe_dimension_support(
    ollama: OllamaClient, config: EmbeddingModelConfig
) -> tuple[bool, int]:
    """A REAL call, not an assumption — Ollama silently clamps an
    out-of-range `dimensions` request to the model's native size instead
    of erroring, so the only honest way to know whether a config is
    supported is to make the call and check what actually came back.
    """
    vector = await ollama.embed("dimension probe", model=config.ollama_model, prefix="")
    if config.output_dimension is None:
        return True, len(vector)
    vector = await ollama.embed(
        "dimension probe", model=config.ollama_model, dimensions=config.output_dimension
    )
    return len(vector) == config.output_dimension, len(vector)


async def run_config_benchmark(
    config: EmbeddingModelConfig,
    settings_obj,
    golden_questions: list[dict],
    work_dir: Path,
) -> dict:
    label = config.label()
    collection_name = collection_name_for(config)
    registry_path = work_dir / f"registry_{_sanitize_label(label)}.db"
    docs_dir = work_dir / "corpus"
    if not docs_dir.exists():
        build_corpus(docs_dir)

    _stop_ollama_model(config.ollama_model)
    probe_ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    supported, actual_dimension = await probe_dimension_support(probe_ollama, config)
    await probe_ollama.aclose()

    if not supported:
        return {
            "label": label,
            "model_key": config.key,
            "ollama_model": config.ollama_model,
            "requested_dimension": config.dimension,
            "actual_dimension_returned": actual_dimension,
            "supported": False,
        }

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
            text,
            model=config.ollama_model,
            prefix=config.document_prefix(),
            dimensions=config.output_dimension,
        )

    connector = LocalFilesystemConnector(str(docs_dir))

    load_start = time.perf_counter()
    first_embed_at = {"t": None}

    async def timed_embed_fn(text: str) -> list[float]:
        vector = await embed_fn(text)
        if first_embed_at["t"] is None:
            first_embed_at["t"] = time.perf_counter() - load_start
        return vector

    index_start = time.perf_counter()
    stats = await ingest_connector(
        connector, store, registry, timed_embed_fn, sparse_encoder,
        pipeline_fingerprint=fingerprint,
    )
    indexing_seconds = time.perf_counter() - index_start
    chunks_per_second = stats.chunks_upserted / indexing_seconds if indexing_seconds > 0 else 0.0

    real_storage_bytes = _measure_real_collection_disk_bytes(collection_name)
    if real_storage_bytes is not None:
        storage_bytes, storage_measurement = real_storage_bytes, "real"
    else:
        collection_info = qdrant_client.get_collection(collection_name)
        point_count = collection_info.points_count or 0
        storage_bytes = point_count * (config.dimension * 4 + 2048)
        storage_measurement = "estimate"

    # Deterministic warmup — discarded, never mixed into the timed
    # samples below, so a cold-start outlier can't skew p50/p95.
    for _ in range(WARMUP_CALLS):
        await ollama.embed("warmup query", model=config.ollama_model,
                            prefix=config.query_prefix(), dimensions=config.output_dimension)

    query_embed_ms: list[float] = []
    retrieval_ms: list[float] = []
    per_cell_metrics: dict[tuple[str, str], list] = defaultdict(list)
    all_metrics = []
    not_found_hits = 0
    not_found_total = 0
    # Sprint 20: per-question metrics, keyed by golden-question id — the
    # raw material app/evaluation/bootstrap.py::paired_bootstrap_ci needs
    # (paired resampling requires the SAME question set scored by both
    # configs being compared, matched by id, not just position).
    per_question: dict[str, dict] = {}

    for question in golden_questions:
        query = question["query"]
        expected_locations: list[Location] = [tuple(loc) for loc in question["expected_locations"]]
        is_not_found = question.get("expect_not_found", False)

        embed_start = time.perf_counter()
        await ollama.embed(query, model=config.ollama_model, prefix=config.query_prefix(),
                            dimensions=config.output_dimension)
        query_embed_ms.append((time.perf_counter() - embed_start) * 1000)

        retrieval_start = time.perf_counter()
        results = await search(
            query, ollama, sparse_encoder, qdrant_client, collection_name, config.ollama_model,
            reranker=None,  # rule: reranker OFF for this benchmark
            query_prefix=config.query_prefix(),
            dimensions=config.output_dimension,
        )
        retrieval_ms.append((time.perf_counter() - retrieval_start) * 1000)

        ranked_locations = [
            (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
            for r in results
        ]

        if is_not_found:
            not_found_total += 1
            if not results or not ranked_locations:
                not_found_hits += 1
            continue

        metrics = compute_rank_metrics(ranked_locations, expected_locations)
        all_metrics.append(metrics)
        cell = (question["query_lang"], question["content_lang"])
        per_cell_metrics[cell].append(metrics)
        per_question[question["id"]] = {
            "recall_at_1": metrics.recall_at_1,
            "recall_at_3": metrics.recall_at_3,
            "recall_at_5": metrics.recall_at_5,
            "mrr": metrics.reciprocal_rank,
            "ndcg_at_5": metrics.ndcg_at_5,
        }

    await ollama.aclose()

    by_cell = {
        f"{query_lang}_query_{content_lang}_content": aggregate_rank_metrics(metrics)
        | {"question_count": len(metrics)}
        for (query_lang, content_lang), metrics in sorted(per_cell_metrics.items())
    }

    def cell_mean(cells: list[str], key: str) -> float | None:
        values = [by_cell[c][key] for c in cells if c in by_cell]
        return sum(values) / len(values) if values else None

    op_metrics = OperationalMetrics(
        embedding_dimension=config.dimension,
        indexing_seconds=indexing_seconds,
        chunks_indexed=stats.chunks_upserted,
        chunks_per_second=chunks_per_second,
        model_load_seconds=first_embed_at["t"],
        query_embed_p50_ms=_percentile(query_embed_ms, 50),
        query_embed_p95_ms=_percentile(query_embed_ms, 95),
        total_retrieval_p50_ms=_percentile(retrieval_ms, 50),
        total_retrieval_p95_ms=_percentile(retrieval_ms, 95),
        query_sample_count=len(query_embed_ms),
        storage_bytes=storage_bytes,
        storage_measurement=storage_measurement,
    )

    return {
        "label": label,
        "model_key": config.key,
        "ollama_model": config.ollama_model,
        "requested_dimension": config.dimension,
        "actual_dimension_returned": actual_dimension,
        "supported": True,
        "fingerprint_digest": fingerprint.digest(),
        "overall": aggregate_rank_metrics(all_metrics),
        "by_cell": by_cell,
        "cross_lingual": {
            "recall_at_5": cell_mean(CROSS_LINGUAL_CELLS, "recall_at_5"),
            "mrr": cell_mean(CROSS_LINGUAL_CELLS, "mrr"),
            "ndcg_at_5": cell_mean(CROSS_LINGUAL_CELLS, "ndcg_at_5"),
        },
        "mono_lingual": {
            "recall_at_5": cell_mean(MONO_LINGUAL_CELLS, "recall_at_5"),
            "mrr": cell_mean(MONO_LINGUAL_CELLS, "mrr"),
            "ndcg_at_5": cell_mean(MONO_LINGUAL_CELLS, "ndcg_at_5"),
        },
        "not_found_accuracy": not_found_hits / not_found_total if not_found_total else None,
        "not_found_question_count": not_found_total,
        "operational": op_metrics.as_dict(),
        "per_question": per_question,
    }


def pareto_dominated(candidate: dict, others: list[dict]) -> str | None:
    """A config is Pareto-dominated if some OTHER supported config is at
    least as good on every objective (higher cross-lingual Recall@5,
    higher cross-lingual MRR, lower query p95, lower dimension) and
    strictly better on at least one. Returns the dominating config's
    label, or None if not dominated.
    """
    c_recall = candidate["cross_lingual"]["recall_at_5"]
    c_mrr = candidate["cross_lingual"]["mrr"]
    c_p95 = candidate["operational"]["query_embed_p95_ms"]
    c_dim = candidate["requested_dimension"]

    for other in others:
        if other["label"] == candidate["label"]:
            continue
        o_recall = other["cross_lingual"]["recall_at_5"]
        o_mrr = other["cross_lingual"]["mrr"]
        o_p95 = other["operational"]["query_embed_p95_ms"]
        o_dim = other["requested_dimension"]

        at_least_as_good = (
            o_recall >= c_recall and o_mrr >= c_mrr and o_p95 <= c_p95 and o_dim <= c_dim
        )
        strictly_better = (
            o_recall > c_recall or o_mrr > c_mrr or o_p95 < c_p95 or o_dim < c_dim
        )
        if at_least_as_good and strictly_better:
            return other["label"]
    return None


def score(result: dict) -> dict:
    supported = [r for r in result if r.get("supported")]
    if not supported:
        return {
            "quality_winner": None,
            "efficiency_winner": None,
            "production_recommendation": (
                "No configuration was supported — cannot make a recommendation."
            ),
            "pareto_dominated": {},
        }

    # Quality score: weighted combination, weights explicit — Sprint
    # 17.7/18 already established cross-lingual retrieval as the
    # motivating weakness, so it's weighted higher than overall nDCG.
    def quality_score(r: dict) -> float:
        cross_recall = r["cross_lingual"]["recall_at_5"] or 0.0
        cross_mrr = r["cross_lingual"]["mrr"] or 0.0
        ndcg = r["overall"]["ndcg_at_5"]
        return 0.4 * cross_recall + 0.3 * cross_mrr + 0.3 * ndcg

    quality_winner = max(supported, key=quality_score)

    ceiling = next((r for r in supported if r["label"] == QUALITY_CEILING_LABEL), None)

    efficiency_candidates = []
    if ceiling is not None:
        ceiling_cross_recall = ceiling["cross_lingual"]["recall_at_5"] or 0.0
        ceiling_cross_mrr = ceiling["cross_lingual"]["mrr"] or 0.0
        ceiling_mono_recall = ceiling["mono_lingual"]["recall_at_5"] or 0.0
        for r in supported:
            cross_recall_loss = ceiling_cross_recall - (r["cross_lingual"]["recall_at_5"] or 0.0)
            cross_mrr_loss = ceiling_cross_mrr - (r["cross_lingual"]["mrr"] or 0.0)
            mono_regression = ceiling_mono_recall - (r["mono_lingual"]["recall_at_5"] or 0.0)
            if (
                cross_recall_loss <= MAX_CROSS_RECALL_LOSS
                and cross_mrr_loss <= MAX_CROSS_MRR_LOSS
                and mono_regression <= MAX_MONO_RECALL_REGRESSION
            ):
                efficiency_candidates.append(r)

    # Among acceptance-passing candidates, prefer smaller dimension
    # first (dominates storage/index cost most directly), tie-break by
    # lower query p95 — deterministic, stated explicitly rather than a
    # single opaque score.
    efficiency_winner = None
    if efficiency_candidates:
        efficiency_winner = min(
            efficiency_candidates,
            key=lambda r: (r["requested_dimension"], r["operational"]["query_embed_p95_ms"]),
        )

    dominated = {}
    for r in supported:
        dominator = pareto_dominated(r, supported)
        if dominator:
            dominated[r["label"]] = dominator

    if efficiency_winner and efficiency_winner["label"] != QUALITY_CEILING_LABEL:
        recommendation = (
            f"Recommended next migration candidate: {efficiency_winner['label']} — stays within "
            f"acceptance thresholds of {QUALITY_CEILING_LABEL} (cross-lingual Recall@5/MRR loss "
            f"<= {MAX_CROSS_RECALL_LOSS}, mono-lingual regression <= {MAX_MONO_RECALL_REGRESSION}) "
            "at a real dimension/latency cost saving. nomic remains the current production "
            "default — this is a candidate for the next migration decision, not an applied "
            "change."
        )
    elif efficiency_winner:
        recommendation = (
            f"{QUALITY_CEILING_LABEL} is both the quality winner and the efficiency winner among "
            "tested configs — no smaller/cheaper config met the acceptance thresholds. nomic "
            "remains the current production default."
        )
    else:
        recommendation = (
            "No configuration met the acceptance thresholds relative to the quality ceiling "
            f"({QUALITY_CEILING_LABEL}) — NEED MORE DATA / no smaller-config recommendation. "
            "nomic remains the current production default."
        )

    return {
        "quality_winner": quality_winner["label"],
        "efficiency_winner": efficiency_winner["label"] if efficiency_winner else None,
        "efficiency_candidates": [c["label"] for c in efficiency_candidates],
        "production_recommendation": recommendation,
        "pareto_dominated": dominated,
        "acceptance_thresholds": {
            "max_cross_recall_at_5_loss": MAX_CROSS_RECALL_LOSS,
            "max_cross_mrr_loss": MAX_CROSS_MRR_LOSS,
            "max_mono_recall_at_5_regression": MAX_MONO_RECALL_REGRESSION,
            "quality_ceiling": QUALITY_CEILING_LABEL,
        },
    }


def _subset_question_ids(golden_questions: list[dict], subset: str) -> set[str]:
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


BOOTSTRAP_METRICS = ["recall_at_1", "recall_at_3", "recall_at_5", "mrr", "ndcg_at_5"]
BOOTSTRAP_SUBSETS = ["overall", "cross_lingual", "mono_lingual"]


def compute_bootstrap_report(
    result_a: dict,
    result_b: dict,
    golden_questions: list[dict],
    seed: int = SPRINT20_BOOTSTRAP_SEED,
    iterations: int = SPRINT20_BOOTSTRAP_ITERATIONS,
) -> list[dict]:
    """Paired bootstrap CIs for (result_a - result_b) across every
    (metric, subset) combination — the raw material for bootstrap.json.
    Pairing is by golden-question id, not list position: both configs
    are guaranteed to have scored the exact same question set (same
    golden_questions input), but keying by id makes that guarantee
    explicit rather than assumed.
    """
    entries = []
    for subset in BOOTSTRAP_SUBSETS:
        ids = sorted(_subset_question_ids(golden_questions, subset))
        ids = [
            qid for qid in ids
            if qid in result_a["per_question"] and qid in result_b["per_question"]
        ]
        if not ids:
            continue
        for metric in BOOTSTRAP_METRICS:
            values_a = [result_a["per_question"][qid][metric] for qid in ids]
            values_b = [result_b["per_question"][qid][metric] for qid in ids]
            ci = paired_bootstrap_ci(
                values_a, values_b, metric=metric, subset=subset,
                seed=seed, iterations=iterations,
            )
            entries.append({
                "compared_configs": [result_a["label"], result_b["label"]],
                "metric": ci.metric,
                "subset": ci.subset,
                "observed_delta": ci.observed_delta,
                "lower_ci": ci.lower,
                "upper_ci": ci.upper,
                "seed": ci.seed,
                "iterations": ci.iterations,
                "n_questions": len(ids),
            })
    return entries


def _find_bootstrap_entry(entries: list[dict], metric: str, subset: str) -> dict | None:
    return next((e for e in entries if e["metric"] == metric and e["subset"] == subset), None)


def sprint20_production_decision(
    results_by_label: dict[str, dict],
    bootstrap_entries: list[dict],
    small_label: str = "qwen3-0.6b@768",
    large_label: str = "qwen3-4b@1024",
    nomic_label: str = "nomic@768",
) -> dict:
    """Sprint 20's three-verdict decision — QUALITY WINNER, EFFICIENCY
    WINNER, PRODUCTION WINNER — implementing the exact logic specified
    in docs/sprint-20-plan.md, coded BEFORE any real result was known:

        if 0.6B quality loss (vs 4B@1024) is within practical tolerance
        AND the bootstrap CI does not confirm a materially worse gap:
            recommend qwen3-0.6b@768
        elif quality loss exceeds tolerance AND the CI confirms it:
            recommend qwen3-4b@1024
        else (point estimate and CI disagree, or data is borderline):
            NEED_MORE_DATA

    "CI confirms a materially worse gap" is deliberately asymmetric from
    "within tolerance": it requires the CI's UPPER bound (the most
    favorable-to-0.6B end of the interval) to still exceed the loss
    threshold — i.e. even bootstrap resampling's best case for 0.6B
    shows a real, threshold-exceeding gap. That asymmetry is what
    produces NEED_MORE_DATA for a genuinely ambiguous case instead of
    forcing a binary answer either direction.
    """
    small = results_by_label.get(small_label)
    large = results_by_label.get(large_label)
    nomic = results_by_label.get(nomic_label)

    if not small or not small.get("supported") or not large or not large.get("supported"):
        return {
            "quality_winner": None,
            "efficiency_winner": None,
            "production_winner": "NEED_MORE_DATA",
            "reason": f"{small_label} and/or {large_label} were not supported/available.",
        }

    # QUALITY WINNER: same weighted formula Sprint 19 used, applied to
    # whichever of the 3 Sprint 20 configs are present and supported.
    def quality_score(r: dict) -> float:
        cross_recall = r["cross_lingual"]["recall_at_5"] or 0.0
        cross_mrr = r["cross_lingual"]["mrr"] or 0.0
        ndcg = r["overall"]["ndcg_at_5"]
        return 0.4 * cross_recall + 0.3 * cross_mrr + 0.3 * ndcg

    supported = [r for r in (small, large, nomic) if r and r.get("supported")]
    quality_winner = max(supported, key=quality_score)["label"]

    # EFFICIENCY WINNER: lowest (dimension, query p95) among configs
    # whose cross-lingual quality is within a real margin of the BEST
    # supported config's quality — deterministic tie-break, dimension
    # first (dominates storage/index cost most directly), then p95.
    #
    # This is RELATIVE to the best config, not the absolute
    # SPRINT20_CRISIS_CROSS_RECALL_FLOOR (that floor is reserved for the
    # separate "both Qwen candidates are broken" nomic-fallback check
    # below) — an earlier version of this function used the absolute
    # floor here too, which let nomic@768 (real cross-lingual Recall@5
    # ~0.58, clearing 0.5 but ~0.35-0.4 below both Qwen configs — a real,
    # substantial quality gap, not a marginal one) win "efficiency" on
    # latency alone despite being clearly worse in quality than every
    # other candidate. Caught by actually running the benchmark, not
    # assumed — see docs/sprint-20-plan.md.
    best_cross_recall = max((r["cross_lingual"]["recall_at_5"] or 0.0) for r in supported)
    quality_floor = best_cross_recall - EFFICIENCY_QUALITY_MARGIN
    efficiency_candidates = [
        r for r in supported if (r["cross_lingual"]["recall_at_5"] or 0.0) >= quality_floor
    ]
    efficiency_winner = (
        min(
            efficiency_candidates,
            key=lambda r: (r["requested_dimension"], r["operational"]["query_embed_p95_ms"]),
        )["label"]
        if efficiency_candidates
        else None
    )

    # PRODUCTION WINNER: the core Sprint 20 question.
    loss_recall5 = (large["cross_lingual"]["recall_at_5"] or 0.0) - (
        small["cross_lingual"]["recall_at_5"] or 0.0
    )
    loss_mrr = (large["cross_lingual"]["mrr"] or 0.0) - (small["cross_lingual"]["mrr"] or 0.0)
    loss_mono_recall5 = (large["mono_lingual"]["recall_at_5"] or 0.0) - (
        small["mono_lingual"]["recall_at_5"] or 0.0
    )
    within_tolerance = (
        loss_recall5 <= SPRINT20_MAX_CROSS_RECALL_LOSS
        and loss_mrr <= SPRINT20_MAX_CROSS_MRR_LOSS
        and loss_mono_recall5 <= SPRINT20_MAX_MONO_RECALL_LOSS
    )

    ci_recall5 = _find_bootstrap_entry(bootstrap_entries, "recall_at_5", "cross_lingual")
    ci_mrr = _find_bootstrap_entry(bootstrap_entries, "mrr", "cross_lingual")
    # bootstrap deltas are (small - large); a materially worse gap for
    # small means the CI's upper (best-case-for-small) bound is still
    # below -threshold.
    ci_confirms_material_gap = False
    if ci_recall5 is not None:
        ci_confirms_material_gap |= ci_recall5["upper_ci"] < -SPRINT20_MAX_CROSS_RECALL_LOSS
    if ci_mrr is not None:
        ci_confirms_material_gap |= ci_mrr["upper_ci"] < -SPRINT20_MAX_CROSS_MRR_LOSS

    both_qwen_in_crisis = (
        (small["cross_lingual"]["recall_at_5"] or 0.0) < SPRINT20_CRISIS_CROSS_RECALL_FLOOR
        and (large["cross_lingual"]["recall_at_5"] or 0.0) < SPRINT20_CRISIS_CROSS_RECALL_FLOOR
    )

    if both_qwen_in_crisis and nomic and nomic.get("supported"):
        production_winner = nomic_label
        reason = (
            "Both Qwen candidates fell below the cross-lingual quality crisis floor "
            f"({SPRINT20_CRISIS_CROSS_RECALL_FLOOR}) — nomic wins on feasibility grounds."
        )
    elif within_tolerance and not ci_confirms_material_gap:
        production_winner = small_label
        reason = (
            f"{small_label}'s quality loss vs {large_label} is within practical tolerance "
            f"(Recall@5 loss {loss_recall5:.3f} <= {SPRINT20_MAX_CROSS_RECALL_LOSS}, MRR loss "
            f"{loss_mrr:.3f} <= {SPRINT20_MAX_CROSS_MRR_LOSS}, mono-lingual loss "
            f"{loss_mono_recall5:.3f} <= {SPRINT20_MAX_MONO_RECALL_LOSS}), and the bootstrap CI "
            "does not confirm a materially worse gap."
        )
    elif not within_tolerance and ci_confirms_material_gap:
        production_winner = large_label
        reason = (
            f"{small_label}'s quality loss vs {large_label} exceeds practical tolerance AND the "
            "bootstrap CI confirms the gap is real (upper bound still exceeds the threshold) — "
            f"{large_label} is the safer production choice."
        )
    else:
        production_winner = "NEED_MORE_DATA"
        reason = (
            "The point-estimate loss and the bootstrap CI disagree on whether the quality gap "
            "is within tolerance — the 220-question dataset does not give a confident answer "
            "either direction for this comparison."
        )

    return {
        "quality_winner": quality_winner,
        "efficiency_winner": efficiency_winner,
        "production_winner": production_winner,
        "reason": reason,
        "loss_vs_large": {
            "cross_recall_at_5": loss_recall5,
            "cross_mrr": loss_mrr,
            "mono_recall_at_5": loss_mono_recall5,
        },
        "within_tolerance": within_tolerance,
        "ci_confirms_material_gap": ci_confirms_material_gap,
        "thresholds": {
            "max_cross_recall_at_5_loss": SPRINT20_MAX_CROSS_RECALL_LOSS,
            "max_cross_mrr_loss": SPRINT20_MAX_CROSS_MRR_LOSS,
            "max_mono_recall_at_5_loss": SPRINT20_MAX_MONO_RECALL_LOSS,
        },
    }


def render_markdown_report(
    results: list[dict],
    decision: dict,
    golden_set_path: str,
    title: str = "Embedding Benchmark Sprint 19: Qwen3 Size & Dimension Trade-off",
    dataset_note: str = "Same 68-question golden set as Sprint 18",
    statistical_caution: str = (
        "68 questions is a small sample — per-cell cells are 16-17 questions. No "
        "bootstrap confidence intervals were computed this sprint (documented as a "
        "limitation, not attempted under time pressure with a small deterministic "
        "n — see docs/PLANNING.md's Sprint 19 closing note). Treat deltas smaller than "
        "roughly 1 question's worth of a cell (~6%) as noise, not signal."
    ),
) -> str:
    # Sprint 20: title/dataset_note/statistical_caution are parameters
    # (defaulting to Sprint 19's exact original text, so a bare call is
    # unchanged) so this SAME renderer can be reused for a differently
    # sized/described run instead of forking a near-duplicate function —
    # a run that DID compute bootstrap CIs (see
    # render_sprint20_extra_section below) must not carry Sprint 19's
    # "no bootstrap CIs were computed" caveat verbatim.
    lines = [
        f"# {title}",
        "",
        "Multi-candidate, single-variable comparison — chunking, sparse encoding, RRF "
        "fusion, top_k/top_n, and reranker (off) identical across every config below. "
        f"{dataset_note} ({golden_set_path}), apples-to-apples. "
        "See results.json for full per-config, per-question data.",
        "",
        "## Configurations tested",
        "",
        "| Config | Supported | Dimension (requested/actual) |",
        "|---|---|---|",
    ]
    for r in results:
        supported = "yes" if r["supported"] else "**NO — unsupported**"
        dims = f"{r['requested_dimension']} / {r['actual_dimension_returned']}"
        lines.append(f"| {r['label']} | {supported} | {dims} |")

    supported_results = [r for r in results if r["supported"]]

    lines += [
        "",
        "## Quality summary",
        "",
        "| Config | TR→TR R@5 | EN→EN R@5 | TR→EN R@5 | EN→TR R@5 | Cross R@5 | "
        "Cross MRR | Mono R@5 | nDCG@5 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in supported_results:
        bc = r["by_cell"]

        def g(cell, key="recall_at_5"):
            return f"{bc[cell][key]:.3f}" if cell in bc else "n/a"

        cross_r5 = r["cross_lingual"]["recall_at_5"]
        cross_mrr = r["cross_lingual"]["mrr"]
        mono_r5 = r["mono_lingual"]["recall_at_5"]
        lines.append(
            f"| {r['label']} | {g('tr_query_tr_content')} | {g('en_query_en_content')} | "
            f"{g('en_query_tr_content')} | {g('tr_query_en_content')} | "
            f"{cross_r5:.3f} | {cross_mrr:.3f} | {mono_r5:.3f} | {r['overall']['ndcg_at_5']:.3f} |"
        )

    lines += [
        "",
        "(TR→EN = Turkish query, English content. EN→TR = English query, Turkish content. "
        "Both cross-lingual. Cross R@5/MRR = mean of the two cross-lingual cells. "
        "Mono R@5 = mean of TR→TR and EN→EN.)",
        "",
        "## Operational results",
        "",
        "| Config | Dim | Index chunks/s | Index total (s) | Query p50/p95 (ms) | "
        "Retrieval p50/p95 (ms) | Load (s) | Storage (bytes, real/estimate) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in supported_results:
        op = r["operational"]
        lines.append(
            f"| {r['label']} | {op['embedding_dimension']} | {op['chunks_per_second']:.2f} | "
            f"{op['indexing_seconds']:.2f} | {op['query_embed_p50_ms']:.1f}/"
            f"{op['query_embed_p95_ms']:.1f} | {op['total_retrieval_p50_ms']:.1f}/"
            f"{op['total_retrieval_p95_ms']:.1f} | {op['model_load_seconds']} | "
            f"{op['storage_bytes']} ({op['storage_measurement']}) |"
        )
    lines.append("")
    lines.append("RAM/VRAM: not measured for any configuration (see module docstring).")

    lines += [
        "",
        "## Pareto frontier",
        "",
        "A config is Pareto-dominated if another tested config is at least as good on "
        "cross-lingual Recall@5, cross-lingual MRR, query p95, AND dimension, and "
        "strictly better on at least one.",
        "",
        "| Config | Dominated by |",
        "|---|---|",
    ]
    for r in supported_results:
        dominator = decision["pareto_dominated"].get(r["label"])
        lines.append(f"| {r['label']} | {dominator or '— (on the frontier)'} |")

    lines += [
        "",
        "## Statistical caution",
        "",
        statistical_caution,
        "",
        "## Decision",
        "",
        f"**QUALITY WINNER: {decision['quality_winner']}**",
        "",
        "**EFFICIENCY WINNER: "
        f"{decision['efficiency_winner'] or 'none met acceptance thresholds'}**",
        "",
        f"Acceptance thresholds (vs. {decision['acceptance_thresholds']['quality_ceiling']}): "
        "cross-lingual Recall@5 loss <= "
        f"{decision['acceptance_thresholds']['max_cross_recall_at_5_loss']}, "
        "cross-lingual MRR loss <= "
        f"{decision['acceptance_thresholds']['max_cross_mrr_loss']}, "
        "mono-lingual Recall@5 regression <= "
        f"{decision['acceptance_thresholds']['max_mono_recall_at_5_regression']}.",
        "",
        f"Configs meeting acceptance thresholds: {decision.get('efficiency_candidates', [])}",
        "",
        f"**PRODUCTION RECOMMENDATION:** {decision['production_recommendation']}",
        "",
        "`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the "
        "actual production default regardless of the recommendation above; switching "
        "it is a separate decision outside this sprint's scope.",
        "",
    ]
    return "\n".join(lines)


def render_sprint20_extra_section(bootstrap_entries: list[dict], decision: dict) -> str:
    compared = bootstrap_entries[0]["compared_configs"] if bootstrap_entries else []
    lines = [
        "",
        "## Paired bootstrap confidence intervals",
        "",
        f"Compared: {compared[0]} (a) vs {compared[1]} (b), delta = a - b" if compared else "",
        "",
        "| Subset | Metric | Observed delta | 95% CI lower | 95% CI upper | n | seed | "
        "iterations |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in bootstrap_entries:
        lines.append(
            f"| {e['subset']} | {e['metric']} | {e['observed_delta']:.4f} | "
            f"{e['lower_ci']:.4f} | {e['upper_ci']:.4f} | {e['n_questions']} | "
            f"{e['seed']} | {e['iterations']} |"
        )
    lines += [
        "",
        "(A CI entirely above or below zero indicates the sign of the difference is not "
        "attributable to chance at this sample size — see the Statistical caution section "
        "for what this does and doesn't imply at n≈220.)",
        "",
        "## Sprint 20 production decision",
        "",
        f"**QUALITY WINNER: {decision['quality_winner']}**",
        "",
        f"**EFFICIENCY WINNER: {decision['efficiency_winner']}**",
        "",
        f"**PRODUCTION WINNER: {decision['production_winner']}**",
        "",
        decision["reason"],
        "",
        f"Loss (large - small) vs {decision['thresholds']}: {decision['loss_vs_large']}",
        "",
        f"Within tolerance: {decision['within_tolerance']}. "
        f"CI confirms material gap: {decision['ci_confirms_material_gap']}.",
        "",
    ]
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> None:
    golden_questions = load_golden_questions(args.golden_set)
    # Sprint 20: explicit, deterministic ordering (sorted by id) rather
    # than trusting the JSON file's own on-disk order — makes query
    # order independent of how the fixture happens to be serialized.
    golden_questions = sorted(golden_questions, key=lambda q: q["id"])
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for token in args.configs:
        config = parse_config_token(token, settings)
        print(f"Running config: {config.label()}")
        result = await run_config_benchmark(config, settings, golden_questions, work_dir)
        if not result["supported"]:
            print(f"  UNSUPPORTED (requested {result['requested_dimension']}, "
                  f"got {result['actual_dimension_returned']})")
        results.append(result)

    decision = score(results)

    dataset_composition = {
        "total_questions": len(golden_questions),
        "language_pair_counts": {
            f"{qlang}_query_{clang}_content": count
            for (qlang, clang), count in language_pair_counts(golden_questions).items()
        },
        "difficulty_counts": dict(
            Counter(q.get("difficulty", "unlabeled") for q in golden_questions)
        ),
        "not_found_count": sum(1 for q in golden_questions if q.get("expect_not_found")),
    }

    output = {
        "results": results,
        "decision": decision,
        "golden_set_path": args.golden_set,
        "question_count": len(golden_questions),
        "dataset_composition": dataset_composition,
    }

    bootstrap_entries: list[dict] = []
    sprint20_decision: dict | None = None
    if args.bootstrap_a and args.bootstrap_b:
        results_by_label = {r["label"]: r for r in results}
        result_a = results_by_label.get(args.bootstrap_a)
        result_b = results_by_label.get(args.bootstrap_b)
        if result_a and result_a.get("supported") and result_b and result_b.get("supported"):
            bootstrap_entries = compute_bootstrap_report(
                result_a, result_b, golden_questions,
                seed=args.bootstrap_seed, iterations=args.bootstrap_iterations,
            )
            sprint20_decision = sprint20_production_decision(
                results_by_label, bootstrap_entries,
                small_label=args.bootstrap_a, large_label=args.bootstrap_b,
            )
            (output_dir / "bootstrap.json").write_text(
                json.dumps(bootstrap_entries, indent=2, ensure_ascii=False)
            )
            output["sprint20_decision"] = sprint20_decision
        else:
            print(
                f"Skipping bootstrap: {args.bootstrap_a!r} and/or {args.bootstrap_b!r} "
                "not supported/available in this run."
            )

    (output_dir / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    if bootstrap_entries and sprint20_decision:
        # A run that computed real bootstrap CIs must not carry Sprint
        # 19's "no bootstrap CIs were computed" caveat or its "68
        # question"/"Sprint 18" framing verbatim.
        report = render_markdown_report(
            results, decision, args.golden_set,
            title="Embedding Benchmark Sprint 20: Stability & Production Decision",
            dataset_note=f"{len(golden_questions)}-question golden set (Sprint 20 expansion)",
            statistical_caution=(
                f"{len(golden_questions)} questions is still a modest sample for a small "
                "quality gap between two close configs — paired bootstrap confidence "
                "intervals (see below) are the primary tool for judging whether an observed "
                "delta is distinguishable from noise at this size, rather than a fixed "
                "rule-of-thumb threshold."
            ),
        )
        report += render_sprint20_extra_section(bootstrap_entries, sprint20_decision)
    else:
        report = render_markdown_report(results, decision, args.golden_set)
    (output_dir / "report.md").write_text(report)

    print(report)
    print(f"\nWritten to {output_dir}/results.json and {output_dir}/report.md")
    if bootstrap_entries:
        print(f"Written to {output_dir}/bootstrap.json")

    if args.cleanup_work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark multiple embedding model/dimension configurations"
    )
    parser.add_argument(
        "--configs", nargs="+", default=DEFAULT_CONFIGS,
        help='"model@dimension" tokens, e.g. qwen3-4b@native qwen3-4b@1024',
    )
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cleanup-work-dir", action="store_true")
    parser.add_argument(
        "--bootstrap-a", default=None,
        help="Config label (e.g. qwen3-0.6b@768) to paired-bootstrap-compare as 'a'",
    )
    parser.add_argument(
        "--bootstrap-b", default=None,
        help="Config label (e.g. qwen3-4b@1024) to paired-bootstrap-compare as 'b'",
    )
    parser.add_argument("--bootstrap-seed", type=int, default=SPRINT20_BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap-iterations", type=int, default=SPRINT20_BOOTSTRAP_ITERATIONS)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
