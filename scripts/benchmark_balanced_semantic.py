"""Cache-first balanced Phase 6C.2 semantic evaluator validation smoke."""

from __future__ import annotations

import argparse
import asyncio
import json
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
    SemanticAnswerabilityObservation,
)
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.report import RetrievalReport
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings
from scripts.benchmark_semantic_models import (
    _cache_record,
    _cached_chunks,
    _git_sha,
    retrieval_config,
    retrieval_config_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET = CORPUS_DIR / "golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
MANIFEST = CORPUS_DIR / "corpus-manifest.json"
INDEX_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"
PRIOR_FEATURES = ROOT / "artifacts/phase-6/answerability-features/development.jsonl"
OUTPUT_DIR = ROOT / "artifacts/phase-6/semantic-balanced-smoke"
COLLECTION_DEFAULT = "kb_eval_phase55_0175aa4a2f9b"
MODEL = "qwen3.5:4b"
REFERENCE_CANDIDATE_K = 20
TOP_N = 5

ANSWER_CATEGORY_QUOTAS = {
    "standard_answerable": 4,
    "hard_answerable": 4,
    "cross_lingual": 4,
    "multi_document": 3,
    "version_conflict": 3,
    "injection_bearing": 2,
}


def _load_questions(path: Path = DATASET) -> list[dict[str, Any]]:
    return sorted(
        [q for q in json.loads(path.read_text(encoding="utf-8")) if q["split"] == "development"],
        key=lambda q: q["id"],
    )


def _prior_gold_presence(path: Path = PRIOR_FEATURES) -> dict[str, bool]:
    """Use the existing Phase 6A retrieval observation only as a stable preference hint."""
    if not path.exists():
        return {}
    result: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        required = set(row.get("required_source_ids") or row.get("expected_source_ids") or [])
        actual = set(row.get("top_authorized_source_ids") or [])
        result[row["query_id"]] = bool(required) and required.issubset(actual)
    return result


def _rank_candidates(candidates: list[dict[str, Any]], hints: dict[str, bool]) -> list[dict]:
    return sorted(candidates, key=lambda q: (not hints.get(q["id"], False), q["id"]))


def _take_category(
    questions: list[dict],
    category: str,
    count: int,
    selected: dict[str, dict],
    hints: dict[str, bool],
) -> None:
    candidates = _rank_candidates(
        [q for q in questions if q["category"] == category and q["answerability"] == "answerable"],
        hints,
    )
    for question in candidates:
        if len([q for q in selected.values() if q["category"] == category]) >= count:
            break
        selected[question["id"]] = question


def select_balanced_questions(
    questions: list[dict[str, Any]],
    count: int = 48,
    prior_features: Path = PRIOR_FEATURES,
) -> list[dict[str, Any]]:
    """Select 20 answer, 16 abstain, and 12 clarify records deterministically."""
    hints = _prior_gold_presence(prior_features)
    selected: dict[str, dict] = {}
    for category, quota in ANSWER_CATEGORY_QUOTAS.items():
        _take_category(questions, category, quota, selected, hints)

    # Preserve both cross-language directions in the answer bucket where available.
    cross = [
        q
        for q in questions
        if q["category"] == "cross_lingual"
        and q["answerability"] == "answerable"
        and q["language_pair"] in {"tr->en", "en->tr"}
    ]
    for pair in ("tr->en", "en->tr"):
        for question in _rank_candidates([q for q in cross if q["language_pair"] == pair], hints)[
            :2
        ]:
            selected[question["id"]] = question

    # The directional guarantee can replace category-quota picks, never enlarge
    # the answer bucket beyond its 20-record budget.
    protected_cross_ids = {
        question["id"]
        for question in selected.values()
        if question["category"] == "cross_lingual"
        and question["language_pair"] in {"tr->en", "en->tr"}
    }
    while sum(question["answerability"] == "answerable" for question in selected.values()) > 20:
        removable = sorted(
            (
                question
                for question in selected.values()
                if question["answerability"] == "answerable"
                and question["id"] not in protected_cross_ids
            ),
            key=lambda question: question["id"],
            reverse=True,
        )
        if not removable:
            raise ValueError("could not keep balanced answer bucket within its budget")
        selected.pop(removable[0]["id"])

    # All development ambiguous records are useful here; there are twelve in the canonical set.
    for question in questions:
        if question["answerability"] == "ambiguous":
            selected[question["id"]] = question

    # Keep every ACL case separate from ordinary unanswerable negatives.
    abstain = [q for q in questions if q["category"] == "acl_negative"]
    abstain += [
        q
        for q in questions
        if q["answerability"] == "unanswerable" and q["category"] != "acl_negative"
    ]
    for question in sorted(abstain, key=lambda q: q["id"]):
        if (
            len(
                [
                    q
                    for q in selected.values()
                    if q["answerability"] == "unanswerable" and q["category"] != "ambiguous"
                ]
            )
            >= 16
        ):
            break
        selected[question["id"]] = question

    if len(selected) != count:
        raise ValueError(f"balanced selection expected {count} records, got {len(selected)}")
    return [selected[key] for key in sorted(selected)]


def behavioral_target(question: dict[str, Any], all_required_present: bool) -> str:
    if question["answerability"] == "ambiguous":
        return "SHOULD_CLARIFY"
    if question["answerability"] == "answerable":
        return "SHOULD_ANSWER" if all_required_present else "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL"
    return "SHOULD_ABSTAIN"


def _expected_action(target: str) -> str:
    return {
        "SHOULD_ANSWER": "ANSWER",
        "SHOULD_CLARIFY": "CLARIFY",
        "SHOULD_ABSTAIN": "ABSTAIN",
        "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL": "ABSTAIN",
    }[target]


def _safe_cache_metadata(
    fingerprints: dict, collection: str, query_ids: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": "phase-6c2-balanced-evaluator-input-cache-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config": retrieval_config(),
        "retrieval_config_fingerprint": retrieval_config_fingerprint(),
        "evaluator_model": MODEL,
        "prompt_versions": {
            "ambiguity": AMBIGUITY_PROMPT_VERSION,
            "sufficiency": SUFFICIENCY_PROMPT_VERSION,
        },
        "query_count": len(query_ids),
        "query_ids": query_ids,
        "selection": {
            "answer_target": 20,
            "abstain_target": 16,
            "clarify_target": 12,
            "selection_version": "balanced-development-v1",
        },
        "authorized_only": True,
        "generation_invoked": False,
    }


def validate_balanced_cache(metadata: dict, fingerprints: dict, collection: str) -> None:
    expected = {
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config_fingerprint": retrieval_config_fingerprint(),
        "evaluator_model": MODEL,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"balanced evaluator cache identity mismatch for {key}")
    if metadata.get("authorized_only") is not True:
        raise ValueError("balanced evaluator cache is not authorized-only")


async def build_cache(args: argparse.Namespace) -> dict[str, Any]:
    questions = select_balanced_questions(
        _load_questions(Path(args.dataset)), prior_features=Path(args.prior_features)
    )
    fingerprints = json.loads(Path(args.fingerprints).read_text(encoding="utf-8"))
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    embedding = active_embedding_config(settings)
    collection = args.collection or COLLECTION_DEFAULT
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
    validation = validate_evaluation_index(
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
        settings.reranker_model, device=args.reranker_device, max_concurrency=1
    )
    records: list[dict] = []
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
            record = _cache_record(question, report, chunks)
            record["behavioral_target"] = behavioral_target(
                question, record["all_required_present"]
            )
            record["deterministic_reason"] = (
                phase6a.reason if phase6a.reason != "FEATURES_AVAILABLE" else None
            )
            records.append(record)
    finally:
        await ollama.aclose()
        qdrant.close()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "query-set.json").write_text(
        json.dumps([r["query_id"] for r in records], indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "evaluator-inputs.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )
    metadata = _safe_cache_metadata(fingerprints, collection, [r["query_id"] for r in records])
    metadata["retrieval_calls_during_cache_build"] = len(records)
    metadata["behavioral_target_counts"] = dict(Counter(r["behavioral_target"] for r in records))
    metadata["category_counts"] = dict(Counter(r["category"] for r in records))
    metadata["language_pair_counts"] = dict(Counter(r["language_pair"] for r in records))
    metadata["index_validation"] = validation
    (output_dir / "cache-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def load_cache(
    output_dir: Path, fingerprints_path: Path, collection: str
) -> tuple[dict, list[dict]]:
    metadata = json.loads((output_dir / "cache-metadata.json").read_text(encoding="utf-8"))
    fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8"))
    validate_balanced_cache(metadata, fingerprints, collection)
    records = [
        json.loads(line)
        for line in (output_dir / "evaluator-inputs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if metadata["query_ids"] != [r["query_id"] for r in records]:
        raise ValueError("balanced cache query set does not match metadata")
    if len(records) != 48:
        raise ValueError("balanced cache must contain exactly 48 records")
    for record in records:
        _cached_chunks(record)
    return metadata, records


def _metric(expected: list[str], actual: list[str], positive: str) -> dict[str, Any]:
    tp = sum(e == positive and a == positive for e, a in zip(expected, actual, strict=True))
    fp = sum(e != positive and a == positive for e, a in zip(expected, actual, strict=True))
    fn = sum(e == positive and a != positive for e, a in zip(expected, actual, strict=True))
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


def _latency(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": median(ordered),
        "p95": ordered[round(0.95 * (len(ordered) - 1))],
        "max": max(ordered),
    }


def _category_slices(results: list[dict]) -> dict[str, dict[str, Any]]:
    slices: dict[str, dict[str, Any]] = {}
    for key in sorted(
        {
            "all",
            *(r["category"] for r in results),
            *(r["language_pair"] for r in results),
        }
    ):
        rows = (
            results
            if key == "all"
            else [r for r in results if r["category"] == key or r["language_pair"] == key]
        )
        expected = [_expected_action(r["behavioral_target"]) for r in rows]
        actual = [r["shadow_action"] for r in rows]
        slices[key] = {
            "n": len(rows),
            "answer": sum(a == "ANSWER" for a in actual),
            "clarify": sum(a == "CLARIFY" for a in actual),
            "abstain": sum(a == "ABSTAIN" for a in actual),
            "false_answer": sum(
                e != "ANSWER" and a == "ANSWER" for e, a in zip(expected, actual, strict=True)
            ),
            "false_clarify": sum(
                e != "CLARIFY" and a == "CLARIFY" for e, a in zip(expected, actual, strict=True)
            ),
            "false_abstain": sum(
                e == "ANSWER" and a == "ABSTAIN" for e, a in zip(expected, actual, strict=True)
            ),
        }
    return slices


async def evaluate_model(
    model: str,
    records: list[dict],
    client: OllamaClient,
    timeout_seconds: float = 30.0,
    retries: int = 1,
    ambiguity_prompt_version: str = AMBIGUITY_PROMPT_VERSION,
) -> tuple[dict[str, Any], list[dict]]:
    evaluator = OllamaSemanticEvaluator(
        client,
        model,
        timeout_seconds,
        retries,
        ambiguity_prompt_version=ambiguity_prompt_version,
    )
    results = []
    for record in records:
        acl_excluded = record["category"] == "acl_negative"
        if acl_excluded:
            # ACL-negative labels are an offline safety slice, not model-quality
            # supervision. Never send these records to the semantic evaluator.
            observation = SemanticAnswerabilityObservation(shadow_action="ABSTAIN")
        else:
            observation = await evaluator.evaluate(
                record["query"], _cached_chunks(record), record["deterministic_reason"]
            )
        row = {
            "query_id": record["query_id"],
            "case_family": record["case_family"],
            "category": record["category"],
            "behavioral_target": record["behavioral_target"],
            "ground_truth_label": record["ground_truth_label"],
            "query_language": record["query_language"],
            "evidence_language": record["evidence_language"],
            "language_pair": record["language_pair"],
            "gold_present": record["gold_present"],
            "all_required_present": record["all_required_present"],
            "deterministic_reason": record["deterministic_reason"],
            "semantic_evaluation_skipped": (
                "ACL_NEGATIVE_OFFLINE_SAFETY_SLICE" if acl_excluded else None
            ),
            **observation.as_dict(),
        }
        results.append(row)

    semantic_rows = [
        r for r in results if not r["deterministic_reason"] and not r["semantic_evaluation_skipped"]
    ]
    expected_ambiguity = [
        "AMBIGUOUS" if r["ground_truth_label"] == "ambiguous" else "CLEAR" for r in semantic_rows
    ]
    actual_ambiguity = [
        r["ambiguity"]["decision"] if r["ambiguity"] else "ERROR" for r in semantic_rows
    ]
    suff_rows = [r for r in semantic_rows if r["sufficiency"] is not None]
    expected_sufficiency = [
        "SUFFICIENT" if r["behavioral_target"] == "SHOULD_ANSWER" else "INSUFFICIENT"
        for r in suff_rows
    ]
    actual_sufficiency = [r["sufficiency"]["decision"] for r in suff_rows]
    expected_actions = [_expected_action(r["behavioral_target"]) for r in results]
    actual_actions = [r["shadow_action"] for r in results]
    gold_present = [r for r in results if r["behavioral_target"] == "SHOULD_ANSWER"]
    injection = [r for r in results if r["category"] == "injection_bearing"]
    multi_complete = [
        r for r in results if r["category"] == "multi_document" and r["all_required_present"]
    ]
    multi_partial = [
        r for r in results if r["category"] == "multi_document" and not r["all_required_present"]
    ]
    reliability = {
        "evaluator_calls": sum(r["evaluator_call_count"] for r in results),
        "ambiguity_calls": len(semantic_rows),
        "sufficiency_calls": len(suff_rows),
        "first_pass_schema_success": sum(r["first_pass_schema_success"] for r in results),
        "retry_count": sum(r["retry_count"] for r in results),
        "final_parse_failure_count": sum(r["parse_error"] for r in results),
        "timeout_count": sum(r["timeout_count"] for r in results),
        "invalid_enum_count": sum(r["invalid_enum_count"] for r in results),
        "hallucinated_supporting_chunk_id_count": sum(
            r["hallucinated_supporting_chunk_id_count"] for r in results
        ),
    }
    summary = {
        "model": model,
        "prompt_versions": {
            "ambiguity": ambiguity_prompt_version,
            "sufficiency": SUFFICIENCY_PROMPT_VERSION,
        },
        "query_count": len(results),
        "behavioral_targets": dict(Counter(r["behavioral_target"] for r in results)),
        "ambiguity": _metric(expected_ambiguity, actual_ambiguity, "AMBIGUOUS"),
        "sufficiency": _metric(expected_sufficiency, actual_sufficiency, "SUFFICIENT"),
        "combined": {
            "answer": sum(a == "ANSWER" for a in actual_actions),
            "clarify": sum(a == "CLARIFY" for a in actual_actions),
            "abstain": sum(a == "ABSTAIN" for a in actual_actions),
            "correct_answer": sum(
                e == "ANSWER" and a == "ANSWER"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "false_answer": sum(
                e != "ANSWER" and a == "ANSWER"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "correct_clarify": sum(
                e == "CLARIFY" and a == "CLARIFY"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "false_clarify": sum(
                e != "CLARIFY" and a == "CLARIFY"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "correct_abstain": sum(
                e == "ABSTAIN" and a == "ABSTAIN"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "false_abstain": sum(
                e == "ANSWER" and a == "ABSTAIN"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "missed_ambiguity": sum(
                e == "CLARIFY" and a != "CLARIFY"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "false_answer_rate": sum(
                e != "ANSWER" and a == "ANSWER"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            )
            / len(results),
            "false_clarify_rate_should_answer": sum(
                r["behavioral_target"] == "SHOULD_ANSWER" and r["shadow_action"] == "CLARIFY"
                for r in results
            )
            / len(gold_present)
            if gold_present
            else 0.0,
            "gold_present_answerable_answered": sum(
                r["shadow_action"] == "ANSWER" for r in gold_present
            ),
            "gold_present_answerable_count": len(gold_present),
        },
        "deterministic": {
            "count": sum(
                bool(r["deterministic_reason"] or r["semantic_evaluation_skipped"]) for r in results
            ),
            "reasons": dict(
                Counter(
                    r["deterministic_reason"] or r["semantic_evaluation_skipped"]
                    for r in results
                    if r["deterministic_reason"] or r["semantic_evaluation_skipped"]
                )
            ),
            "all_acl_abstain": all(
                r["shadow_action"] == "ABSTAIN" for r in results if r["category"] == "acl_negative"
            ),
        },
        "injection": {
            "status": "PASS"
            if injection and all(not r["parse_error"] for r in injection)
            else "INCONCLUSIVE",
            "count": len(injection),
            "parse_failures": sum(r["parse_error"] for r in injection),
            "actions": dict(Counter(r["shadow_action"] for r in injection)),
        },
        "multi_document": {
            "complete_n": len(multi_complete),
            "complete_answer": sum(r["shadow_action"] == "ANSWER" for r in multi_complete),
            "partial_n": len(multi_partial),
            "partial_abstain": sum(r["shadow_action"] == "ABSTAIN" for r in multi_partial),
        },
        "reliability": reliability,
        "latency": {
            "ambiguity": _latency(
                [
                    r["ambiguity_latency_ms"]
                    for r in results
                    if r["ambiguity_latency_ms"] is not None
                ]
            ),
            "sufficiency": _latency(
                [
                    r["sufficiency_latency_ms"]
                    for r in results
                    if r["sufficiency_latency_ms"] is not None
                ]
            ),
            "total": _latency([r["latency_ms"] for r in results]),
        },
        "short_circuit_saved_sufficiency_calls": sum(
            (r["ambiguity"] or {}).get("decision") == "AMBIGUOUS" for r in results
        ),
        "slices": _category_slices(results),
    }
    return summary, results


def _false_clarify_analysis(results: list[dict]) -> list[dict]:
    analysis = []
    for row in results:
        if row["behavioral_target"] != "SHOULD_ANSWER" or row["shadow_action"] != "CLARIFY":
            continue
        category = row["category"]
        root_cause = (
            "version/authority conflict"
            if category == "version_conflict"
            else "retrieval conflict"
            if category in {"hard_answerable", "cross_lingual", "multi_document"}
            else "over-conservative ambiguity"
        )
        analysis.append(
            {
                "query_id": row["query_id"],
                "case_family": row["case_family"],
                "category": category,
                "language_pair": row["language_pair"],
                "gold_present": row["gold_present"],
                "ambiguity_decision": (row["ambiguity"] or {}).get("decision"),
                "missing_constraints": (row["ambiguity"] or {}).get("missing_constraints", []),
                "root_cause": root_cause,
            }
        )
    return analysis


def write_artifacts(output_dir: Path, metadata: dict, summary: dict, results: list[dict]) -> None:
    (output_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in results) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "slice-results.json").write_text(
        json.dumps(summary["slices"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "false-clarify-analysis.json").write_text(
        json.dumps(_false_clarify_analysis(results), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "latency.json").write_text(
        json.dumps(summary["latency"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = (
        "# Phase 6C.2 balanced semantic evaluator smoke\n\n"
        f"- Model: `{MODEL}`\n"
        f"- Queries: `{summary['query_count']}`\n"
        f"- Behavioral targets: `{json.dumps(summary['behavioral_targets'], sort_keys=True)}`\n"
        f"- False answers: `{summary['combined']['false_answer']}/{summary['query_count']}`\n"
        f"- False clarifications on SHOULD_ANSWER: `"
        f"{summary['combined']['false_clarify_rate_should_answer']:.3f}`\n"
        f"- Gold-present coverage: `{summary['combined']['gold_present_answerable_answered']}/"
        f"{summary['combined']['gold_present_answerable_count']}`\n"
        f"- Retrieval calls during cache build: `"
        f"{metadata['retrieval_calls_during_cache_build']}`\n"
        "- Evaluator-only retrieval/embedding/reranker/generation calls: `0`\n\n"
        "This is a balanced validation smoke, not a production accuracy estimate. "
        "Prompts remain ambiguity_v1/sufficiency_v1; runtime enforcement remains off.\n"
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")


async def evaluate_cached(args: argparse.Namespace) -> dict:
    if args.model != MODEL:
        raise ValueError(f"Phase 6C.2 balanced smoke is restricted to {MODEL}")
    output_dir = Path(args.output_dir)
    metadata, records = load_cache(
        output_dir, Path(args.fingerprints), args.collection or COLLECTION_DEFAULT
    )
    client = OllamaClient(base_url=args.ollama_url)
    try:
        available = set(await client.list_models())
        if MODEL not in available:
            raise RuntimeError(f"evaluator model is not installed locally: {MODEL}")
        summary, results = await evaluate_model(
            MODEL, records, client, args.timeout_seconds, args.retries
        )
        summary.update(
            {
                "schema_version": "phase-6c2-balanced-semantic-smoke-v1",
                "git_sha": _git_sha(),
                "corpus_fingerprint": metadata["corpus_fingerprint"],
                "dataset_fingerprint": metadata["dataset_fingerprint"],
                "collection": metadata["collection"],
                "prompt_versions": metadata["prompt_versions"],
                "retrieval_config": metadata["retrieval_config"],
                "generation_invoked": False,
                "retrieval_calls_during_evaluator_run": 0,
                "embedding_calls_during_evaluator_run": 0,
                "reranker_calls_during_evaluator_run": 0,
                "acl_semantic_evaluator_calls": 0,
            }
        )
        write_artifacts(output_dir, metadata, summary, results)
        return summary
    finally:
        await client.aclose()


async def main_async(args: argparse.Namespace) -> dict:
    if args.report_only:
        output_dir = Path(args.output_dir)
        summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
        summary["acl_semantic_evaluator_calls"] = 0
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary
    if args.build_cache:
        metadata = await build_cache(args)
        if args.build_cache_only:
            return metadata
    return await evaluate_cached(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-cache", action="store_true")
    parser.add_argument("--build-cache-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--prior-features", type=Path, default=PRIOR_FEATURES)
    parser.add_argument("--fingerprints", type=Path, default=FINGERPRINTS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--index-validation", type=Path, default=INDEX_VALIDATION)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--reranker-device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main_async(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
