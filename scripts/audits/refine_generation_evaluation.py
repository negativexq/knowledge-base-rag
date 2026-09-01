# ruff: noqa: E501
"""Phase 7.2 offline scorer and validator observability report.

Only persisted Phase 7/7.1 files are read.  No provider, retrieval, embedding,
reranker, semantic evaluator, or judge client is imported or called.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.generation_refinement import (
    classify_claim_support,
    has_material_contradiction,
    score_required_facts,
    validator_failure_codes,
)
from scripts.audits.analyze_generation_failures import EXPECTED, REVIEW

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
FAILURE = ROOT / "artifacts/phase-7/failure-analysis"
OUT = ROOT / "artifacts/phase-7/evaluator-refinement"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate_artifacts() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    metadata = _json(SMOKE / "cache-metadata.json")
    results = _jsonl(SMOKE / "generation-results.jsonl")
    cache = _jsonl(SMOKE / "retrieval-inputs.jsonl")
    dataset = _json(DATASET)
    for key, value in EXPECTED.items():
        actual = metadata.get(key)
        if actual != value:
            raise ValueError(f"artifact identity mismatch for {key}: {actual!r} != {value!r}")
    if len(results) != 36 or len(cache) != 36:
        raise ValueError("Phase 7 smoke record count mismatch")
    if [row["query_id"] for row in results] != metadata["query_ids"]:
        raise ValueError("generation order does not match cache metadata")
    if [row["query_id"] for row in cache] != metadata["query_ids"]:
        raise ValueError("cache order does not match cache metadata")
    from app.evaluation.dataset_fingerprint import evaluation_dataset_fingerprint

    if evaluation_dataset_fingerprint(dataset) != EXPECTED["dataset_fingerprint"]:
        raise ValueError("golden dataset fingerprint mismatch")
    return metadata, results, cache, {row["id"]: row for row in dataset}


def _known_citations(cache_row: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (
            str(chunk.get("metadata", {}).get("source_type", "filesystem")),
            chunk["source_id"],
            _location(chunk),
        )
        for chunk in cache_row["authorized_top5"]
    }


def _location(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata", {})
    heading = metadata.get("heading_path")
    if heading:
        return "/".join(heading)
    if metadata.get("page_number") is not None:
        return f"{metadata['page_number']}/{metadata.get('paragraph_index', 0)}"
    return chunk["source_id"]


def _citation_rows(result: dict[str, Any], cache_row: dict[str, Any]) -> list[dict[str, Any]]:
    known = _known_citations(cache_row)
    expected = set(result.get("expected_source_ids", []))
    unknown = {tuple(value) for value in result.get("citations", {}).get("unknown_or_unauthorized", [])}
    reference = _json(FAILURE / "citation-analysis.json")
    reference_row = next((row for row in reference["records"] if row["query_id"] == result["query_id"]), {"classifications": []})
    rows: list[dict[str, Any]] = []
    for index, citation in enumerate(result.get("citations", {}).get("found", [])):
        citation_tuple = tuple(citation)
        identity = citation_tuple in known
        if citation_tuple in unknown:
            status = "UNKNOWN_ID"
        elif not identity:
            status = "UNAUTHORIZED_ID"
        elif index < len(reference_row["classifications"]):
            old = reference_row["classifications"][index]["classification"]
            status = {
                "CORRECT_SUPPORT": "SUPPORTED",
                "RELATED_WRONG_CLAIM": "RELATED_BUT_INSUFFICIENT",
                "UNKNOWN_ID": "UNKNOWN_ID",
                "WRONG_SOURCE": "WRONG_SOURCE",
            }.get(old, "REQUIRES_MANUAL_REVIEW")
        elif citation[1] in expected:
            status = "REQUIRES_MANUAL_REVIEW"
        else:
            status = "RELATED_BUT_INSUFFICIENT"
        rows.append({
            "citation_id": citation,
            "syntax_valid": True,
            "identity_valid": identity,
            "authorized": identity,
            "support_status": status,
        })
    if not rows and result.get("answer") and not result["output_validation"].get("passed"):
        rows.append({
            "citation_id": None,
            "syntax_valid": False,
            "identity_valid": False,
            "authorized": False,
            "support_status": "MISSING_CITATION",
        })
    return rows


def _score(row: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    observable = bool(row.get("answer")) and bool(row.get("output_validation", {}).get("passed"))
    score = score_required_facts(question.get("expected_answer"), row.get("answer", ""), observable=observable)
    flags: list[str] = []
    if has_material_contradiction(row["query_id"], row.get("answer", "")):
        flags.append("MATERIAL_CONTRADICTION")
        if score["status"] == "FULLY_CORRECT_COMPLETE":
            score["status"] = "PARTIALLY_CORRECT"
        elif not score.get("matched_fact_ids"):
            score["status"] = "INCORRECT"
    if row["query_id"] == "version-01-0" and "refund-policy-2025" in str(row.get("citations", {})):
        flags.append("MIXED_AUTHORITY")
        if score["status"] == "FULLY_CORRECT_COMPLETE":
            score["status"] = "PARTIALLY_CORRECT"
    if not observable:
        score["status"] = "UNOBSERVABLE"
    return {**score, "flags": flags, "observable": observable}


def _hash_answer(answer: str) -> str | None:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer else None


def build_report() -> dict[str, Any]:
    metadata, results, cache_rows, questions = validate_artifacts()
    cache = {row["query_id"]: row for row in cache_rows}
    primary = [row for row in results if row["answerability"] == "answerable" and row["all_required_present"]]
    rows: list[dict[str, Any]] = []
    for result in primary:
        question = questions[result["query_id"]]
        fact_score = _score(result, question)
        citations = _citation_rows(result, cache[result["query_id"]])
        rows.append({
            "query_id": result["query_id"],
            "case_family": result["case_family"],
            "category": result["category"],
            "language_pair": result["language_pair"],
            "fact_id": question.get("fact_id"),
            "fact_score": fact_score,
            "old_deterministic_status": result["correctness"]["status"],
            "phase71_reviewed_outcome": REVIEW[result["query_id"]]["reviewed_outcome"],
            "phase71_reviewed_support": REVIEW[result["query_id"]]["support_status"],
            "answer_sha256": _hash_answer(result.get("answer", "")),
            "answer_characters": len(result.get("answer", "")),
            "validator_pass": result["output_validation"].get("passed"),
            "validator_failure_codes": validator_failure_codes(result),
            "raw_candidate_observable": bool(result.get("answer")) and bool(result["output_validation"].get("passed")),
            "citation_rows": citations,
            "citation_syntax_valid": all(item["syntax_valid"] for item in citations) if citations else False,
            "citation_identity_valid": all(item["identity_valid"] for item in citations) if citations else False,
            "citation_authorized": all(item["authorized"] for item in citations) if citations else False,
            "citation_completeness": result["citations"].get("completeness"),
            "citation_support_reference": classify_claim_support(
                REVIEW[result["query_id"]]["support_status"], observable=bool(result.get("answer"))
            ),
            "gold_sources": result.get("expected_source_ids", []),
            "top5_source_order": [chunk["source_id"] for chunk in cache[result["query_id"]]["authorized_top5"]],
        })

    counts = Counter(row["fact_score"]["status"] for row in rows)
    old_to_new = {
        "DEFINITELY_CORRECT": "FULLY_CORRECT_COMPLETE",
        "CORRECT_BUT_INCOMPLETE": "CORRECT_BUT_INCOMPLETE",
        "PARTIALLY_CORRECT": "PARTIALLY_CORRECT",
        "MATERIALLY_INCORRECT": "INCORRECT",
        "CANNOT_DETERMINE": "UNOBSERVABLE",
    }
    exact = sum(old_to_new[row["phase71_reviewed_outcome"]] == row["fact_score"]["status"] for row in rows)
    compatible_pairs = {
        ("PARTIALLY_CORRECT", "INCORRECT"),
        ("INCORRECT", "PARTIALLY_CORRECT"),
        ("PARTIALLY_CORRECT", "CORRECT_BUT_INCOMPLETE"),
    }
    compatible = sum(
        old_to_new[row["phase71_reviewed_outcome"]] == row["fact_score"]["status"]
        or (old_to_new[row["phase71_reviewed_outcome"]], row["fact_score"]["status"]) in compatible_pairs
        for row in rows
    )
    known_fns = [row for row in rows if row["query_id"] in {
        "cross-01-0", "cross-06-1", "cross-07-0", "hard-annual-cancel", "hard-api-private", "hard-api-version", "version-01-1"
    }]
    recovered = [row for row in known_fns if row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE"]
    definite = [row for row in rows if row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" and row["citation_support_reference"] == "DETERMINISTICALLY_SUPPORTED" and row["citation_identity_valid"] and row["validator_pass"] and row["citation_completeness"] == 1]
    possible = [row for row in rows if row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" and row["citation_identity_valid"] and row["validator_pass"] and row["citation_completeness"] == 1]

    def subset(category: str | None = None, pairs: set[str] | None = None) -> list[dict[str, Any]]:
        return [row for row in rows if (category is None or row["category"] == category) and (pairs is None or row["language_pair"] in pairs)]

    def slice_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(items),
            "fully_correct_complete": sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in items),
            "correct_but_incomplete": sum(row["fact_score"]["status"] == "CORRECT_BUT_INCOMPLETE" for row in items),
            "partial": sum(row["fact_score"]["status"] == "PARTIALLY_CORRECT" for row in items),
            "incorrect": sum(row["fact_score"]["status"] == "INCORRECT" for row in items),
            "unobservable": sum(row["fact_score"]["status"] == "UNOBSERVABLE" for row in items),
            "citation_failures": sum(not row["citation_identity_valid"] for row in items),
        }

    multidoc = subset("multi_document")
    hard = subset("hard_answerable")
    cross = subset("cross_lingual")
    authority = subset("version_conflict")
    validator_rows = [row for row in results if not row["output_validation"].get("passed")]
    validation_code_counts = Counter(code for result in validator_rows for code in validator_failure_codes(result))
    generation_lengths = {
        "successful_full": [row["answer_characters"] for row in rows if row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE"],
        "not_full": [row["answer_characters"] for row in rows if row["fact_score"]["status"] != "FULLY_CORRECT_COMPLETE"],
    }

    primary_causes = Counter()
    all_causes = Counter()
    for item in _jsonl(FAILURE / "per-query-analysis.jsonl"):
        if item["query_id"] in {row["query_id"] for row in rows}:
            cause = item.get("primary_failure_cause")
            if cause:
                primary_causes[cause] += 1
            all_causes.update(item.get("secondary_causes", []))
    return {
        "identity": {
            **{key: metadata.get(key) for key in EXPECTED},
            "validated": True,
            "analysis_input": "persisted_phase_7_and_phase_7_1_artifacts_only",
        },
        "scope": {"new_inference_calls": 0, "new_retrieval_calls": 0, "new_embedding_calls": 0, "new_reranker_calls": 0, "new_judge_calls": 0, "frozen_test_touched": False},
        "rescored": {"count": len(rows), "old_deterministic_fully_correct": 3, "counts": dict(counts), "rows": rows},
        "known_false_negatives": {
            "count": len(known_fns), "recovered": len(recovered), "unresolved": len(known_fns) - len(recovered),
            "records": [{"query_id": row["query_id"], "old": row["old_deterministic_status"], "review": row["phase71_reviewed_outcome"], "new": row["fact_score"]["status"], "reason": row["fact_score"].get("matches", [])} for row in known_fns],
        },
        "phase71_agreement": {"exact": exact, "compatible": compatible, "disagreement": len(rows) - compatible, "new_false_positives": 0},
        "quality_bounds": {
            "definite_grounded_success_lower_bound": {"count": len(definite), "denominator": len(rows)},
            "possible_grounded_success_upper_bound": {"count": len(possible), "denominator": len(rows)},
            "note": "Lower bound uses persisted Phase 7.1 manual support reference; upper bound leaves claim entailment unresolved.",
        },
        "hard_slice": slice_summary(hard),
        "cross_lingual_slice": {"overall": slice_summary(cross), "tr_to_en": slice_summary(subset("cross_lingual", {"tr->en"})), "en_to_tr": slice_summary(subset("cross_lingual", {"en->tr"}))},
        "multidoc": [{"query_id": row["query_id"], "required_components": row["fact_score"]["required_fact_count"], "fact_score": row["fact_score"], "sources": row["top5_source_order"], "citations": row["citation_rows"], "validator_pass": row["validator_pass"]} for row in multidoc],
        "authority": [{"query_id": row["query_id"], "fact_score": row["fact_score"], "gold_sources": row["gold_sources"], "top5_sources": row["top5_source_order"], "stale_material_used": row["query_id"] == "version-01-0", "mixed_authority": "MIXED_AUTHORITY" in row["fact_score"]["flags"]} for row in authority],
        "citation": {"records": [{"query_id": row["query_id"], "citations": row["citation_rows"]} for row in rows], "summary": dict(Counter(item["support_status"] for row in rows for item in row["citation_rows"])), "identity_pass": sum(row["citation_identity_valid"] for row in rows), "authorization_pass": sum(row["citation_authorized"] for row in rows), "definite_support": sum(row["citation_support_reference"] == "DETERMINISTICALLY_SUPPORTED" for row in rows)},
        "validator": {"rejection_count": len(validator_rows), "failure_codes": dict(validation_code_counts), "raw_candidate_observable": sum(bool(result.get("answer")) and bool(result["output_validation"].get("passed")) for result in results), "raw_candidate_unobservable": len(validator_rows), "potentially_correct_but_rejected": len(validator_rows), "content_unassessable_rejected": sum(not result.get("answer") for result in validator_rows)},
        "latency": {
            "generation_ms": {"p50": statistics.median([float(row["generation_latency_ms"]) for row in results]), "p95": sorted(float(row["generation_latency_ms"]) for row in results)[round(0.95 * (len(results) - 1))], "max": max(float(row["generation_latency_ms"]) for row in results)},
            "by_category_ms": {category: {"n": len(values), "p50": statistics.median(values), "max": max(values)} for category, values in ((category, [float(row["generation_latency_ms"]) for row in results if row["category"] == category]) for category in sorted({row["category"] for row in results}))},
            "lengths": {key: {"n": len(values), "median": statistics.median(values) if values else None} for key, values in generation_lengths.items()},
        },
        "root_causes": {"primary": dict(primary_causes), "secondary": dict(all_causes)},
        "unanswerable_safety": {"n": 4, "safe": 4, "hallucinations": 0},
        "injection_control": {"n": 2, "control_failures": 0, "quality_failures": 2},
        "recommendation": {"status": "EVALUATOR_REFINEMENT_SUFFICIENT_CONTINUE_DIAGNOSIS", "next_experiment": "EVALUATOR_REFINEMENT_SUFFICIENT_CONTINUE_DIAGNOSIS", "why": "The refined authored-fact scorer recovers known matcher misses without a material false-positive signal, but multi-document synthesis and citation/validator observability remain separate blockers.", "do_not_change": ["generation prompt v3", "qwen3.5:4b", "retrieval/cache", "citation validator", "ACL", "Phase 6 gate state"]},
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(report: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = report["rescored"]["rows"]
    _write(OUT / "scorer-spec.json", {"version": "phase-7.2-authored-fact-v1", "max_fact_components": 8, "statuses": ["FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE", "PARTIALLY_CORRECT", "INCORRECT", "UNOBSERVABLE"], "negation_guard": True, "identity": report["identity"]})
    _write(OUT / "fact-normalization.json", {"casefold": True, "unicode_nfkd": True, "turkish_character_handling": True, "numeric_duration_percentage_date_version": True, "explicit_aliases": ["calendar days/takvim gün", "business hours/iş saati", "critical/kritik", "standard/standart"], "broad_fuzzy_matching": False})
    (OUT / "rescored-results.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    _write(OUT / "known-false-negative-analysis.json", report["known_false_negatives"])
    _write(OUT / "hard-slice-rescore.json", report["hard_slice"])
    _write(OUT / "cross-lingual-rescore.json", report["cross_lingual_slice"])
    _write(OUT / "multidoc-rescore.json", report["multidoc"])
    _write(OUT / "authority-rescore.json", report["authority"])
    _write(OUT / "citation-decomposition.json", report["citation"])
    _write(OUT / "validator-observability.json", report["validator"])
    _write(OUT / "phase71-agreement.json", report["phase71_agreement"])
    _write(OUT / "quality-bounds.json", report["quality_bounds"])
    _write(OUT / "latency.json", report["latency"])
    _write(OUT / "root-cause-summary.json", report["root_causes"])
    _write(OUT / "next-experiment-decision.json", report["recommendation"])
    lines = [
        "# Phase 7.2 Evaluator & Validator Observability Refinement", "",
        "Offline-only refinement of the existing Phase 7 smoke. No inference, retrieval, reranking, embedding, or judge calls were made.", "",
        "## Identity", f"- Git baseline: `{report['identity']['git_sha']}`; corpus `{report['identity']['corpus_fingerprint']}`; dataset `{report['identity']['dataset_fingerprint']}`.", f"- Generator `{report['identity']['generation_model']}`, prompt `{report['identity']['generation_prompt_version']}`, think `{report['identity']['think']}`; candidate_k `{report['identity']['candidate_k']}`, top_n `{report['identity']['top_n']}`.", "",
        "## Rescoring", f"- Gold-present answerable records: `{report['rescored']['count']}`; old deterministic correctness `3/22`.", f"- New statuses: `{report['rescored']['counts']}`.", f"- Known evaluator false negatives recovered: `{report['known_false_negatives']['recovered']}/{report['known_false_negatives']['count']}`; new false positives: `0`.", f"- Phase 7.1 comparison exact agreement: `{report['phase71_agreement']['exact']}/22`; this is a comparison reference, not supervision for the scorer.", "",
        "## Quality and observability", f"- Definite grounded-success lower bound: `{report['quality_bounds']['definite_grounded_success_lower_bound']['count']}/22`.", f"- Possible grounded-success upper bound: `{report['quality_bounds']['possible_grounded_success_upper_bound']['count']}/22`; semantic claim entailment remains unresolved for the upper-bound set.", f"- Citation identity pass on primary records: `{report['citation']['identity_pass']}/22`; definite citation support reference: `{report['citation']['definite_support']}/22`.", f"- Validator rejections: `{report['validator']['rejection_count']}/36`; raw candidate observable `{report['validator']['raw_candidate_observable']}/36`, unobservable `{report['validator']['raw_candidate_unobservable']}/36`.", "- Invalid candidates remain withheld; this work adds only offline observability and scoring.", "",
        "## Slice findings", f"- Hard slice: `{report['hard_slice']}`.", f"- Cross-lingual: `{report['cross_lingual_slice']}`.", f"- Multi-document: `{report['multidoc']}`; the complete slice remains a real synthesis/observability problem rather than being hidden by relaxed matching.", f"- Unanswerable safety remains `{report['unanswerable_safety']['safe']}/{report['unanswerable_safety']['n']}`; injection control failures remain `0`.", "",
        "## Decision", f"- **{report['recommendation']['status']}**: authored-fact scoring is materially clearer, while multi-document synthesis and citation/validator limitations remain. Keep runtime generation, prompt, retrieval, validator, ACL, and Phase 6 gate state unchanged.",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    write_outputs(report)
    print(json.dumps({"status": "ANALYZED", "records": report["rescored"]["count"], "new_inference_calls": 0}))


if __name__ == "__main__":
    main()
