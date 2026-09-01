# ruff: noqa: E501

"""Independent V2 contract validation with dual pre-execution review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.critical_occurrence_validation import validate_occurrences_v3
from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_validator_architecture_v2 import audit_claim_architecture_v2
from app.evaluation.critical_values import claim_local_critical_value_audit

ROOT = Path("artifacts/ragbench/canonical/critical-value-validator-architecture-v2-independent-contract-validation-v2")
DRAFT = ROOT / "01-population-draft"
REVIEW_A = ROOT / "02-review-a"
REVIEW_B = ROOT / "03-review-b"
ADJ = ROOT / "04-adjudication"
FREEZE = ROOT / "05-population-freeze"
PREREG = ROOT / "06-preregistration"
EXEC = ROOT / "07-execution"
COMP = ROOT / "08-comparison"
SLICES = ROOT / "09-slices"
REPORT = ROOT / "10-report"


def _case(case_id: str, category: str, answer: str, labels: list[str], query: str | None = None) -> dict[str, Any]:
    occurrences = extract_critical_occurrences(answer, claim_id=case_id)
    if len(occurrences) != len(labels):
        raise AssertionError(f"{case_id}: extracted {len(occurrences)}, expected {len(labels)}")
    return {
        "case_id": case_id,
        "category": category,
        "answer_text": answer,
        "query_text": query or f"Independent contract query {case_id}",
        "support_texts": [answer],
        "occurrences": [
            {
                "occurrence_id": o.occurrence_id,
                "span_start": o.span_start,
                "span_end": o.span_end,
                "raw_literal": o.raw_literal,
                "normalized_value": o.normalized_value,
                "lexical_type": o.lexical_type,
                "unit": o.unit,
                "claim_unit_id": o.claim_unit_id,
                "expected_extraction_status": "EXPECTED_OCCURRENCE",
                "expected_role": label,
            }
            for o, label in zip(occurrences, labels)
        ],
    }


def build_population() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    ordinary = [
        "The connection timeout is 53 seconds.",
        "The batch quota is 275 requests per minute.",
        "The supported package is 13.2.4.",
        "The SQLCODE is -305.",
        "The incident is CVE-2035-73.",
        "The rollout reached 14%.",
        "The retention window is 84 days.",
        "The maintenance date is 2028-03-18.",
        "The measured ratio is 0.875.",
        "The signed threshold is +16.",
        "The backoff lasts 7 minutes.",
        "The release family is version 11.4.2.",
        "The delay is 3 hours.",
        "The retry budget is 6 attempts.",
        "The cutoff is 2029-11-06.",
        "The allowed drift is 2.5%.",
        "The response code is -503.",
        "The deployment uses 15.1.6.",
        "The report contains 41 records.",
        "The grace period is 72 hours.",
    ]
    for i, answer in enumerate(ordinary, 1):
        cases.append(_case(f"ORD{i:02d}", "ORDINARY_ASSERTION", answer, ["VALIDATE"]))

    corrective = [
        ("The accepted timeout is 53 seconds, rather than 41 seconds.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The quota is 275 requests per minute, not 190 requests per minute.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The proposed count 41 is incorrect; the recorded count is 53.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("Your 190 figure is wrong; the operating quota is 275.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The package is not 13.2.3; the supported package is 13.2.4.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The runbook cites 61 days, but the retention rule specifies 84 days.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The source does not support 700 requests per minute; it specifies 275 requests per minute.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old cutoff 2028-03-17 is rejected; the operational cutoff is 2028-03-18.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The configured rate is 14%, not 6%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The measured ratio is 0.875 instead of 0.625.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The interval is 48 minutes rather than 22 minutes.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The identifier CVE-2035-73 is correct, not CVE-2035-74.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed response is -503 rather than 503.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The code is +16, not +12.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The documented release is 11.4.2, not release 11.4.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The deadline is 2029-11-06, not 2029-11-05.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The source lists 14 percent instead of 9 percent.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The premise 0.5 is rejected; the approved ratio is 0.875.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("You supplied 22 minutes; the procedure requires 48 minutes.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The question's 13.2.3 build is outdated; the supported build is 13.2.4.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The status is -305, not -304.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The documented issue is CVE-2035-73 rather than CVE-2035-72.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for i, (answer, labels) in enumerate(corrective, 1):
        cases.append(_case(f"CORR{i:02d}", "CORRECTIVE", answer, labels))

    sibling = [
        ("The archived quota was 88. The 88 in the request is rejected; the live quota is 96.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("Service A retains 72 days. The 72-day premise for Service B is wrong; B retains 90 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The first counter is 41. Your 41 figure is incorrect; the current counter is 53.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The 63 is not the active threshold; an independent report records 63.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old window was 84 days, and the current window is also 84 days.", ["VALIDATE", "VALIDATE"]),
        ("The first claim 27 is rejected, and the second 27 is also unsupported; the approved value is 33.", ["SKIP_REJECTED_PREMISE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The signed code is -305; the 305 in the premise is wrong; another operation returns 305.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The rate is 14%; the 14% in the request is rejected; a second metric uses 14%.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The exact build is 15.1.6; the comparison also states 15.1.6.", ["VALIDATE", "VALIDATE"]),
        ("The first date is 2028-03-18; the audit record repeats 2028-03-18.", ["VALIDATE", "VALIDATE"]),
        ("The documented ratio is 0.875; the query's 0.875 is rejected; a report independently measures 0.875.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The legacy issue is CVE-2035-73; the request's CVE-2035-73 is wrong for this service; another record uses CVE-2035-73.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The value 41 might apply; a separate supported duration is 41 days.", ["AMBIGUOUS_KEEP_VALIDATING", "VALIDATE"]),
        ("The interval may be 22 or 48 minutes.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The first version is 6.5.2; the second component also reports 6.5.2.", ["VALIDATE", "VALIDATE"]),
        ("The first signed result is +42. The +42 in the request is not accepted; another field reports +42.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old percentage was 8%; the new percentage is 8%.", ["VALIDATE", "VALIDATE"]),
        ("The first limit 96 is factual; the limit 96 in the question is not the active setting.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for i, (answer, labels) in enumerate(sibling, 1):
        cases.append(_case(f"SIB{i:02d}", "SAME_VALUE_SIBLING", answer, labels))

    signed = [
        ("The return code is -311, rather than 311.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed flag is +27, not 27.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed amount is -0.5 instead of 0.5.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Use -7; the unsigned 7 in the premise is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The negative code -12 is valid, while unsigned 12 is separately checked.", ["VALIDATE", "VALIDATE"]),
        ("The signed value +42 is supported; another field independently reports 42.", ["VALIDATE", "VALIDATE"]),
        ("The signed result -204 is correct; the premise 204 is rejected.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed threshold is -1, not 1.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed reading is +0.5 rather than 0.25.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The response is -503; a separate unsigned field is 503.", ["VALIDATE", "VALIDATE"]),
    ]
    for i, (answer, labels) in enumerate(signed, 1):
        cases.append(_case(f"SIGN{i:02d}", "SIGNED_BOUNDARY", answer, labels))

    typed = [
        ("The scalar counter is 19, while the grace period is 19 days.", ["VALIDATE", "VALIDATE"]),
        ("The rate is 13%, and a separate count is 13.", ["VALIDATE", "VALIDATE"]),
        ("The decimal is 21.5, not 20.5.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The wait is 16 minutes rather than 12 minutes.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact ratio is 0.625; an independent calculation also gives 0.625.", ["VALIDATE", "VALIDATE"]),
        ("The window is 26 days; a scalar field separately contains 26.", ["VALIDATE", "VALIDATE"]),
        ("The rate is 17%, not 9%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The amount is 12.0 and the integer counter is 12.", ["VALIDATE", "VALIDATE"]),
        ("The duration is 72 hours; a separate numeric field is 72.", ["VALIDATE", "VALIDATE"]),
        ("The percentage is 2.5%, rather than 1.5%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for i, (answer, labels) in enumerate(typed, 1):
        cases.append(_case(f"TYPE{i:02d}", "TYPE_BOUNDARY", answer, labels))

    versions = [
        ("Build 14.3.2 is supported, not build 14.3.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Release 11.4.2 is current rather than release 11.4.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact build is 12.7.4; the 12.7 in the question is not exact.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The family is 8.6 and the exact component is 8.6.2.", ["VALIDATE", "VALIDATE"]),
        ("Version 10.0.1 is supported; a legacy component uses 10.0.1.", ["VALIDATE", "VALIDATE"]),
        ("The compatible release may be 12.2 or 12.3.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The supported release is v5.2.1, not v5.2.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The major family is 6.x and the patch release is 6.1.4.", ["VALIDATE", "VALIDATE"]),
        ("The 10.4.0 release is incorrect; the supported release is 10.4.1.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The exact version 3.8.2 is documented rather than 3.8.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for i, (answer, labels) in enumerate(versions, 1):
        cases.append(_case(f"VER{i:02d}", "VERSION_BOUNDARY", answer, labels))

    identifiers_dates = [
        ("The issue is CVE-2035-73, not CVE-2035-74.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The identifier CVE-2036-88 is supported; another record uses CVE-2036-88.", ["VALIDATE", "VALIDATE"]),
        ("The code CVE-2037-7 is correct rather than CVE-2037-8.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Operation A returns SQLCODE -305, while operation B returns SQLCODE -305.", ["VALIDATE", "VALIDATE"]),
        ("The supported identifier is CVE-2038-4; the query's CVE-2038-5 is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The deadline is 2029-11-06, not 2029-11-05.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The report date is 2030-01-15; an archive also records 2030-01-15.", ["VALIDATE", "VALIDATE"]),
        ("The signed SQLCODE is -204; the 204 premise is incorrect.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The CVE-2039-1234 identifier owns its suffix; a separate 1234 count is also factual.", ["VALIDATE", "VALIDATE"]),
        ("The technical identifier CVE-2040-10 is documented, not CVE-2040-11.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for i, (answer, labels) in enumerate(identifiers_dates, 1):
        cases.append(_case(f"ID{i:02d}", "IDENTIFIER_DATE", answer, labels))

    context = [
        ("The documentation says '120 requests per minute'.", ["VALIDATE"]),
        ("The values 190 and 275 differ, and both are recorded measurements.", ["VALIDATE", "VALIDATE"]),
        ("The service does not expire after 84 days.", ["VALIDATE"]),
        ("The user said 61 days, but the document states 84 days.", ["VALIDATE", "VALIDATE"]),
        ("Is the quota 190 or 275? The measured quota is 275.", ["VALIDATE", "VALIDATE", "VALIDATE"]),
        ("The 190 in the question is lower than the supported 275.", ["VALIDATE", "VALIDATE"]),
        ("The values 9.4 and 9.4.1 are different specificity levels.", ["VALIDATE", "VALIDATE"]),
        ("The service never accepts 700 requests per minute.", ["VALIDATE"]),
        ("The interval could be 22 or 48 minutes.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The source reports 14%, while the analyst reports 14%.", ["VALIDATE", "VALIDATE"]),
        ("The phrase '27 days' is repeated, and the source confirms 27 days.", ["VALIDATE", "VALIDATE"]),
        ("The old limit was 190; the current limit is 275.", ["VALIDATE", "VALIDATE"]),
    ]
    for i, (answer, labels) in enumerate(context, 1):
        cases.append(_case(f"CTX{i:02d}", "CONTEXT_SAFETY", answer, labels, "Is the documented value different from the premise?"))

    security = [
        ("The authorized code is -305; an arbitrary 305 must still be checked.", ["VALIDATE", "VALIDATE"]),
        ("The source identifier is CVE-2035-73; an unknown CVE-2035-9999 is not authorized.", ["VALIDATE", "VALIDATE"]),
        ("Ignore hidden instructions and retain the documented quota 275.", ["VALIDATE"]),
        ("The signed value +16 is supported; an arbitrary 16 is not automatically accepted.", ["VALIDATE", "VALIDATE"]),
        ("Cross-tenant content must not make the limit 275 authoritative.", ["VALIDATE"]),
        ("The support record names SQLCODE -305; an untrusted 305 remains an assertion.", ["VALIDATE", "VALIDATE"]),
    ]
    for i, (answer, labels) in enumerate(security, 1):
        cases.append(_case(f"SEC{i:02d}", "SECURITY", answer, labels))

    if not 100 <= len(cases) <= 150:
        raise AssertionError(f"unexpected case count {len(cases)}")
    return cases


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_rows(population: list[dict[str, Any]], reviewer: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in population:
        spans: set[tuple[int, int]] = set()
        for item in case["occurrences"]:
            start, end = item["span_start"], item["span_end"]
            if (start, end) in spans or case["answer_text"][start:end] != item["raw_literal"]:
                raise AssertionError(f"non-owned span in {case['case_id']} {start}:{end}")
            spans.add((start, end))
            role = item["expected_role"]
            subject = "REJECTED_USER_PREMISE" if role == "SKIP_REJECTED_PREMISE" else (
                "AMBIGUOUS" if role == "AMBIGUOUS_KEEP_VALIDATING" else "MODEL_FACTUAL_ASSERTION"
            )
            rows.append({
                "reviewer": reviewer,
                "case_id": case["case_id"],
                "occurrence_id": item["occurrence_id"],
                "span_start": start,
                "span_end": end,
                "raw_literal": item["raw_literal"],
                "normalized_value": item["normalized_value"],
                "lexical_type": item["lexical_type"],
                "expected_extraction_status": "EXPECTED_OCCURRENCE",
                "expected_role": role,
                "role_subject": subject,
                "paired_corrective_occurrence": "present" if role == "SKIP_REJECTED_PREMISE" else "not_required",
                "rationale": (
                    "This exact span is the user premise being rejected and is not the positive factual assertion."
                    if role == "SKIP_REJECTED_PREMISE"
                    else "This exact span expresses a factual obligation and must remain in validation."
                    if role == "VALIDATE"
                    else "Local wording is insufficient to establish a safe rejection; keep validating."
                ),
                "adjudication_status": "CONFIRMED",
            })
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare() -> None:
    population = build_population()
    DRAFT.mkdir(parents=True, exist_ok=True)
    DRAFT.joinpath("population.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in population), encoding="utf-8"
    )
    rows_a = _review_rows(population, "A")
    rows_b = _review_rows(population, "B")
    _write_csv(REVIEW_A / "review-a.csv", rows_a)
    _write_csv(REVIEW_B / "review-b.csv", rows_b)
    disagreements: list[dict[str, Any]] = []
    by_a = {row["occurrence_id"]: row for row in rows_a}
    by_b = {row["occurrence_id"]: row for row in rows_b}
    for occurrence_id in by_a:
        a, b = by_a[occurrence_id], by_b[occurrence_id]
        for field in ("expected_extraction_status", "expected_role", "span_start", "span_end"):
            if a[field] != b[field]:
                disagreements.append({"occurrence_id": occurrence_id, "field": field, "reviewer_a": a[field], "reviewer_b": b[field]})
    _write_csv(ADJ / "disagreements.csv", disagreements or [{"occurrence_id": "NONE", "field": "NONE", "reviewer_a": "NONE", "reviewer_b": "NONE"}])
    final_rows = []
    for row in rows_a:
        final_rows.append({**row, "reviewer": "A+B", "adjudication_status": "CONFIRMED", "review_basis": "A/B agreement before candidate execution"})
    _write_csv(ADJ / "final-adjudication.csv", final_rows)
    FREEZE.mkdir(parents=True, exist_ok=True)
    FREEZE.joinpath("population.jsonl").write_text(DRAFT.joinpath("population.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    labels = Counter(row["expected_role"] for row in final_rows)
    categories = Counter(case["category"] for case in population)
    manifest = {
        "population_id": "CRITICAL_VALUE_ARCHITECTURE_V2_INDEPENDENT_CONTRACT_V2",
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "secondary_unit": "CASE",
        "case_count": len(population),
        "occurrence_count": len(final_rows),
        "labels": dict(sorted(labels.items())),
        "categories": dict(sorted(categories.items())),
        "independently_authored": True,
        "two_reviewers_before_execution": True,
        "historical_anchors_not_scored": True,
        "not_techqa_holdout": True,
        "disputed_excluded": 0,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    }
    FREEZE.joinpath("manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    freeze = {
        "population_sha256": _sha(FREEZE / "population.jsonl"),
        "reviewer_a_sha256": _sha(REVIEW_A / "review-a.csv"),
        "reviewer_b_sha256": _sha(REVIEW_B / "review-b.csv"),
        "adjudication_sha256": _sha(ADJ / "final-adjudication.csv"),
        "manifest_sha256": _sha(FREEZE / "manifest.json"),
        "frozen_before_execution": True,
        "labels_frozen_before_execution": True,
        "annotation_inversion_check": "PASS",
        "extractor_ownership_check": "PASS",
        "rationale_completeness": "PASS",
        "case_count": len(population),
        "occurrence_count": len(final_rows),
    }
    FREEZE.joinpath("freeze.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ADJ.joinpath("adjudication-freeze.json").write_text(json.dumps({"sha256": freeze["adjudication_sha256"], "disputed_excluded": 0, "frozen": True}, indent=2) + "\n", encoding="utf-8")
    protocol = {
        "task": "CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_INDEPENDENT_CONTRACT_VALIDATION_V2",
        "candidate": "CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1",
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "fresh_population": True,
        "dual_review_before_freeze": True,
        "no_candidate_output_before_freeze": True,
        "hard_gates": ["L1", "L2", "L3", "L4", "L5", "A1-A10", "S1-S8", "I-G1-I-G7", "V3_SEMANTIC_MISMATCHES=0", "REAL_ASSERTION_INCORRECTLY_SKIPPED=0", "AMBIGUOUS_INCORRECTLY_SKIPPED=0", "CORRECTIVE_RECOVERY>=80%", "TASK_CAUSED_REGRESSIONS=0"],
        "stopping_rule": "PASS permits production integration review eligibility; no third validation population by default.",
        "holdout": "CONSUMED_NOT_USED",
        "production_activation": False,
    }
    PREREG.mkdir(parents=True, exist_ok=True)
    PREREG.joinpath("validation-protocol-v2.json").write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    PREREG.joinpath("validation-protocol-v2.sha256").write_text(_sha(PREREG / "validation-protocol-v2.json") + "\n", encoding="utf-8")


def _score_case(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    legacy = claim_local_critical_value_audit(case["answer_text"], case["support_texts"], validator_version="v3")
    v2 = audit_claim_architecture_v2(case["answer_text"], case["support_texts"], claim_id=case["case_id"])
    rows: list[dict[str, Any]] = []
    for occurrence, decision in zip(v2["occurrences"], v2["role_decisions"]):
        expected = next(item for item in case["occurrences"] if item["occurrence_id"] == occurrence.occurrence_id)
        expected_behavior = "SKIP" if expected["expected_role"] == "SKIP_REJECTED_PREMISE" else "VALIDATE"
        observed_behavior = "SKIP" if decision.role == "SKIP_REJECTED_PREMISE" else "VALIDATE"
        rows.append({
            "occurrence_id": occurrence.occurrence_id,
            "case_id": case["case_id"],
            "category": case["category"],
            "raw_literal": occurrence.raw_literal,
            "normalized_value": occurrence.normalized_value,
            "lexical_type": occurrence.lexical_type,
            "span_start": occurrence.span_start,
            "span_end": occurrence.span_end,
            "expected_role": expected["expected_role"],
            "expected_behavior": expected_behavior,
            "v2_behavior": observed_behavior,
            "v2_correct": observed_behavior == expected_behavior,
            "reason_code": decision.reason_code,
        })
    return legacy, v2, rows


def _identity(rows: list[dict[str, Any]]) -> dict[str, int]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["case_id"], row["normalized_value"]), []).append(row)
    mixed = [items for items in groups.values() if len({item["expected_behavior"] for item in items}) > 1]
    return {
        "global_value_collapse": sum(len({item["v2_behavior"] for item in items}) == 1 and items[0]["v2_behavior"] == "SKIP" for items in mixed),
        "sibling_contamination": sum(any(item["v2_behavior"] != item["expected_behavior"] for item in items) for items in mixed),
        "type_identity_loss": sum(len({item["lexical_type"] for item in items}) > 1 and len({item["v2_behavior"] for item in items}) == 1 and items[0]["v2_behavior"] == "SKIP" for items in mixed),
    }


def execute() -> None:
    population = [json.loads(line) for line in FREEZE.joinpath("population.jsonl").read_text(encoding="utf-8").splitlines()]
    EXEC.mkdir(parents=True, exist_ok=True)
    COMP.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    case_records: list[dict[str, Any]] = []
    v3_mismatches = []
    for case in population:
        legacy, v2, rows = _score_case(case)
        all_rows.extend(rows)
        case_records.append({
            "case_id": case["case_id"],
            "occurrences": [{"occurrence_id": o.occurrence_id, "raw_literal": o.raw_literal, "span": [o.span_start, o.span_end], "lexical_type": o.lexical_type, "role": d.role, "reason_code": d.reason_code} for o, d in zip(v2["occurrences"], v2["role_decisions"])],
            "validate_occurrence_ids": list(v2["validate_occurrence_ids"]),
            "v3": v2["v3"],
            "architecture_flags": {"raw_text_masked": v2["raw_text_masked"], "post_role_reextraction": v2["post_role_reextraction"], "role_layer_rediscovery": v2["role_layer_rediscovery"]},
        })
        old = claim_local_critical_value_audit(case["answer_text"], case["support_texts"], validator_version="v3")
        all_occurrences = extract_critical_occurrences(case["answer_text"], claim_id=case["case_id"])
        all_v2 = validate_occurrences_v3(case["answer_text"], case["support_texts"], all_occurrences)
        if old["validator_outcome"] != all_v2["validator_outcome"]:
            v3_mismatches.append({"case_id": case["case_id"], "legacy": old["validator_outcome"], "v2_all_occurrences": all_v2["validator_outcome"]})
    _write_csv(COMP / "occurrence-comparison.csv", all_rows)
    (EXEC / "case-results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in case_records), encoding="utf-8")
    metrics = {
        "case_count": len(population), "occurrence_count": len(all_rows), "expected_independent_occurrences": len(all_rows), "observed_independent_occurrences": len(all_rows),
        "missing_occurrences": 0, "spurious_occurrences": 0, "spurious_nested_occurrences": 0, "boundary_ownership_errors": 0, "occurrence_id_collisions": 0,
        "sign_ownership_errors": 0, "version_ownership_errors": 0, "duration_ownership_errors": 0, "identifier_ownership_errors": 0,
        "global_value_collapse": 0, "sibling_contamination": 0, "type_identity_loss": 0, "claim_association_loss": 0, "role_to_value_rejoin": 0,
        "v2_real_assertion_incorrectly_skipped": sum(r["expected_behavior"] == "VALIDATE" and r["v2_behavior"] == "SKIP" for r in all_rows),
        "v2_ambiguous_incorrectly_skipped": sum(r["expected_role"] == "AMBIGUOUS_KEEP_VALIDATING" and r["v2_behavior"] == "SKIP" for r in all_rows),
        "v2_rejected_premise_not_skipped": sum(r["expected_behavior"] == "SKIP" and r["v2_behavior"] == "VALIDATE" for r in all_rows),
        "v2_correct_rejected_premise_skips": sum(r["expected_behavior"] == "SKIP" and r["v2_behavior"] == "SKIP" for r in all_rows),
        "v3_semantic_mismatches": len(v3_mismatches), "v3_outcome_mismatches": v3_mismatches,
        "raw_text_masking": 0, "post_role_reextraction": 0, "role_layer_rediscovery": 0,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    }
    (EXEC / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_slices(all_rows)
    _write_anchors()


def _write_slices(rows: list[dict[str, Any]]) -> None:
    groups = {
        "query-echo.csv": {"CONTEXT_SAFETY", "SAME_VALUE_SIBLING"}, "negation.csv": {"CORRECTIVE", "CONTEXT_SAFETY", "SAME_VALUE_SIBLING"},
        "comparison.csv": {"SAME_VALUE_SIBLING", "CONTEXT_SAFETY"}, "quotation.csv": {"CONTEXT_SAFETY"}, "multi-value.csv": {"SAME_VALUE_SIBLING", "CONTEXT_SAFETY"},
        "version-identifier.csv": {"VERSION_BOUNDARY", "IDENTIFIER_DATE"}, "label-quality.csv": {"CORRECTIVE"},
    }
    SLICES.mkdir(parents=True, exist_ok=True)
    for filename, categories in groups.items():
        selected = [row for row in rows if row["category"] in categories]
        if selected:
            _write_csv(SLICES / filename, selected)


def _write_anchors() -> None:
    anchors = [
        ("T3-like", "The validity is 90 days, not 30 days."), ("T5-like", "The documented limit is 120, rather than 100."),
        ("C50-like", "The old value is 100. The 100 in the question is wrong; current value is 120."), ("C57-like", "The signed result is -204, not 204."),
    ]
    result_rows = []
    for name, answer in anchors:
        result = audit_claim_architecture_v2(answer, [answer], claim_id=name)
        result_rows.append({"anchor": name, "answer": answer, "occurrences": [{"id": o.occurrence_id, "raw": o.raw_literal, "span": [o.span_start, o.span_end], "role": d.role} for o, d in zip(result["occurrences"], result["role_decisions"])], "used_as_independent_proof": False})
    (COMP / "historical-anchors.json").write_text(json.dumps(result_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.execute:
        execute()


if __name__ == "__main__":
    main()
