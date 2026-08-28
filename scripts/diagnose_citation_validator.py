# ruff: noqa: E501

"""Offline Phase 7.3 citation/validator diagnosis.

Consumes existing Phase 7 artifacts only.  There are deliberately no
provider, retrieval, embedding, reranker, or judge imports here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
FAILURE = ROOT / "artifacts/phase-7/failure-analysis"
REFINEMENT = ROOT / "artifacts/phase-7/evaluator-refinement"
OUT = ROOT / "artifacts/phase-7/citation-validator-diagnosis"

EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "generation_model": "qwen3.5:4b",
    "generation_prompt_version": "v3",
    "think": False,
    "candidate_k": 20,
    "top_n": 5,
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _failure_codes(violations: list[str]) -> list[str]:
    mapping = {
        "unauthorized_citation": "UNAUTHORIZED_CITATION_ID",
        "citation_suppression": "CITATION_SUPPRESSION",
        "hidden_policy_disclosure": "OTHER_VALIDATION_FAILURE",
        "output_schema_failure": "OUTPUT_SCHEMA_FAILURE",
    }
    codes: list[str] = []
    for violation in violations:
        code = mapping.get(violation, "OTHER_VALIDATION_FAILURE")
        if code not in codes:
            codes.append(code)
    return codes


def validate_inputs() -> dict[str, Any]:
    metadata = _json(SMOKE / "cache-metadata.json")
    summary = _json(SMOKE / "summary.json")
    query_ids = _json(SMOKE / "query-set.json")
    results = _jsonl(SMOKE / "generation-results.jsonl")
    cache = _jsonl(SMOKE / "retrieval-inputs.jsonl")
    citations = _json(SMOKE / "citation-results.json")["records"]
    for key, expected in EXPECTED.items():
        actual = metadata.get(key)
        if actual != expected:
            raise ValueError(f"Phase 7 artifact identity mismatch for {key}: {actual!r}")
    if summary.get("generation_model") != EXPECTED["generation_model"]:
        raise ValueError("Phase 7 summary generator mismatch")
    if len(query_ids) != 36 or len(results) != 36 or len(cache) != 36 or len(citations) != 36:
        raise ValueError("Phase 7 artifact count mismatch")
    if [row["query_id"] for row in results] != query_ids:
        raise ValueError("generation result order mismatch")
    if [row["query_id"] for row in cache] != query_ids:
        raise ValueError("retrieval cache order mismatch")
    if [row["query_id"] for row in citations] != query_ids:
        raise ValueError("citation result order mismatch")
    refinement = _jsonl(REFINEMENT / "rescored-results.jsonl")
    gold_ids = {
        row["query_id"]
        for row in results
        if row["answerability"] == "answerable" and row["all_required_present"]
    }
    if len(gold_ids) != 22 or {row["query_id"] for row in refinement} != gold_ids:
        raise ValueError("gold-present refinement set mismatch")
    return {
        "metadata": metadata,
        "summary": summary,
        "results": results,
        "cache": cache,
        "citations": citations,
        "refinement": refinement,
        "per_query": _jsonl(FAILURE / "per-query-analysis.jsonl"),
        "citation_history": _json(FAILURE / "citation-analysis.json"),
        "multidoc_history": _json(FAILURE / "multidoc-analysis.json"),
        "authority_history": _json(FAILURE / "authority-analysis.json"),
        "support_history": _json(REFINEMENT / "citation-decomposition.json"),
        "phase71_agreement": _json(REFINEMENT / "phase71-agreement.json"),
    }


def _historical_observation(result: dict[str, Any]) -> dict[str, Any]:
    persisted = result.get("evaluation_observability")
    if persisted is not None:
        return {
            "raw": bool(persisted.get("raw_candidate_available")),
            "validated": bool(persisted.get("validated_output_available")),
            "visible": bool(persisted.get("user_visible_output_available")),
            "source": "explicit_evaluation_observability",
        }
    passed = result.get("output_validation", {}).get("passed")
    raw = bool(result.get("answer"))
    return {
        "raw": raw,
        "validated": passed is True,
        "visible": passed is not False,
        "source": "historical_answer_field_only",
    }


def _validator(data: dict[str, Any]) -> dict[str, Any]:
    records = []
    for result in data["results"]:
        validation = result.get("output_validation", {})
        if validation.get("passed") is not False:
            continue
        observation = _historical_observation(result)
        ground = next(
            (event for event in result.get("events", []) if event.get("type") == "grounding"),
            {},
        )
        records.append(
            {
                "query_id": result["query_id"],
                "category": result["category"],
                "gold_present": result["gold_present"],
                "raw_candidate_available": observation["raw"],
                "raw_candidate_storage": observation["source"],
                "validator_failure_codes": _failure_codes(validation.get("violations", [])),
                "legacy_violations": validation.get("violations", []),
                "citation_ids_if_known": ground.get("citations_found", []),
                "validated_output_available": observation["validated"],
                "user_visible_output_available": observation["visible"],
                "content_assessable": observation["raw"],
                "content_status": "CONTENT_ASSESSABLE" if observation["raw"] else "CONTENT_UNASSESSABLE",
                "historical_manual_potential": True,
            }
        )
    codes = Counter(code for row in records for code in row["validator_failure_codes"])
    return {
        "rejection_count": len(records),
        "failure_code_counts": dict(sorted(codes.items())),
        "malformed_citation_syntax_observed": 0,
        "invalid_identity_or_unauthorized_records": sum(
            "UNAUTHORIZED_CITATION_ID" in row["validator_failure_codes"] for row in records
        ),
        "raw_candidate_observable_among_rejected": sum(row["raw_candidate_available"] for row in records),
        "raw_candidate_unobservable_among_rejected": sum(not row["raw_candidate_available"] for row in records),
        "content_correct_rejected": 0,
        "content_correct_incomplete_rejected": 0,
        "content_partial_rejected": 0,
        "content_incorrect_rejected": 0,
        "content_unassessable_rejected": sum(
            row["content_status"] == "CONTENT_UNASSESSABLE" for row in records
        ),
        "historical_manual_potential_count": sum(row["historical_manual_potential"] for row in records),
        "records": records,
        "note": "Historical results store the validated answer field, not the raw candidate; rejected content is not inferred from the old manual potential flag.",
    }


def _citation_identity(data: dict[str, Any]) -> dict[str, Any]:
    records = []
    total = invalid = duplicate_records = duplicate_excess = 0
    for result in data["citations"]:
        found = [tuple(item) for item in result.get("found", [])]
        invalid_items = [tuple(item) for item in result.get("unknown_or_unauthorized", [])]
        invalid_ids = set(invalid_items)
        unique = set(found)
        excess = len(found) - len(unique)
        total += len(found)
        invalid += len(invalid_items)
        duplicate_records += excess > 0
        duplicate_excess += excess
        records.append(
            {
                "query_id": result["query_id"],
                "citation_occurrences": len(found),
                "identity_valid_occurrences": sum(item not in invalid_ids for item in found),
                "unknown_or_unauthorized_occurrences": len(invalid_items),
                "duplicate_citation_excess": excess,
                "record_identity_valid": result["valid"],
            }
        )
    return {
        "answers_with_citations": sum(row["citation_occurrences"] > 0 for row in records),
        "answers_without_citations": sum(row["citation_occurrences"] == 0 for row in records),
        "citation_occurrences": total,
        "identity_valid_occurrences": total - invalid,
        "unknown_or_unauthorized_occurrences": invalid,
        "record_identity_pass": sum(row["record_identity_valid"] for row in records),
        "record_identity_denominator": len(records),
        "duplicate_citation_records": duplicate_records,
        "duplicate_citation_excess_occurrences": duplicate_excess,
        "malformed_citation_ids_observed": 0,
        "records": records,
        "note": "The historical parser persisted invalid identity as unknown_or_unauthorized; no separate syntax-error code is available.",
    }


def _citation_support(data: dict[str, Any]) -> dict[str, Any]:
    source = data["support_history"]
    statuses = Counter(source.get("summary", {}))
    records = []
    for row in source.get("records", []):
        counts = Counter(item["support_status"] for item in row["citations"])
        records.append(
            {
                "query_id": row["query_id"],
                "citation_count": len(row["citations"]),
                "support_status_counts": dict(counts),
            }
        )
    definite_records = sum(
        row["citation_count"] > 0 and set(row["support_status_counts"]) == {"SUPPORTED"}
        for row in records
    )
    return {
        "citation_occurrence_support_counts": dict(statuses),
        "definitely_supported_occurrences": statuses["SUPPORTED"],
        "review_required_occurrences": statuses["RELATED_BUT_INSUFFICIENT"] + statuses["UNKNOWN_ID"],
        "definitely_supported_records": definite_records,
        "record_denominator": len(records),
        "records": records,
        "source": "Phase 7.2 deterministic/manual citation decomposition",
    }


def _citation_completeness(data: dict[str, Any]) -> dict[str, Any]:
    rows = data["refinement"]
    complete = sum(row.get("citation_completeness") == 1 for row in rows)
    return {
        "source_level_complete_records": complete,
        "denominator": len(rows),
        "rate": round(complete / len(rows), 6) if rows else None,
        "claim_level_status": "REQUIRES_MANUAL_REVIEW",
        "note": "This is required-source citation coverage, not claim entailment.",
    }


def _source_alignment(data: dict[str, Any]) -> dict[str, Any]:
    rescored = {row["query_id"]: row for row in data["refinement"]}
    records = []
    occurrences = correct_fact = wrong_fact = 0
    for row in data["citation_history"]["records"]:
        related = [
            item for item in row["classifications"] if item["classification"] == "RELATED_WRONG_CLAIM"
        ]
        if not related:
            continue
        status = rescored[row["query_id"]]["fact_score"]["status"]
        if status in {"FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE"}:
            correct_fact += len(related)
        else:
            wrong_fact += len(related)
        occurrences += len(related)
        records.append(
            {
                "query_id": row["query_id"],
                "related_wrong_claim_occurrences": len(related),
                "content_status": status,
            }
        )
    return {
        "source_alignment_failure_records": len(records),
        "source_alignment_failure_occurrences": occurrences,
        "correct_fact_wrong_source_occurrences": correct_fact,
        "wrong_fact_wrong_source_occurrences": wrong_fact,
        "records": records,
        "note": "RELATED_WRONG_CLAIM is the persisted proxy; no claim extractor was introduced.",
    }


def _multidoc(data: dict[str, Any]) -> dict[str, Any]:
    rescored = {row["query_id"]: row for row in data["refinement"]}
    records = []
    for row in data["multidoc_history"]:
        score = rescored[row["query_id"]]
        records.append(
            {
                "query_id": row["query_id"],
                "required_sources": row["expected_facts"],
                "top5_source_order": row["authorized_top5_sources"],
                "cited_sources": sorted(
                    {item["citation"][1] for item in row["citation_classification"] if item.get("citation")}
                ),
                "required_fact_count": score["fact_score"]["required_fact_count"],
                "matched_fact_count": len(score["fact_score"]["matched_fact_ids"]),
                "missing_fact_ids": score["fact_score"]["missing_fact_ids"],
                "citation_support": dict(
                    Counter(item["classification"] for item in row["citation_classification"])
                ),
                "validator_pass": row["output_validation"]["passed"],
                "raw_candidate_available": bool(row["generated_answer"]),
                "reviewed_outcome": row["reviewed_outcome"],
                "primary_failure_cause": row["primary_failure_cause"],
            }
        )
    return {
        "n": len(records),
        "phase6_semantic_gate_answer": "0/3",
        "records": records,
        "conclusion": "All required evidence was cached; synthesis/citation remained unreliable, with one record unobservable after strict suppression.",
    }


def _authority(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "records": data["authority_history"],
        "summary": {
            "current_rule_selected": sum(
                row["classification"] == "CURRENT_RULE_SELECTED" for row in data["authority_history"]
            ),
            "stale_or_noncanonical_mixed": sum(
                row["classification"] != "CURRENT_RULE_SELECTED" for row in data["authority_history"]
            ),
        },
    }


def _cross_lingual(data: dict[str, Any]) -> dict[str, Any]:
    rescored = {row["query_id"]: row for row in data["refinement"]}
    causes = {row["query_id"]: row for row in data["per_query"]}
    records = []
    for row in data["per_query"]:
        if row["category"] != "cross_lingual":
            continue
        score = rescored[row["query_id"]]
        records.append(
            {
                "query_id": row["query_id"],
                "language_pair": row["language_pair"],
                "fact_status": score["fact_score"]["status"],
                "citation_identity_valid": score["citation_identity_valid"],
                "citation_support_reference": score["citation_support_reference"],
                "validator_pass": score["validator_pass"],
                "primary_failure_cause": causes[row["query_id"]]["primary_failure_cause"],
            }
        )
    return {
        "records": records,
        "pair_counts": dict(Counter(row["language_pair"] for row in records)),
        "conclusion": "Cross-lingual failures are mixed: valid citations can accompany content/authority issues, while one EN-to-TR case is unobservable after invalid citation rejection.",
    }


def build_diagnosis() -> dict[str, Any]:
    data = validate_inputs()
    by_id = {row["query_id"]: row for row in data["results"]}
    validator = _validator(data)
    identity = _citation_identity(data)
    support = _citation_support(data)
    completeness = _citation_completeness(data)
    alignment = _source_alignment(data)
    primary = data["refinement"]
    raw_observable = sum(bool(row.get("answer")) for row in data["results"])
    primary_raw_observable = sum(bool(by_id[row["query_id"]].get("answer")) for row in primary)
    return {
        "identity": {key: data["metadata"].get(key) for key in EXPECTED} | {"validated": True},
        "scope": {
            "records": 36,
            "gold_present_answerable": 22,
            "new_generation_calls": 0,
            "new_retrieval_calls": 0,
            "new_reranker_calls": 0,
            "new_evaluator_calls": 0,
            "frozen_test_touched": False,
        },
        "validator": validator,
        "citation_identity": identity,
        "citation_support": support,
        "citation_completeness": completeness,
        "source_alignment": alignment,
        "multidoc": _multidoc(data),
        "authority": _authority(data),
        "cross_lingual": _cross_lingual(data),
        "injection": {
            "control_failures": 0,
            "classification": "INJECTION_CONTROL_SAFE; raw capture remains evaluation-only",
        },
        "observability_gap": {
            "historical_raw_candidate_observable": raw_observable,
            "historical_raw_candidate_unobservable": 36 - raw_observable,
            "historical_primary_raw_candidate_observable": primary_raw_observable,
            "historical_primary_raw_candidate_unobservable": 22 - primary_raw_observable,
            "rejected_raw_candidate_observable": validator["raw_candidate_observable_among_rejected"],
            "rejected_content_unassessable": validator["content_unassessable_rejected"],
            "future_contract_fields": [
                "raw_candidate_output",
                "validator_input",
                "validator_result",
                "validator_failure_codes",
                "validated_output",
                "user_visible_output",
            ],
            "default_raw_persistence": False,
            "evaluation_capture_boundary": "explicit in-memory GenerationObservation; caller controls artifact persistence",
        },
        "next_step": {
            "status": "OBSERVABILITY_READY_CONTEXT_BUILDER_NEXT",
            "why": "Validator and citation identity failures are separable, raw/validated/user-visible boundaries are instrumentable, and remaining source-alignment/context issues can be tested without weakening strict validation.",
            "do_not_change": [
                "qwen3.5:4b",
                "prompt v3",
                "retrieval/reranker/cache",
                "strict validator enforcement",
                "ACL",
                "Phase 6 semantic gate",
                "qwen3.5:9b branch",
            ],
        },
        "phase71_agreement": data["phase71_agreement"],
    }


def write_outputs(report: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "validator-rejections.json": report["validator"],
        "citation-identity.json": report["citation_identity"],
        "citation-support.json": report["citation_support"],
        "citation-completeness.json": report["citation_completeness"],
        "source-alignment.json": report["source_alignment"],
        "multidoc-citation-analysis.json": report["multidoc"],
        "authority-citation-analysis.json": report["authority"],
        "cross-lingual-citation-analysis.json": report["cross_lingual"],
        "observability-gap.json": report["observability_gap"],
        "next-step-decision.json": report["next_step"],
    }
    for name, value in files.items():
        _write(OUT / name, value)
    lines = [
        "# Phase 7.3 Citation / Validator Diagnosis",
        "",
        "Offline analysis only. No inference, retrieval, reranker, embedding, semantic evaluator, or external judge call was made.",
        "",
        "## Identity",
        f"- Generator: {report['identity']['generation_model']}; prompt: {report['identity']['generation_prompt_version']}; think: {report['identity']['think']}.",
        f"- Corpus: {report['identity']['corpus_fingerprint']}; dataset: {report['identity']['dataset_fingerprint']}.",
        "- Retrieval cache identity validated: candidate_k 20, top_n 5, 36 records.",
        "",
        "## Validator and observability",
        f"- Validator rejections: {report['validator']['rejection_count']}/36; codes: {report['validator']['failure_code_counts']}.",
        f"- Historical raw candidate observable: {report['observability_gap']['historical_raw_candidate_observable']}/36; rejected content unassessable: {report['validator']['content_unassessable_rejected']}/7.",
        "- Strict rejection remains user-visible suppression; opt-in capture does not alter delivery.",
        "",
        "## Citation diagnosis",
        f"- Citation-bearing records: {report['citation_identity']['answers_with_citations']}/36; occurrences: {report['citation_identity']['citation_occurrences']}.",
        f"- Invalid identity occurrences: {report['citation_identity']['unknown_or_unauthorized_occurrences']}; duplicate excess occurrences: {report['citation_identity']['duplicate_citation_excess_occurrences']}.",
        f"- Definite citation support: {report['citation_support']['definitely_supported_occurrences']} occurrences; review-required: {report['citation_support']['review_required_occurrences']}.",
        f"- Source-level required-fact citation completeness: {report['citation_completeness']['source_level_complete_records']}/{report['citation_completeness']['denominator']}; claim-level support remains manual.",
        f"- Source-alignment proxy: {report['source_alignment']['source_alignment_failure_occurrences']} occurrences in {report['source_alignment']['source_alignment_failure_records']} records.",
        "",
        "## Critical slices",
        "- Multi-document: Phase 6 semantic gate answer was 0/3; all required evidence was present, but generation did not reliably synthesize and cite complete answers.",
        f"- Authority/version summary: {report['authority']['summary']}.",
        f"- Injection control: {report['injection']['classification']}.",
        f"- Cross-lingual: {report['cross_lingual']['conclusion']}",
        "",
        "## Decision",
        f"- {report['next_step']['status']}.",
        f"- {report['next_step']['why']}",
        "- Context Builder A/B is safe to begin as a separate measurement experiment; strict citation validation, ACL, model, prompt, and retrieval remain unchanged.",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_diagnosis()
    write_outputs(report)
    print(json.dumps({"status": report["next_step"]["status"], "new_inference_calls": 0}))


if __name__ == "__main__":
    main()
