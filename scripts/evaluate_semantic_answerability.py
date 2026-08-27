"""Evaluate Phase 6C semantic answerability in development shadow mode.

This command runs retrieval, server-owned ACL, reranking, and the two semantic
classifiers. It never invokes answer generation. Calibration and frozen-test
execution are explicit opt-ins; frozen test additionally requires its
dedicated dangerous flag.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.index_validation import validate_evaluation_index
from app.evaluation.semantic_answerability import (
    AMBIGUITY_PROMPT_VERSION,
    SUFFICIENCY_PROMPT_VERSION,
    OllamaSemanticEvaluator,
)
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.report import RetrievalReport
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DEFAULT_DATASET = CORPUS_DIR / "golden-dataset-v2.json"
DEFAULT_FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
DEFAULT_MANIFEST = CORPUS_DIR / "corpus-manifest.json"
DEFAULT_INDEX_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"
DEFAULT_OUTPUT = ROOT / "artifacts/phase-6/semantic-answerability/development.jsonl"
REFERENCE_CANDIDATE_K = 20
TOP_N = 5


def load_questions(
    path: Path, split: str, allow_calibration: bool, allow_frozen_test: bool
) -> list[dict]:
    if split == "calibration" and not allow_calibration:
        raise ValueError("calibration requires --allow-calibration")
    if split == "frozen_test" and not allow_frozen_test:
        raise ValueError("frozen_test requires --allow-frozen-test")
    questions = json.loads(path.read_text(encoding="utf-8"))
    selected = sorted((q for q in questions if q["split"] == split), key=lambda q: q["id"])
    if not selected:
        raise ValueError(f"dataset contains no questions in split {split!r}")
    return selected


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_ids(chunks: list) -> list[str]:
    return list(
        dict.fromkeys(str(c.payload.get("source_id")) for c in chunks if c.payload.get("source_id"))
    )


def _expected_sources(question: dict) -> list[str]:
    return list(question.get("required_evidence") or question.get("expected_source_ids") or [])


def _gold_present(question: dict, chunks: list) -> tuple[bool, bool]:
    actual = set(_source_ids(chunks))
    required = set(_expected_sources(question))
    return bool(actual & required), required.issubset(actual) if required else False


def _record(question: dict, report: RetrievalReport, chunks: list, semantic: Any) -> dict:
    any_present, all_present = _gold_present(question, chunks)
    semantic_data = semantic.as_dict()
    return {
        "query_id": question["id"],
        "case_family": question["case_family"],
        "category": question["category"],
        "split": question["split"],
        "tenant": question["tenant_id"],
        "ground_truth_label": question["answerability"],
        "query_language": question["query_language"],
        "evidence_language": question["evidence_language"],
        "language_pair": question["language_pair"],
        "expected_source_ids": question.get("expected_source_ids", []),
        "required_source_ids": _expected_sources(question),
        "gold_present": all_present,
        "any_gold_present": any_present,
        "top_authorized_source_ids": _source_ids(chunks),
        "deterministic_reason": semantic.deterministic_reason,
        "ambiguity_decision": (semantic_data.get("ambiguity") or {}).get("decision"),
        "missing_constraints": (semantic_data.get("ambiguity") or {}).get(
            "missing_constraints", []
        ),
        "sufficiency_decision": (semantic_data.get("sufficiency") or {}).get("decision"),
        "supporting_chunk_ids": (semantic_data.get("sufficiency") or {}).get(
            "supporting_chunk_ids", []
        ),
        "missing_information": (semantic_data.get("sufficiency") or {}).get(
            "missing_information", []
        ),
        "shadow_action": semantic.shadow_action,
        "parse_error": semantic.parse_error,
        "error_code": semantic.error_code,
        "latency_ms": semantic.latency_ms,
        "ambiguity_latency_ms": semantic.ambiguity_latency_ms,
        "sufficiency_latency_ms": semantic.sufficiency_latency_ms,
        "prompt_versions": {
            "ambiguity": AMBIGUITY_PROMPT_VERSION,
            "sufficiency": SUFFICIENCY_PROMPT_VERSION,
        },
        "retrieval": {
            "pre_acl_candidate_count": report.pre_acl_candidate_count,
            "authorized_candidate_count": report.authorized_candidate_count,
            "reranked_count": len(chunks),
        },
    }


def _classification_metrics(expected: list[str], actual: list[str], positive: str) -> dict:
    pairs = zip(expected, actual, strict=True)
    tp = sum(
        expected_value == positive and actual_value == positive
        for expected_value, actual_value in pairs
    )
    pairs = zip(expected, actual, strict=True)
    fp = sum(
        expected_value != positive and actual_value == positive
        for expected_value, actual_value in pairs
    )
    pairs = zip(expected, actual, strict=True)
    fn = sum(
        expected_value == positive and actual_value != positive
        for expected_value, actual_value in pairs
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(expected),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _latency(records: list[dict], key: str = "latency_ms") -> dict:
    values = sorted(float(r[key]) for r in records if r.get(key) is not None)
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {
        "n": len(values),
        "p50": median(values),
        "p95": values[round(0.95 * (len(values) - 1))],
        "max": max(values),
    }


def _slice_summary(records: list[dict]) -> dict:
    expected_action = {
        "answerable": "ANSWER",
        "ambiguous": "CLARIFY",
        "unanswerable": "ABSTAIN",
    }
    result = {}
    for dimension in ("category", "query_language", "evidence_language", "language_pair", "tenant"):
        groups: dict[str, list[dict]] = {}
        for record in records:
            groups.setdefault(str(record.get(dimension)), []).append(record)
        result[dimension] = {}
        for group, selected in sorted(groups.items()):
            false_answer = sum(
                r["shadow_action"] == "ANSWER"
                and r["ground_truth_label"] in {"unanswerable", "ambiguous"}
                for r in selected
            )
            result[dimension][group] = {
                "n": len(selected),
                "ANSWER": sum(r["shadow_action"] == "ANSWER" for r in selected),
                "CLARIFY": sum(r["shadow_action"] == "CLARIFY" for r in selected),
                "ABSTAIN": sum(r["shadow_action"] == "ABSTAIN" for r in selected),
                "false_answer": false_answer,
                "false_abstain": sum(
                    expected_action.get(r["ground_truth_label"]) == "ANSWER"
                    and r["shadow_action"] == "ABSTAIN"
                    for r in selected
                ),
            }
    return result


def build_summary(
    records: list[dict],
    questions: list[dict],
    settings: Settings,
    fingerprints: dict,
    collection: str,
    index_validation: dict,
) -> dict:
    labels = Counter(r["ground_truth_label"] for r in records)
    expected_answer = {r["query_id"] for r in records if r["ground_truth_label"] == "answerable"}
    actual_answer = {r["query_id"] for r in records if r["shadow_action"] == "ANSWER"}
    semantic_records = [r for r in records if not r["deterministic_reason"]]
    ambiguity_expected = [
        "AMBIGUOUS" if r["ground_truth_label"] == "ambiguous" else "CLEAR" for r in semantic_records
    ]
    ambiguity_actual = [r["ambiguity_decision"] for r in semantic_records]
    ambiguity_metrics = _classification_metrics(ambiguity_expected, ambiguity_actual, "AMBIGUOUS")
    sufficiency_records = [r for r in semantic_records if r["sufficiency_decision"] is not None]
    suff_expected = [
        "SUFFICIENT"
        if r["ground_truth_label"] == "answerable" and r["gold_present"]
        else "INSUFFICIENT"
        for r in sufficiency_records
    ]
    suff_actual = [r["sufficiency_decision"] for r in sufficiency_records]
    sufficiency_metrics = _classification_metrics(suff_expected, suff_actual, "SUFFICIENT")
    return {
        "schema_version": "phase-6c-semantic-answerability-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "split": questions[0]["split"],
        "query_count": len(records),
        "case_family_count": len({q["case_family"] for q in questions}),
        "config": {
            "runtime_profile": "BENCHMARK_REFERENCE",
            "embedding_model": active_embedding_config(settings).ollama_model,
            "embedding_dimension": active_embedding_config(settings).dimension,
            "retrieval_method": "BM25 + dense + RRF",
            "reranker_model": settings.reranker_model,
            "candidate_k": REFERENCE_CANDIDATE_K,
            "top_n": TOP_N,
            "collection": collection,
            "corpus_fingerprint": fingerprints["corpus_fingerprint"],
            "dataset_fingerprint": fingerprints["dataset_fingerprint"],
            "answerability_eval_model": settings.answerability_eval_model,
            "prompt_versions": {
                "ambiguity": AMBIGUITY_PROMPT_VERSION,
                "sufficiency": SUFFICIENCY_PROMPT_VERSION,
            },
            "generation_invoked": False,
        },
        "index_validation": index_validation,
        "label_counts": dict(labels),
        "semantic_evaluator_records": len(semantic_records),
        "semantic_evaluator_errors": sum(r["parse_error"] for r in records),
        "ambiguity_metrics": ambiguity_metrics if semantic_records else None,
        "sufficiency_metrics": sufficiency_metrics if sufficiency_records else None,
        "false_answer_count": len(
            actual_answer
            & (
                {
                    r["query_id"]
                    for r in records
                    if r["ground_truth_label"] in {"unanswerable", "ambiguous"}
                }
            )
        ),
        "false_abstain_count": len(expected_answer - actual_answer),
        "missed_ambiguity_count": sum(
            r["ground_truth_label"] == "ambiguous" and r["shadow_action"] != "CLARIFY"
            for r in records
        ),
        "false_clarify_count": sum(
            r["ground_truth_label"] == "answerable" and r["shadow_action"] == "CLARIFY"
            for r in records
        ),
        "gold_present_answerable": sum(
            r["ground_truth_label"] == "answerable" and r["gold_present"] for r in records
        ),
        "gold_present_answered": sum(
            r["ground_truth_label"] == "answerable"
            and r["gold_present"]
            and r["shadow_action"] == "ANSWER"
            for r in records
        ),
        "gold_present_answerable_coverage": (
            sum(
                r["ground_truth_label"] == "answerable"
                and r["gold_present"]
                and r["shadow_action"] == "ANSWER"
                for r in records
            )
            / sum(r["ground_truth_label"] == "answerable" and r["gold_present"] for r in records)
            if any(r["ground_truth_label"] == "answerable" and r["gold_present"] for r in records)
            else None
        ),
        "deterministic_reason_counts": dict(Counter(r["deterministic_reason"] for r in records)),
        "latency": {
            "ambiguity": _latency(records, "ambiguity_latency_ms"),
            "sufficiency": _latency(records, "sufficiency_latency_ms"),
            "total": _latency(records),
        },
        "slices": _slice_summary(records),
        "no_threshold_or_runtime_enforcement": True,
        "calibration_run": False,
        "frozen_test_used": False,
    }


def write_derived_artifacts(output: Path, records: list[dict], summary: dict) -> None:
    """Write bounded analysis files beside the selected JSONL export."""
    output.with_name("slice-results.json").write_text(
        json.dumps(summary["slices"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.with_name("latency.json").write_text(
        json.dumps(summary["latency"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors = [
        {
            "query_id": record["query_id"],
            "case_family": record["case_family"],
            "error_code": record["error_code"],
        }
        for record in records
        if record["parse_error"]
    ]
    output.with_name("error-analysis.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = (
        "# Phase 6C semantic answerability shadow export\n\n"
        f"- Split: `{summary['split']}`\n"
        f"- Queries: `{summary['query_count']}`\n"
        f"- Evaluator model: `{summary['config']['answerability_eval_model']}`\n"
        f"- Ambiguity prompt: `{AMBIGUITY_PROMPT_VERSION}`\n"
        f"- Sufficiency prompt: `{SUFFICIENCY_PROMPT_VERSION}`\n"
        f"- Parse/evaluator errors: `{summary['semantic_evaluator_errors']}`\n"
        "- Generation invoked: `NO`\n"
        "- Runtime gate enabled: `NO`\n\n"
        "This is a shadow observation only. No threshold or user-facing "
        "abstention decision was applied.\n"
    )
    output.with_name("report.md").write_text(report, encoding="utf-8")


async def evaluate(args: argparse.Namespace) -> dict:
    questions = load_questions(
        Path(args.dataset), args.split, args.allow_calibration, args.allow_frozen_test
    )
    if args.limit is not None:
        questions = questions[: args.limit]
    fingerprints = json.loads(Path(args.fingerprints).read_text(encoding="utf-8"))
    settings = Settings.benchmark_reference(
        ollama_base_url=args.ollama_url,
        **({"answerability_eval_model": args.evaluator_model} if args.evaluator_model else {}),
    )
    embedding = active_embedding_config(settings)
    collection = args.collection or f"kb_eval_phase55_{fingerprints['corpus_fingerprint'][:12]}"
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
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
    semantic = OllamaSemanticEvaluator(
        ollama,
        settings.answerability_eval_model,
        settings.answerability_eval_timeout_seconds,
        settings.answerability_eval_retries,
    )
    records = []
    try:
        for question in questions:
            report = RetrievalReport()
            chunks = await search(
                question["question"],
                ollama,
                sparse,
                qdrant,
                collection,
                embedding.ollama_model,
                RetrievalContext(tenant_id=question["tenant_id"]),
                reranker=reranker,
                top_k=REFERENCE_CANDIDATE_K,
                top_n=TOP_N,
                query_prefix=embedding.query_prefix(),
                dimensions=embedding.output_dimension,
                report=report,
            )
            phase6a = extract_answerability_observation(
                chunks,
                authorized_candidate_count=report.authorized_candidate_count,
                pre_acl_candidate_count=report.pre_acl_candidate_count,
            )
            semantic_observation = await semantic.evaluate(
                question["question"],
                chunks,
                deterministic_reason=phase6a.reason
                if phase6a.reason != "FEATURES_AVAILABLE"
                else None,
            )
            records.append(_record(question, report, chunks, semantic_observation))
    finally:
        await ollama.aclose()
        qdrant.close()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )
    summary = build_summary(
        records, questions, settings, fingerprints, collection, index_validation
    )
    summary_path = output.with_name(f"{output.stem}-summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_derived_artifacts(output, records, summary)
    return {"output": str(output), "summary": str(summary_path), "query_count": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fingerprints", type=Path, default=DEFAULT_FINGERPRINTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--index-validation", type=Path, default=DEFAULT_INDEX_VALIDATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--split", choices=("development", "calibration", "frozen_test"), default="development"
    )
    parser.add_argument("--allow-calibration", action="store_true")
    parser.add_argument("--allow-frozen-test", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--evaluator-model")
    parser.add_argument("--collection")
    parser.add_argument("--reranker-device", choices=("cpu", "mps"), default="cpu")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(evaluate(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
