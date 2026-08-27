"""Export Phase 6A answerability shadow features without generation.

The command uses the existing Qwen -> BM25/RRF -> ACL -> BGE path. It only
serializes metadata, raw feature values, and authorized source identities;
query text and document content are deliberately excluded.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.index_validation import validate_evaluation_index
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.filters import filter_authorized_candidates
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DEFAULT_DATASET = CORPUS_DIR / "golden-dataset-v2.json"
DEFAULT_FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
DEFAULT_MANIFEST = CORPUS_DIR / "corpus-manifest.json"
DEFAULT_INDEX_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"
DEFAULT_OUTPUT = ROOT / "artifacts/phase-6/answerability-features/development.jsonl"
REFERENCE_CANDIDATE_K = 20
TOP_N = 5
FEATURE_FIELDS = (
    "top1_score",
    "top1_top2_margin",
    "mean_top3_score",
    "distinct_source_count_top5",
    "dense_sparse_agreement",
    "authorized_candidate_count",
)


def load_questions(
    path: Path,
    split: str,
    allow_frozen_test: bool,
    allow_calibration: bool = False,
) -> list[dict]:
    if split == "frozen_test" and not allow_frozen_test:
        raise ValueError("frozen_test requires --allow-frozen-test and is never run by default")
    if split == "calibration" and not allow_calibration:
        raise ValueError("calibration requires explicit --allow-calibration")
    questions = json.loads(path.read_text(encoding="utf-8"))
    selected = [question for question in questions if question["split"] == split]
    if not selected:
        raise ValueError(f"dataset contains no questions in split {split!r}")
    return sorted(selected, key=lambda question: question["id"])


def select_questions(
    questions: list[dict], limit: int | None, sample_per_category: int | None
) -> list[dict]:
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


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _build_record(question: dict, observation: Any) -> dict[str, Any]:
    return {
        "query_id": question["id"],
        "case_family": question["case_family"],
        "split": question["split"],
        "category": question["category"],
        "tenant": question["tenant_id"],
        "answerability_label": question["answerability"],
        "query_language": question["query_language"],
        "evidence_language": question["evidence_language"],
        "language_pair": question["language_pair"],
        "expected_source_ids": question.get("expected_source_ids", []),
        "required_source_ids": question.get("required_evidence", []),
        "features": observation.features.as_dict(),
        "top_authorized_source_ids": observation.top_authorized_source_ids,
        "top_raw_reranker_scores": observation.top_raw_reranker_scores,
        "deterministic_reason": observation.reason,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "p95": None,
        }
    return {
        "n": len(values),
        "mean": round(mean(values), 6),
        "median": round(median(values), 6),
        "p25": round(_percentile(values, 0.25), 6),
        "p75": round(_percentile(values, 0.75), 6),
        "p90": round(_percentile(values, 0.90), 6),
        "p95": round(_percentile(values, 0.95), 6),
    }


def build_distributions(records: list[dict]) -> list[dict[str, Any]]:
    groups: list[tuple[str, str, list[dict]]] = [("answerability", "all", records)]
    for label in sorted({record["answerability_label"] for record in records}):
        groups.append(
            ("answerability", label, [r for r in records if r["answerability_label"] == label])
        )
    for category in sorted({record["category"] for record in records}):
        groups.append(("category", category, [r for r in records if r["category"] == category]))

    rows = []
    for dimension, group, selected in groups:
        for field in FEATURE_FIELDS:
            values = [
                record["features"].get(field)
                for record in selected
                if record["features"].get(field) is not None
            ]
            rows.append(
                {"dimension": dimension, "group": group, "feature": field, **_summary(values)}
            )
    return rows


def _config_snapshot(settings: Settings, fingerprints: dict[str, str], collection: str) -> dict:
    embedding = active_embedding_config(settings)
    return {
        "runtime_profile": "BENCHMARK_REFERENCE",
        "embedding_model": embedding.ollama_model,
        "embedding_dimension": embedding.dimension,
        "retrieval_method": "BM25 + dense + RRF",
        "rrf_prefetch_limit_per_branch": 20,
        "reranker_model": settings.reranker_model,
        "reranker_backend": settings.reranker_backend,
        "candidate_k": REFERENCE_CANDIDATE_K,
        "top_n": TOP_N,
        "collection": collection,
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "generation_invoked": False,
    }


def build_summary(
    records: list[dict],
    questions: list[dict],
    settings: Settings,
    fingerprints: dict[str, str],
    collection: str,
    index_validation: dict,
) -> dict:
    unavailable = [
        "top1_fused_rank",
        "top1_dense_rank",
        "top1_sparse_rank",
        "dense_sparse_agreement",
        "fused_rerank_agreement",
        "pre_acl_candidate_count",
    ]
    return {
        "schema_version": "phase-6a-answerability-shadow-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "split": questions[0]["split"],
        "query_count": len(records),
        "case_family_count": len({question["case_family"] for question in questions}),
        "config": _config_snapshot(settings, fingerprints, collection),
        "index_validation": index_validation,
        "answerability_counts": dict(Counter(record["answerability_label"] for record in records)),
        "reason_counts": dict(Counter(record["deterministic_reason"] for record in records)),
        "category_counts": dict(Counter(record["category"] for record in records)),
        "feature_unavailable": unavailable,
        "descriptive_only": True,
        "thresholds_or_calibration": False,
        "generation_invoked": False,
    }


async def export(args: argparse.Namespace) -> dict:
    if args.split == "calibration" and not args.allow_calibration:
        raise ValueError("calibration requires --allow-calibration")
    questions = select_questions(
        load_questions(
            Path(args.dataset),
            args.split,
            args.allow_frozen_test,
            args.allow_calibration,
        ),
        args.limit,
        args.sample_per_category,
    )
    fingerprints = json.loads(Path(args.fingerprints).read_text(encoding="utf-8"))
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    embedding = active_embedding_config(settings)
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
    collection = args.collection or f"kb_eval_phase55_{fingerprints['corpus_fingerprint'][:12]}"
    try:
        index_validation = validate_evaluation_index(
            qdrant,
            collection,
            Path(args.manifest),
            Path(args.index_validation),
            fingerprints["corpus_fingerprint"],
            expected_dimension=embedding.dimension,
        )
        ollama = OllamaClient(base_url=settings.ollama_base_url)
        sparse = SparseEncoder()
        reranker = CrossEncoderReranker(
            settings.reranker_model,
            device=args.reranker_device,
            max_concurrency=settings.reranker_max_concurrency,
        )
        records = []
        try:
            for question in questions:
                dense_vector = await ollama.embed(
                    question["question"],
                    model=embedding.ollama_model,
                    prefix=embedding.query_prefix(),
                    dimensions=embedding.output_dimension,
                )
                sparse_vector = sparse.embed_query(question["question"])
                context = RetrievalContext(tenant_id=question["tenant_id"])
                raw_candidates = hybrid_search(
                    qdrant,
                    collection,
                    dense_vector,
                    sparse_vector,
                    top_k=REFERENCE_CANDIDATE_K,
                    filters=None,
                )
                authorized = filter_authorized_candidates(raw_candidates, context)
                ranked = await reranker.async_rerank(
                    question["question"], authorized, TOP_N
                )
                observation = extract_answerability_observation(
                    ranked,
                    authorized_candidate_count=len(authorized),
                    pre_acl_candidate_count=len(raw_candidates),
                )
                records.append(_build_record(question, observation))
        finally:
            await ollama.aclose()

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        summary = build_summary(
            records, questions, settings, fingerprints, collection, index_validation
        )
        summary_path = output.with_name(f"{output.stem}-summary.json")
        distributions_path = output.with_name(f"{output.stem}-distributions.csv")
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rows = build_distributions(records)
        with distributions_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "dimension",
                    "group",
                    "feature",
                    "n",
                    "mean",
                    "median",
                    "p25",
                    "p75",
                    "p90",
                    "p95",
                ),
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        return {"output": str(output), "summary": str(summary_path), "query_count": len(records)}
    finally:
        qdrant.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fingerprints", type=Path, default=DEFAULT_FINGERPRINTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--index-validation", type=Path, default=DEFAULT_INDEX_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--split",
        choices=("development", "calibration", "frozen_test"),
        default="development",
    )
    parser.add_argument("--allow-calibration", action="store_true")
    parser.add_argument("--allow-frozen-test", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-per-category", type=int)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--collection")
    parser.add_argument("--reranker-device", choices=("cpu", "mps"), default="cpu")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(export(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
