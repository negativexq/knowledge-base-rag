# ruff: noqa: E501

"""Sprint 27: tokenizer-aware chunking benchmark.

Every configuration gets its own Qdrant collection and SQLite registry. The
active production alias/collection is never opened for writes. The benchmark
holds embedding, BM25, RRF, BGE reranking, ACL context, candidate count, and
the 220-question dataset constant while changing only chunking.

Run the full matrix with:

    python -m scripts.benchmark_chunking
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.bootstrap import paired_bootstrap_ci
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.ingestion.chunker import chunk_document
from app.ingestion.chunking_config import ChunkingConfig, config_for_name
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.ingestion.qdrant_store import QdrantStore
from app.ingestion.tokenizer import token_count
from app.llm.citation_location import location_for
from app.llm.embedding_models import qwen3_4b_config
from app.llm.ollama_client import OllamaClient
from app.llm.trust_boundary import serialize_untrusted_context
from app.registry.store import DocumentRegistry
from app.reranker.config import RERANKER_CANDIDATE_K, RERANKER_TOP_N
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import settings
from app.shared.slug import slugify
from scripts.benchmark_embeddings import SPRINT20_GOLDEN_SET, build_corpus

DEFAULT_OUTPUT = "artifacts/chunking-benchmark-sprint27"
DEFAULT_WORK_DIR = "artifacts/chunking-benchmark-sprint27/work"
CONFIG_NAMES = ("baseline", "256-32", "384-48", "512-64", "768-96")
DATASET_FINGERPRINT = "55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691"
BOOTSTRAP_SEED = 2701
BOOTSTRAP_ITERATIONS = 5000
CELLS = ("tr_query_tr_content", "en_query_en_content", "tr_query_en_content", "en_query_tr_content")
CROSS_CELLS = ("tr_query_en_content", "en_query_tr_content")
MONO_CELLS = ("tr_query_tr_content", "en_query_en_content")


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return round(ordered[index], 3)


def local_reranker_device() -> str:
    """Use an available local accelerator without changing the model."""
    override = os.getenv("SPRINT27_RERANKER_DEVICE")
    if override in {"cpu", "mps"}:
        return override
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


class CachedQueryEmbedder:
    """Reuse one real Qwen query embedding across all chunk collections."""

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors

    async def embed(self, query: str, **_kwargs) -> list[float]:
        return self._vectors[query]


async def prepare_query_embeddings(
    questions: list[dict],
) -> tuple[CachedQueryEmbedder, dict[str, float]]:
    config = qwen3_4b_config(settings)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    vectors: dict[str, list[float]] = {}
    timings: dict[str, float] = {}
    # The local Ollama build serves this 4B embedding model faster and more
    # predictably with one request per query than with a large /api/embed
    # batch. Keep the measured per-query latency visible in the artifact.
    for question in questions:
        started = time.perf_counter()
        vectors[question["query"]] = await ollama.embed(
            question["query"],
            model=config.ollama_model,
            prefix=config.query_prefix(),
            dimensions=config.output_dimension,
        )
        timings[question["id"]] = (time.perf_counter() - started) * 1000
    await ollama.aclose()
    return CachedQueryEmbedder(vectors), timings


def locations(results) -> list[Location]:
    return [
        (result.payload["source_type"], result.payload["source_id"], location_for(result.payload))
        for result in results
    ]


def expected_rank(ranked: list[Location], expected: list[Location]) -> int | None:
    expected_set = set(expected)
    for rank, location in enumerate(ranked, start=1):
        if location in expected_set:
            return rank
    return None


def classify_case(before: int | None, after: int | None) -> str:
    if after is None:
        return "dropped_out_of_top5"
    if before is None or before > 5:
        return "rescued"
    if after < before:
        return "improved"
    if after > before:
        return "degraded"
    return "unchanged"


def metric_dict(metrics) -> dict[str, float]:
    return {
        "recall_at_1": metrics.recall_at_1,
        "recall_at_3": metrics.recall_at_3,
        "recall_at_5": metrics.recall_at_5,
        "mrr": metrics.reciprocal_rank,
        "ndcg_at_5": metrics.ndcg_at_5,
    }


def _chunk_files(work_dir: Path, config: ChunkingConfig) -> tuple[list, float]:
    docs_dir = work_dir / "corpus"
    started = time.perf_counter()
    chunks = []
    for path in sorted(docs_dir.iterdir()):
        source_id = slugify(path.name)
        if path.suffix == ".pdf":
            chunks.extend(
                chunk_document(str(path), source_id, "filesystem", chunking_config=config)
            )
        elif path.suffix == ".md":
            chunks.extend(
                chunk_markdown_document(str(path), source_id, "filesystem", chunking_config=config)
            )
    return chunks, time.perf_counter() - started


def _measure_storage(collection: str) -> int | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "kb-rag-qdrant",
                "du",
                "-sk",
                f"/qdrant/storage/collections/{collection}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.split()[0]) * 1024
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def _scroll_payloads(qdrant: QdrantClient, collection: str) -> list[dict]:
    payloads: list[dict] = []
    offset = None
    while True:
        points, offset = qdrant.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        payloads.extend(point.payload or {} for point in points)
        if offset is None:
            return payloads


def payload_signature(qdrant: QdrantClient, collection: str) -> str:
    """Hash chunk text and citation identity, excluding vector scores."""
    rows = [
        {
            "source_type": payload.get("source_type"),
            "source_id": payload.get("source_id"),
            "location": location_for(payload),
            "char_range": payload.get("char_range"),
            "text": payload.get("text", ""),
        }
        for payload in _scroll_payloads(qdrant, collection)
    ]
    canonical = json.dumps(sorted(rows, key=lambda row: str(row)), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def chunk_stats(payloads: list[dict], config: ChunkingConfig) -> dict:
    counts = [
        int(payload["token_count"])
        if isinstance(payload.get("token_count"), int)
        else token_count(payload.get("text", ""), config.tokenizer_model, config.tokenizer_revision)
        for payload in payloads
    ]
    by_doc: dict[str, int] = defaultdict(int)
    for payload in payloads:
        by_doc[payload.get("source_id", "unknown")] += 1
    measured_overlap = [
        payload.get("overlap_token_count")
        for payload in payloads
        if isinstance(payload.get("overlap_token_count"), int)
    ]
    flags = {
        key: [payload.get(key) for payload in payloads if isinstance(payload.get(key), bool)]
        for key in ("sentence_split", "heading_preserved", "page_crossing")
    }
    hard_violations = (
        sum(count > config.hard_max_tokens for count in counts)
        if config.hard_max_tokens is not None
        else "not enforced"
    )
    return {
        "total_chunks": len(payloads),
        "avg_tokens_per_chunk": round(sum(counts) / len(counts), 3) if counts else None,
        "median_tokens_per_chunk": sorted(counts)[len(counts) // 2] if counts else None,
        "p95_tokens_per_chunk": percentile(counts, 95),
        "max_tokens_per_chunk": max(counts) if counts else None,
        "chunks_per_document": round(sum(by_doc.values()) / len(by_doc), 3) if by_doc else None,
        "chunks_by_document": dict(sorted(by_doc.items())),
        "overlap_ratio": (
            round(sum(measured_overlap) / sum(counts), 4)
            if measured_overlap and counts and len(measured_overlap) == len(counts)
            else "not measured"
        ),
        "chunks_exceeding_hard_max": hard_violations,
        "boundary": {
            "sentence_split_rate": (
                round(sum(flags["sentence_split"]) / len(flags["sentence_split"]), 4)
                if flags["sentence_split"]
                else "not measured"
            ),
            "heading_preservation_rate": (
                round(sum(flags["heading_preserved"]) / len(flags["heading_preserved"]), 4)
                if flags["heading_preserved"]
                else "not measured"
            ),
            "page_crossing_rate": (
                round(sum(flags["page_crossing"]) / len(flags["page_crossing"]), 4)
                if flags["page_crossing"]
                else "not measured"
            ),
        },
    }


def _context_metrics(results, question: dict, config: ChunkingConfig) -> dict:
    raw_tokens = []
    serialized_tokens = []
    relevant_tokens = []
    overlap_tokens = 0
    expected = set(tuple(location) for location in question.get("expected_locations", []))
    for result in results:
        text = result.payload.get("text", "")
        raw_tokens.append(token_count(text, config.tokenizer_model, config.tokenizer_revision))
        if (
            result.payload.get("source_type"),
            result.payload.get("source_id"),
            location_for(result.payload),
        ) in expected:
            relevant_tokens.append(raw_tokens[-1])
    serialized = serialize_untrusted_context(results)
    serialized_tokens.append(
        token_count(serialized, config.tokenizer_model, config.tokenizer_revision)
    )
    for left, right in zip(results, results[1:]):
        if left.payload.get("source_id") != right.payload.get("source_id"):
            continue
        left_range = left.payload.get("char_range") or [0, 0]
        right_range = right.payload.get("char_range") or [0, 0]
        if right_range[0] < left_range[1] and isinstance(
            right.payload.get("overlap_token_count"), int
        ):
            overlap_tokens += right.payload["overlap_token_count"]
    return {
        "raw_context_tokens": sum(raw_tokens),
        "serialized_context_tokens": serialized_tokens[0],
        "envelope_overhead_percent": round(
            (serialized_tokens[0] - sum(raw_tokens)) / max(sum(raw_tokens), 1) * 100, 3
        ),
        "relevant_context_tokens": sum(relevant_tokens) if relevant_tokens else 0,
        "duplicate_overlap_tokens": overlap_tokens,
        "duplicate_overlap_ratio": round(overlap_tokens / max(sum(raw_tokens), 1), 4),
        "citation_precision_proxy": "not measured (dataset has no exact evidence spans)",
    }


def _aggregate(cases: list[dict]) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    per_cell: dict[str, list] = defaultdict(list)
    all_metrics = []
    per_question = {}
    for case in cases:
        if case["expect_not_found"]:
            continue
        metrics = compute_rank_metrics(case["ranked_locations"], case["expected_locations"])
        all_metrics.append(metrics)
        per_cell[case["cell"]].append(metrics)
        per_question[case["query_id"]] = metric_dict(metrics)
    by_cell = {
        cell: aggregate_rank_metrics(per_cell[cell]) | {"question_count": len(per_cell[cell])}
        for cell in CELLS
    }
    return (
        aggregate_rank_metrics(all_metrics) | {"question_count": len(all_metrics)},
        by_cell,
        per_question,
    )


async def ensure_index(
    qdrant: QdrantClient,
    config: ChunkingConfig,
    work_dir: Path,
    rebuild: bool,
) -> dict:
    collection = f"kb_chunk_benchmark_{config.name.replace('-', '_')}"
    docs_dir = work_dir / config.name / "corpus"
    build_corpus(docs_dir)
    chunks, chunking_seconds = _chunk_files(work_dir / config.name, config)
    if qdrant.collection_exists(collection) and not rebuild:
        info = qdrant.get_collection(collection)
        if info.points_count:
            return {
                "collection": collection,
                "reused": True,
                "points": info.points_count,
                "chunking_seconds": round(chunking_seconds, 3),
                "chunks": chunks,
            }
        qdrant.delete_collection(collection)
    if qdrant.collection_exists(collection):
        qdrant.delete_collection(collection)
    registry_path = work_dir / config.name / "registry.db"
    if registry_path.exists():
        registry_path.unlink()
    embed_config = qwen3_4b_config(settings)
    store = QdrantStore(qdrant, collection, dense_dimension=embed_config.dimension)
    registry = DocumentRegistry(registry_path)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()

    async def embed(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    started = time.perf_counter()
    stats = await ingest_connector(
        LocalFilesystemConnector(str(docs_dir)),
        store,
        registry,
        embed,
        sparse,
        pipeline_fingerprint=build_pipeline_fingerprint(embed_config, config),
        chunking_config=config,
    )
    ingest_seconds = time.perf_counter() - started
    await ollama.aclose()
    return {
        "collection": collection,
        "reused": False,
        "points": stats.chunks_upserted,
        "chunking_seconds": round(chunking_seconds, 3),
        "ingest_seconds": round(ingest_seconds, 3),
        "chunks_per_second_end_to_end": round(
            stats.chunks_upserted / max(ingest_seconds, 0.001), 3
        ),
        "chunks": chunks,
    }


async def run_config(
    config: ChunkingConfig,
    questions: list[dict],
    qdrant: QdrantClient,
    index: dict,
    reranker: CrossEncoderReranker,
    query_embedder: CachedQueryEmbedder,
    query_embed_ms: dict[str, float],
) -> tuple[dict, list[dict]]:
    embed_config = qwen3_4b_config(settings)
    sparse = SparseEncoder()
    rerank_times: list[float] = []
    total_times: list[float] = []
    cases: list[dict] = []
    retrieval_records: list[tuple[dict, list, list[Location], list[Location], float]] = []
    for question in questions:
        expected = [tuple(location) for location in question.get("expected_locations", [])]
        started = time.perf_counter()
        candidates = await search(
            question["query"],
            query_embedder,
            sparse,
            qdrant,
            index["collection"],
            embed_config.ollama_model,
            RetrievalContext.system(),
            reranker=None,
            top_k=RERANKER_CANDIDATE_K,
            top_n=RERANKER_CANDIDATE_K,
            query_prefix=embed_config.query_prefix(),
            dimensions=embed_config.output_dimension,
        )
        before_locations = locations(candidates)
        retrieval_records.append(
            (
                question,
                candidates,
                before_locations,
                expected,
                (time.perf_counter() - started) * 1000,
            )
        )
    ranked_requests, amortized_rerank_ms = reranker.rerank_batch_with_amortized_timing(
        [(record[0]["query"], record[1]) for record in retrieval_records],
        top_n=RERANKER_TOP_N,
    )
    latency_sample_requests = [
        (record[0]["query"], record[1]) for record in retrieval_records[:20]
    ]
    if reranker.device == "mps":
        _sampled_ranked, sampled_rerank_ms = reranker.rerank_batch_with_amortized_timing(
            latency_sample_requests,
            top_n=RERANKER_TOP_N,
        )
        sampled_rerank_times = [sampled_rerank_ms] * len(latency_sample_requests)
    else:
        _sampled_ranked, sampled_rerank_times = reranker.rerank_many_with_timings(
            latency_sample_requests,
            top_n=RERANKER_TOP_N,
        )
    rerank_times = [amortized_rerank_ms] * len(retrieval_records)
    for record_index, (record, ranked) in enumerate(zip(retrieval_records, ranked_requests)):
        question, candidates, before_locations, expected, retrieval_ms = record
        total_ms = retrieval_ms + rerank_times[record_index] + query_embed_ms[question["id"]]
        total_times.append(total_ms)
        after_locations = locations(ranked)
        before = expected_rank(before_locations, expected)
        after = expected_rank(after_locations, expected)
        cases.append(
            {
                "query_id": question["id"],
                "pair": question.get("content_lang"),
                "cell": f"{question.get('query_lang')}_query_{question.get('content_lang')}_content",
                "expected": expected,
                "rank_before": before,
                "rank_after": after,
                "classification": classify_case(before, after),
                "candidate_count_before": len(candidates),
                "ranked_locations": after_locations,
                "expected_locations": expected,
                "expect_not_found": question.get("expect_not_found", False),
                "context": _context_metrics(ranked, question, config),
                "rerank_ms": round(rerank_times[record_index], 3),
                "total_retrieval_ms": round(total_ms, 3),
            }
        )
    overall, by_cell, per_question = _aggregate(cases)
    measured = [case for case in cases if not case["expect_not_found"]]
    classifications = [case["classification"] for case in measured]
    eligible_before = [
        case for case in measured if case["rank_before"] is not None and case["rank_before"] <= 5
    ]
    rescue_pool = [
        case for case in measured if case["rank_before"] is None or case["rank_before"] > 5
    ]
    drop_count = sum(1 for case in eligible_before if case["rank_after"] is None)
    context = [case["context"] for case in cases]
    return (
        {
            "config": config.name,
            "chunking": config.as_dict(),
            "embedding_control": "Qwen3-Embedding-4B@1024 + BM25 sparse + RRF",
            "reranker_control": "BAAI/bge-reranker-v2-m3 · sentence-transformers · CPU",
            "overall": overall,
            "by_cell": by_cell,
            "cross_lingual": {
                key: sum(by_cell[cell][key] for cell in CROSS_CELLS) / len(CROSS_CELLS)
                for key in ("recall_at_5", "mrr", "ndcg_at_5")
            },
            "mono_lingual": {
                key: sum(by_cell[cell][key] for cell in MONO_CELLS) / len(MONO_CELLS)
                for key in ("recall_at_5", "mrr", "ndcg_at_5")
            },
            "chunk_stats": chunk_stats(_scroll_payloads(qdrant, index["collection"]), config),
            "context_efficiency": {
                "avg_top5_context_tokens": round(
                    sum(item["raw_context_tokens"] for item in context) / len(context), 3
                ),
                "p95_top5_context_tokens": percentile(
                    [item["raw_context_tokens"] for item in context], 95
                ),
                "avg_serialized_context_tokens": round(
                    sum(item["serialized_context_tokens"] for item in context) / len(context), 3
                ),
                "avg_envelope_overhead_percent": round(
                    sum(item["envelope_overhead_percent"] for item in context) / len(context), 3
                ),
                "avg_relevant_context_tokens": round(
                    sum(item["relevant_context_tokens"] for item in context) / len(context), 3
                ),
                "avg_duplicate_overlap_tokens": round(
                    sum(item["duplicate_overlap_tokens"] for item in context) / len(context), 3
                ),
                "avg_duplicate_overlap_ratio": round(
                    sum(item["duplicate_overlap_ratio"] for item in context) / len(context), 4
                ),
                "citation_precision_proxy": "not measured (dataset has no exact evidence spans)",
            },
            "latency": {
                "retrieval_p50_ms": percentile(total_times, 50),
                "retrieval_p95_ms": percentile(total_times, 95),
                "query_embedding_p50_ms": percentile(list(query_embed_ms.values()), 50),
                "query_embedding_p95_ms": percentile(list(query_embed_ms.values()), 95),
                "rerank_p50_ms": percentile(sampled_rerank_times, 50),
                "rerank_p95_ms": percentile(sampled_rerank_times, 95),
                "rerank_latency_sample_p50_ms": percentile(sampled_rerank_times, 50),
                "rerank_latency_sample_p95_ms": percentile(sampled_rerank_times, 95),
                "rerank_batch_amortized_ms": round(amortized_rerank_ms, 3),
                "rerank_latency_sample_count": len(sampled_rerank_times),
                "query_throughput_qps": round(1000 / (sum(total_times) / len(total_times)), 3),
                "model_load_time": "shared benchmark load",
                "cpu_gpu": reranker.device or "cpu",
                "memory_vram": "not measured",
            },
            "indexing": {
                "chunking_seconds": index.get("chunking_seconds"),
                "end_to_end_ingest_seconds": index.get(
                    "ingest_seconds", "not measured (reused index)"
                ),
                "chunks_per_second": index.get(
                    "chunks_per_second_end_to_end", "not measured (reused index)"
                ),
                "storage_bytes": _measure_storage(index["collection"]),
            },
            "rescue_drop": {
                "reranker_rescue_rate": (
                    sum(
                        1
                        for case in rescue_pool
                        if case["rank_after"] is not None and case["rank_after"] <= 5
                    )
                    / len(rescue_pool)
                    if rescue_pool
                    else None
                ),
                "reranker_drop_rate": drop_count / len(eligible_before)
                if eligible_before
                else None,
                "classification_counts": {
                    label: classifications.count(label)
                    for label in (
                        "improved",
                        "rescued",
                        "unchanged",
                        "degraded",
                        "dropped_out_of_top5",
                    )
                },
            },
            "per_question": per_question,
        },
        cases,
    )


def paired_comparison(
    results: dict[str, dict], cases_by_config: dict[str, list[dict]], seed: int, iterations: int
) -> dict:
    metric_names = ("recall_at_5", "mrr", "ndcg_at_5")
    comparisons = {}
    pairs = [("baseline", name) for name in CONFIG_NAMES[1:]]
    for left, right in pairs:
        left_questions = results[left]["per_question"]
        right_questions = results[right]["per_question"]
        ids = sorted(set(left_questions) & set(right_questions))
        comparisons[f"{left}_vs_{right}"] = {}
        for metric in metric_names:
            ci = paired_bootstrap_ci(
                [left_questions[query_id][metric] for query_id in ids],
                [right_questions[query_id][metric] for query_id in ids],
                metric,
                "overall",
                seed,
                iterations=iterations,
            )
            comparisons[f"{left}_vs_{right}"][metric] = {
                "delta_baseline_minus_candidate": ci.observed_delta,
                "lower": ci.lower,
                "upper": ci.upper,
                "seed": seed,
                "iterations": iterations,
                "question_count": len(ids),
            }
    return comparisons


def report_markdown(payload: dict, paired: dict) -> str:
    lines = [
        "# Sprint 27 — Token-aware chunking benchmark",
        "",
        "Decision rule was fixed before running the benchmark: quality must stay within the baseline floor (Recall@5 -0.01, cross-lingual Recall@5 -0.01, MRR -0.02), hard-max violations must be zero, and efficiency is a secondary preference. No weighted score is used.",
        "",
        f"Dataset: `{payload['dataset']}` · questions: {payload['question_count']} · historical fingerprint: `{payload['dataset_fingerprint']}`",
        "Controls: Qwen3-Embedding-4B@1024 · BM25 sparse · Qdrant RRF · BAAI/bge-reranker-v2-m3 · candidate 20 → top 5 · same corpus/parser/ACL.",
        "Hard-max rule: target + 64 tokens (320, 448, 576, 832) for token-aware candidates; the baseline has no enforced hard max.",
        "",
        "## Cross-lingual retrieval",
        "",
        "| Config | TR→EN R@5 | EN→TR R@5 | Cross MRR | Cross nDCG@5 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in payload["configs"]:
        result = payload["results"][name]
        cells = result["by_cell"]
        lines.append(
            f"| {name} | {cells['tr_query_en_content']['recall_at_5']:.4f} | {cells['en_query_tr_content']['recall_at_5']:.4f} | {result['cross_lingual']['mrr']:.4f} | {result['cross_lingual']['ndcg_at_5']:.4f} |"
        )
    lines += [
        "",
        "## Chunk/context efficiency",
        "",
        "| Config | chunks | avg tokens | p95 context tokens | envelope overhead | storage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in payload["configs"]:
        result = payload["results"][name]
        stats = result["chunk_stats"]
        context = result["context_efficiency"]
        lines.append(
            f"| {name} | {stats['total_chunks']} | {stats['avg_tokens_per_chunk']} | {context['p95_top5_context_tokens']} | {context['avg_envelope_overhead_percent']}% | {result['indexing']['storage_bytes'] or 'not measured'} |"
        )
    lines += [
        "",
        "## Paired bootstrap",
        "",
        f"Seed: `{payload['bootstrap_seed']}` · iterations: `{payload['bootstrap_iterations']}` · 95% CI · deltas are baseline minus candidate.",
        "",
    ]
    for pair, metrics in paired.items():
        lines.append(f"### {pair}")
        for metric, value in metrics.items():
            lines.append(
                f"- {metric}: Δ={value['delta_baseline_minus_candidate']:.5f}, CI [{value['lower']:.5f}, {value['upper']:.5f}]"
            )
    lines += [
        "",
        f"Production recommendation: **{payload['production_decision']['recommendation']}**",
        "",
        "This benchmark does not claim production-scale storage behavior for the tiny four-document fixture corpus. Qwen tokenizer/model and BGE reranker are served locally; reranker inference remains synchronous in the async retrieval path.",
        "",
    ]
    return "\n".join(lines)


async def main_async(args) -> None:
    dataset_path = Path(args.dataset)
    questions = json.loads(dataset_path.read_text(encoding="utf-8"))
    output = Path(args.output)
    work_dir = Path(args.work_dir)
    output.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    qdrant = QdrantClient(url=settings.qdrant_url)
    query_embedder, query_embed_ms = await prepare_query_embeddings(questions)
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        trust_remote_code=settings.reranker_trust_remote_code,
        device=local_reranker_device(),
    )
    configs = [config_for_name(name) for name in args.configs]
    results = {}
    cases_by_config = {}
    indexes = {}
    for config in configs:
        index_info = await ensure_index(qdrant, config, work_dir, args.rebuild_index)
        indexes[config.name] = {
            key: value for key, value in index_info.items() if key != "chunks"
        }
        partial_path = output / f"{config.name}.partial.json"
        cases_partial_path = output / f"{config.name}.cases.partial.json"
        if args.reuse_partials and partial_path.exists() and not args.rebuild_index:
            result = json.loads(partial_path.read_text(encoding="utf-8"))
            if result.get("config") != config.name:
                raise ValueError(f"partial artifact does not match config: {partial_path}")
            cases = (
                json.loads(cases_partial_path.read_text(encoding="utf-8"))
                if cases_partial_path.exists()
                else []
            )
            if not cases and args.reuse_equivalent and results:
                previous_name = list(results)[-1]
                if payload_signature(
                    qdrant, index_info["collection"]
                ) == payload_signature(qdrant, indexes[previous_name]["collection"]):
                    cases = list(cases_by_config[previous_name])
                    cases_partial_path.write_text(
                        json.dumps(cases, indent=2), encoding="utf-8"
                    )
            results[config.name] = result
            cases_by_config[config.name] = cases
            continue
        if args.reuse_equivalent and results:
            previous_name = list(results)[-1]
            previous_index = indexes[previous_name]
            current_signature = payload_signature(qdrant, index_info["collection"])
            previous_signature = payload_signature(qdrant, previous_index["collection"])
            if current_signature == previous_signature:
                equivalent = json.loads(json.dumps(results[previous_name]))
                equivalent["config"] = config.name
                equivalent["chunking"] = config.as_dict()
                equivalent["chunk_stats"] = chunk_stats(
                    _scroll_payloads(qdrant, index_info["collection"]), config
                )
                equivalent["indexing"] = {
                    "chunking_seconds": index_info.get("chunking_seconds"),
                    "end_to_end_ingest_seconds": index_info.get(
                        "ingest_seconds", "not measured (reused index)"
                    ),
                    "chunks_per_second": index_info.get(
                        "chunks_per_second_end_to_end", "not measured (reused index)"
                    ),
                    "storage_bytes": _measure_storage(index_info["collection"]),
                }
                equivalent["payload_signature"] = current_signature
                equivalent["evaluation_mode"] = "equivalent_payload_reuse"
                results[config.name] = equivalent
                cases_by_config[config.name] = list(cases_by_config[previous_name])
                partial_path.write_text(json.dumps(equivalent, indent=2), encoding="utf-8")
                cases_partial_path.write_text(
                    json.dumps(cases_by_config[config.name], indent=2), encoding="utf-8"
                )
                continue
        result, cases = await run_config(
            config, questions, qdrant, index_info, reranker, query_embedder, query_embed_ms
        )
        results[config.name] = result
        cases_by_config[config.name] = cases
        partial_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        cases_partial_path.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    baseline = results.get("baseline")
    recommendation = "NEED_MORE_DATA"
    eligible = []
    efficiency_dominance = {}
    if baseline:
        for name in args.configs:
            if name == "baseline":
                continue
            candidate = results[name]
            quality_ok = (
                candidate["overall"]["recall_at_5"] >= baseline["overall"]["recall_at_5"] - 0.01
                and candidate["cross_lingual"]["recall_at_5"]
                >= baseline["cross_lingual"]["recall_at_5"] - 0.01
                and candidate["overall"]["mrr"] >= baseline["overall"]["mrr"] - 0.02
                and candidate["chunk_stats"]["chunks_exceeding_hard_max"] == 0
            )
            baseline_efficiency = (
                baseline["context_efficiency"]["avg_top5_context_tokens"],
                baseline["chunk_stats"]["total_chunks"],
                baseline["indexing"].get("storage_bytes") or float("inf"),
            )
            candidate_efficiency = (
                candidate["context_efficiency"]["avg_top5_context_tokens"],
                candidate["chunk_stats"]["total_chunks"],
                candidate["indexing"].get("storage_bytes") or float("inf"),
            )
            dominates_baseline = all(
                current <= reference
                for current, reference in zip(candidate_efficiency, baseline_efficiency)
            ) and candidate_efficiency != baseline_efficiency
            efficiency_dominance[name] = {
                "quality_floor_passed": quality_ok,
                "baseline": baseline_efficiency,
                "candidate": candidate_efficiency,
                "candidate_dominates_baseline": dominates_baseline,
            }
            if quality_ok and dominates_baseline:
                eligible.append((candidate_efficiency, name))
        if eligible:
            recommendation = f"ADOPT_{min(eligible)[1].replace('-', '_')}"
        else:
            recommendation = "KEEP_CURRENT"
    payload = {
        "sprint": 27,
        "dataset": str(dataset_path),
        "dataset_fingerprint": DATASET_FINGERPRINT,
        "dataset_file_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "question_count": len(questions),
        "configs": list(args.configs),
        "controls": {
            "embedding": "qwen3-4b@1024",
            "sparse": "BM25",
            "fusion": "RRF",
            "reranker": settings.reranker_model,
            "candidate_k": RERANKER_CANDIDATE_K,
            "top_n": RERANKER_TOP_N,
        },
        "indexes": indexes,
        "bootstrap_seed": args.bootstrap_seed,
        "bootstrap_iterations": args.bootstrap_iterations,
        "results": results,
        "production_decision": {
            "recommendation": recommendation,
            "rule": "Quality floor first: overall Recall@5 >= baseline -0.01, cross Recall@5 >= baseline -0.01, MRR >= baseline -0.02, zero hard-max violations; a candidate must then Pareto-dominate baseline on context tokens, chunk count, or storage before adoption.",
            "efficiency_comparison": efficiency_dominance,
        },
    }
    (output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    paired = paired_comparison(
        results, cases_by_config, args.bootstrap_seed, args.bootstrap_iterations
    )
    (output / "paired-comparison.json").write_text(json.dumps(paired, indent=2), encoding="utf-8")
    (output / "cases.json").write_text(
        json.dumps(
            [{"config": name, **case} for name, cases in cases_by_config.items() for case in cases],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output / "chunk-stats.json").write_text(
        json.dumps({name: result["chunk_stats"] for name, result in results.items()}, indent=2),
        encoding="utf-8",
    )
    (output / "report.md").write_text(report_markdown(payload, paired), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "configs": list(args.configs),
                "question_count": len(questions),
                "recommendation": recommendation,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark legacy and tokenizer-aware chunking")
    parser.add_argument("--configs", nargs="+", choices=CONFIG_NAMES, default=list(CONFIG_NAMES))
    parser.add_argument("--dataset", default=SPRINT20_GOLDEN_SET)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument(
        "--reuse-partials",
        action="store_true",
        help="reuse explicitly named completed *.partial.json results",
    )
    parser.add_argument(
        "--reuse-equivalent",
        action="store_true",
        help="reuse exact chunk-payload-equivalent configurations after hashing them",
    )
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
