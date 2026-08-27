# ruff: noqa: E501

"""Measure candidate-k trade-offs without changing retrieval semantics or data.

The command reads the committed Evaluation Corpus v2 labels and an existing
Qdrant collection. It never creates an index, calls a chat/generation
provider, or touches the frozen split unless two explicit flags are supplied.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.candidate_sweep import (
    SWEEP_CANDIDATE_K,
    TOP_N,
    aggregate_case_families,
    aggregate_query_records,
    classify_rescue_drop,
    post_rerank_metrics,
    pre_rerank_metrics,
    recommend_candidate_k,
    source_ids,
    summarize_latency,
    validate_candidate_k,
)
from app.evaluation.index_validation import validate_evaluation_index
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.filters import build_acl_filter
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DEFAULT_DATASET = DEFAULT_CORPUS_DIR / "golden-dataset-v2.json"
DEFAULT_FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
DEFAULT_OUTPUT = ROOT / "artifacts/phase-5-5"
DEFAULT_MANIFEST = DEFAULT_CORPUS_DIR / "corpus-manifest.json"
DEFAULT_INDEX_VALIDATION = DEFAULT_OUTPUT / "index-validation.json"


def _load_questions(path: Path, split: str, allow_frozen_test: bool) -> list[dict]:
    if split == "frozen_test" and not allow_frozen_test:
        raise ValueError("frozen_test requires --allow-frozen-test and is not run by default")
    questions = json.loads(path.read_text(encoding="utf-8"))
    selected = [question for question in questions if question["split"] == split]
    if not selected:
        raise ValueError(f"dataset contains no questions in split {split!r}")
    return sorted(selected, key=lambda question: question["id"])


def select_questions(
    questions: list[dict], limit: int | None = None, sample_per_category: int | None = None
) -> list[dict]:
    """Select a deterministic subset without random sampling or re-splitting."""
    if sample_per_category is not None:
        grouped: dict[str, list[dict]] = {}
        for question in questions:
            grouped.setdefault(question["category"], []).append(question)
        questions = [
            question
            for category in sorted(grouped)
            for question in grouped[category][:sample_per_category]
        ]
        questions.sort(key=lambda question: question["id"])
    if limit is not None:
        questions = questions[:limit]
    if not questions:
        raise ValueError("selection produced no questions")
    return questions


async def _retrieve_candidates(
    question: dict,
    candidate_k: int,
    settings: Settings,
    ollama: OllamaClient,
    sparse: SparseEncoder,
    qdrant: QdrantClient,
    collection: str,
    embedding_cache: dict[str, tuple[list[float], float]] | None = None,
) -> tuple[list, float]:
    embedding = active_embedding_config(settings)
    started = time.perf_counter()
    if embedding_cache is None:
        dense_vector = await ollama.embed(
            question["question"],
            model=embedding.ollama_model,
            prefix=embedding.query_prefix(),
            dimensions=embedding.output_dimension,
        )
        embedding_ms = 0.0
    else:
        dense_vector, embedding_ms = embedding_cache[question["id"]]
    sparse_vector = sparse.embed_query(question["question"])
    acl_filter = build_acl_filter(RetrievalContext(tenant_id=question["tenant_id"]))
    candidates = hybrid_search(
        qdrant,
        collection,
        dense_vector,
        sparse_vector,
        top_k=candidate_k,
        filters=acl_filter,
    )
    return candidates, (time.perf_counter() - started) * 1000 + embedding_ms


async def build_embedding_cache(
    questions: list[dict], settings: Settings
) -> dict[str, tuple[list[float], float]]:
    """Embed each query once so candidate-k remains the only sweep variable."""
    embedding = active_embedding_config(settings)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    cache: dict[str, tuple[list[float], float]] = {}
    try:
        for question in questions:
            started = time.perf_counter()
            vector = await ollama.embed(
                question["question"],
                model=embedding.ollama_model,
                prefix=embedding.query_prefix(),
                dimensions=embedding.output_dimension,
            )
            cache[question["id"]] = (vector, (time.perf_counter() - started) * 1000)
    finally:
        await ollama.aclose()
    return cache


async def run_candidate_k(
    questions: list[dict],
    candidate_k: int,
    settings: Settings,
    qdrant: QdrantClient,
    collection: str,
    reranker: Any,
    embedding_cache: dict[str, tuple[list[float], float]] | None = None,
) -> dict[str, Any]:
    validate_candidate_k(candidate_k, TOP_N)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()
    records: list[dict[str, Any]] = []
    retrieval_latencies: list[float] = []
    rerank_latencies: list[float] = []
    total_latencies: list[float] = []
    pairs_scored = 0
    try:
        for question in questions:
            started = time.perf_counter()
            candidates, retrieval_ms = await _retrieve_candidates(
                question,
                candidate_k,
                settings,
                ollama,
                sparse,
                qdrant,
                collection,
                embedding_cache,
            )
            candidate_ids = source_ids(candidates)
            expected_ids = question["expected_source_ids"]
            rerank_started = time.perf_counter()
            ranked = await asyncio.to_thread(
                reranker.rerank, question["question"], candidates, TOP_N
            )
            rerank_ms = (time.perf_counter() - rerank_started) * 1000
            ranked_ids = source_ids(ranked)
            pre = pre_rerank_metrics(candidate_ids, expected_ids)
            post = post_rerank_metrics(ranked_ids, expected_ids)
            records.append(
                {
                    "query_id": question["id"],
                    "case_family": question["case_family"],
                    "category": question["category"],
                    "query_language": question["query_language"],
                    "evidence_language": question["evidence_language"],
                    "language_pair": question["language_pair"],
                    "tenant_id": question["tenant_id"],
                    "answerability": question["answerability"],
                    "difficulty": question["difficulty"],
                    "expected_source_ids": expected_ids,
                    "candidate_source_ids": candidate_ids,
                    "ranked_source_ids": ranked_ids,
                    "candidate_count": len(candidates),
                    **pre,
                    **post,
                    "rescue_drop": classify_rescue_drop(
                        candidate_ids, ranked_ids, expected_ids, TOP_N
                    ),
                    "retrieval_ms": round(retrieval_ms, 3),
                    "rerank_ms": round(rerank_ms, 3),
                    "total_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            retrieval_latencies.append(retrieval_ms)
            rerank_latencies.append(rerank_ms)
            total_latencies.append(records[-1]["total_ms"])
            pairs_scored += len(candidates)
    finally:
        await ollama.aclose()

    eligible = [record for record in records if record["expected_source_ids"]]
    rescue_drop = {
        label: sum(record["rescue_drop"] == label for record in eligible)
        for label in ("rescued", "dropped", "unchanged")
    }
    total_rerank_seconds = sum(rerank_latencies) / 1000
    return {
        "candidate_k": candidate_k,
        "top_n": TOP_N,
        "query_count": len(records),
        "theoretical_pairs": len(questions) * candidate_k,
        "answerable_query_count": len(eligible),
        "query_level": aggregate_query_records(eligible),
        "case_family_level": aggregate_case_families(eligible),
        "rescue_drop": rescue_drop,
        "latency": {
            "retrieval": summarize_latency(retrieval_latencies),
            "reranker": summarize_latency(rerank_latencies),
            "total_pipeline": summarize_latency(total_latencies),
            "pairs_scored": pairs_scored,
            "pairs_per_second": round(pairs_scored / total_rerank_seconds, 3)
            if total_rerank_seconds
            else None,
        },
        "records": records,
    }


def _slice_metrics(records: list[dict], field: str) -> dict[str, dict[str, Any]]:
    values = sorted(
        {record[field] for record in records},
        key=lambda value: (value is None, "" if value is None else str(value)),
    )
    result = {}
    for value in values:
        subset = [record for record in records if record[field] == value]
        eligible = [record for record in subset if record["expected_source_ids"]]
        result["none" if value is None else str(value)] = {
            "query_count": len(subset),
            "answerable_query_count": len(eligible),
            "case_family_count": len({record["case_family"] for record in subset}),
            "query_level": aggregate_query_records(eligible),
        }
    return result


def _git_ref() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_payload(
    results: list[dict[str, Any]],
    questions: list[dict],
    settings: Settings,
    fingerprints: dict[str, str],
    split: str,
    collection: str,
    index_validation: dict[str, Any],
) -> dict[str, Any]:
    embedding = active_embedding_config(settings)
    return {
        "schema_version": "phase-5-5-candidate-sweep-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit_ref": _git_ref(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "split": split,
        "collection": collection,
        "index_validation": index_validation,
        "question_count": len(questions),
        "case_family_count": len({question["case_family"] for question in questions}),
        "config_snapshot": {
            "runtime_profile": "BENCHMARK_REFERENCE",
            "embedding_model": embedding.ollama_model,
            "embedding_dimension": embedding.output_dimension,
            "retrieval_method": "BM25 + dense + RRF",
            "reranker_model": settings.reranker_model,
            "reranker_backend": settings.reranker_backend,
            "reranker_max_concurrency": settings.reranker_max_concurrency,
            "top_n": TOP_N,
            "chunking_mode": settings.chunking_mode,
            "security_validation_mode": settings.security_validation_mode,
            "generation_invoked": False,
            "shared_query_embedding_cache": True,
        },
        "candidate_k_values": [result["candidate_k"] for result in results],
        "execution_order": [result["candidate_k"] for result in results],
        "results": results,
        "slice_dimensions": [
            "category",
            "query_language",
            "evidence_language",
            "language_pair",
            "tenant_id",
            "answerability",
            "difficulty",
        ],
        "slice_metrics": {
            field: {
                str(result["candidate_k"]): _slice_metrics(result["records"], field)
                for result in results
            }
            for field in (
                "category",
                "query_language",
                "evidence_language",
                "language_pair",
                "tenant_id",
                "answerability",
                "difficulty",
            )
        },
        "decision": "NOT ENOUGH EVIDENCE TO PROMOTE",
        "promotion_policy": "Comparison artifact only; candidate_k is never promoted automatically.",
        "recommendation": recommend_candidate_k(results, {
            field: {
                str(result["candidate_k"]): _slice_metrics(result["records"], field)
                for result in results
            }
            for field in ("category",)
        }),
    }


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = (
        "candidate_k",
        "pre_rerank_candidate_recall",
        "pre_rerank_any_required_evidence",
        "pre_rerank_all_required_evidence",
        "pre_rerank_recall_at_10",
        "pre_rerank_recall_at_15",
        "pre_rerank_recall_at_20",
        "post_rerank_recall_at_5",
        "mrr",
        "ndcg_at_5",
        "rerank_p50_ms",
        "rerank_p95_ms",
        "total_p95_ms",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for result in payload["results"]:
            query = result["query_level"]
            writer.writerow(
                {
                    "candidate_k": result["candidate_k"],
                    "pre_rerank_candidate_recall": query["candidate_recall"],
                    "pre_rerank_any_required_evidence": query["any_required_evidence"],
                    "pre_rerank_all_required_evidence": query["all_required_evidence"],
                    "pre_rerank_recall_at_10": query["recall_at_10"],
                    "pre_rerank_recall_at_15": query["recall_at_15"],
                    "pre_rerank_recall_at_20": query["recall_at_20"],
                    "post_rerank_recall_at_5": query["recall_at_5"],
                    "mrr": query["mrr"],
                    "ndcg_at_5": query["ndcg_at_5"],
                    "rerank_p50_ms": result["latency"]["reranker"]["p50_ms"],
                    "rerank_p95_ms": result["latency"]["reranker"]["p95_ms"],
                    "total_p95_ms": result["latency"]["total_pipeline"]["p95_ms"],
                }
            )


async def main_async(args: argparse.Namespace) -> None:
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    questions = _load_questions(Path(args.dataset), args.split, args.allow_frozen_test)
    questions = select_questions(questions, args.limit, args.sample_per_category)
    for candidate_k in args.candidate_k:
        validate_candidate_k(candidate_k, TOP_N)
        if candidate_k not in SWEEP_CANDIDATE_K:
            raise ValueError(f"candidate_k must be one of {SWEEP_CANDIDATE_K}")
    fingerprints = json.loads(Path(args.fingerprints).read_text(encoding="utf-8"))
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
    collection = args.collection or settings.qdrant_active_alias
    index_validation = validate_evaluation_index(
        qdrant,
        collection,
        Path(args.manifest),
        Path(args.index_validation),
        fingerprints["corpus_fingerprint"],
        expected_dimension=active_embedding_config(settings).dimension,
    )
    embedding_cache = await build_embedding_cache(questions, settings)
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        device=args.reranker_device,
        max_concurrency=settings.reranker_max_concurrency,
    )
    results = [
        await run_candidate_k(
            questions,
            candidate_k,
            settings,
            qdrant,
            collection,
            reranker,
            embedding_cache,
        )
        for candidate_k in args.candidate_k
    ]
    payload = build_payload(
        results, questions, settings, fingerprints, args.split, collection, index_validation
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "candidate-sweep.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(output / "candidate-sweep.csv", payload)
    print(json.dumps({"output": str(output), "question_count": len(questions)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep authorized reranker candidate_k values")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fingerprints", type=Path, default=DEFAULT_FINGERPRINTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--index-validation", type=Path, default=DEFAULT_INDEX_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split", choices=("development", "calibration", "frozen_test"), default="development")
    parser.add_argument("--allow-frozen-test", action="store_true")
    parser.add_argument("--candidate-k", nargs="+", type=int, default=list(SWEEP_CANDIDATE_K))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-per-category", type=int)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--collection")
    parser.add_argument("--reranker-device", choices=("cpu", "mps"), default="cpu")
    args = parser.parse_args()
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
