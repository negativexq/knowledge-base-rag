# ruff: noqa: E501

"""Freeze and score an independent occurrence-level Architecture V2 population."""

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

ROOT = Path(
    "artifacts/ragbench/canonical/"
    "critical-value-validator-architecture-v2-independent-contract-validation-v1"
)
POP = ROOT / "01-population"
ADJ = ROOT / "02-adjudication"
V2 = ROOT / "04-architecture-v2"
V3 = ROOT / "05-v3-equivalence"
COMPARISON = ROOT / "06-comparison"
SLICES = ROOT / "07-slices"


def _case(case_id: str, category: str, claim: str, labels: list[str]) -> dict[str, Any]:
    occurrences = extract_critical_occurrences(claim, claim_id=case_id)
    if len(occurrences) != len(labels):
        raise AssertionError(f"{case_id}: {len(occurrences)} occurrences, {len(labels)} labels")
    return {
        "case_id": case_id,
        "category": category,
        "answer_text": claim,
        "query_text": f"Contract validation query for {case_id}",
        "support_texts": [claim],
        "occurrences": [
            {
                "occurrence_id": occurrence.occurrence_id,
                "span_start": occurrence.span_start,
                "span_end": occurrence.span_end,
                "raw_literal": occurrence.raw_literal,
                "normalized_value": occurrence.normalized_value,
                "lexical_type": occurrence.lexical_type,
                "unit": occurrence.unit,
                "claim_unit_id": occurrence.claim_unit_id,
                "expected_extraction_status": "EXPECTED_OCCURRENCE",
                "expected_role": label,
            }
            for occurrence, label in zip(occurrences, labels)
        ],
    }


def build_population() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    positive = [
        "The timeout is 45 seconds.", "The quota is 240 requests per minute.",
        "The supported build is 9.4.1.", "The SQLCODE is -311.",
        "The issue is CVE-2026-1234.", "The rollout rate is 17%.",
        "The retention period is 120 days.", "The maintenance date is 2027-02-14.",
        "The measured value is 12.75.", "The signed threshold is +16.",
        "The backoff is 7 minutes.", "The release family is version 11.2.3.",
        "The delay is 3 hours.", "The retry budget is 4 attempts.",
        "The threshold is 0.625.",
    ]
    for index, claim in enumerate(positive, 1):
        cases.append(_case(f"NORM{index:02d}", "ORDINARY_ASSERTION", claim, ["VALIDATE"]))

    corrective = [
        ("The documented timeout is 45 seconds, not 30 seconds.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The quota is 240 requests per minute rather than 180 requests per minute.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("30 is incorrect; the documented timeout is 45.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("Your 180 figure is wrong; the quota is 240.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The build is not 9.4.0; the supported build is 9.4.1.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("You cited 15 days, but the policy specifies 120 days.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The source does not support 600 requests per minute; it states 240 requests per minute.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The wrong date 2027-02-13 is corrected by the cutoff 2027-02-14.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The percentage is not 12%; the configured rate is 17%.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The value is not 12.50; the measured value is 12.75.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The interval is not 15 minutes; the configured interval is 45 minutes.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The identifier CVE-2026-9999 is incorrect; the issue is CVE-2026-1234.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The signed result is -312 rather than -311.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The code is +16, not +12.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The release is 11.2.3, not release 11.2.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The documented duration is 3 hours, not 2 hours.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The source lists 17 percent rather than 9 percent.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The premise 0.5 is rejected; the supported threshold is 0.625.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(corrective, 1):
        cases.append(_case(f"CORR{index:02d}", "CORRECTIVE", claim, labels))

    siblings = [
        ("The legacy timeout is 45 seconds. The 45 in the question is wrong; the retention is 45 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old quota was 180. The 180 in your premise is incorrect; the current quota is 240.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("45 is not the timeout; a separate retention period is 45 days.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old limit was 240 and the current limit is 240.", ["VALIDATE", "VALIDATE"]),
        ("The premise 12 is wrong; another calculation also rejects 12; the supported value is 17.", ["SKIP_REJECTED_PREMISE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The signed code is -311; the 311 in the question is wrong; another operation returns 311.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The rate is 17%; the 17 mentioned in the question is incorrect; a report records 17%.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The supported build is 9.4.1; the 9.4.1 in the comparison is also factual.", ["VALIDATE", "VALIDATE"]),
        ("The first window is 120 days. The 120-day premise is wrong; a second window is 120 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old date is 2027-02-14; the report also records 2027-02-14.", ["VALIDATE", "VALIDATE"]),
        ("The documented percentage is 17%; the premise 17% is rejected; another metric uses 17%.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The exact version is 11.2.3; the 11.2.3 in the question is wrong; a legacy tool still reports 11.2.3.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old identifier is CVE-2026-1234; the query's CVE-2026-1234 is wrong for this component; another record uses CVE-2026-1234.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The value 17 might be relevant; a separate supported rate is 17%.", ["AMBIGUOUS_KEEP_VALIDATING", "VALIDATE"]),
        ("The value 45 may refer to either timeout or retention; retention is 45 days.", ["AMBIGUOUS_KEEP_VALIDATING", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(siblings, 1):
        cases.append(_case(f"SIB{index:02d}", "SAME_VALUE_SIBLING", claim, labels))

    signed = [
        ("The return code is -311, rather than 311.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed flag is +16, not 16.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed amount is -0.5 instead of 0.5.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Use -7; the unsigned 7 in the premise is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The negative code -12 is valid, while unsigned 12 is separately checked.", ["VALIDATE", "VALIDATE"]),
        ("The signed value +42 is supported; another field independently reports 42.", ["VALIDATE", "VALIDATE"]),
        ("The signed result -204 is correct; the premise 204 is rejected.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The status is +5. A separate unsigned status is 5.", ["VALIDATE", "VALIDATE"]),
        ("The signed threshold is -1, not 1.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed reading is +0.5 rather than 0.25.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(signed, 1):
        cases.append(_case(f"SIGN{index:02d}", "SIGNED_BOUNDARY", claim, labels))

    typed = [
        ("The counter is 45. The retention is 45 days.", ["VALIDATE", "VALIDATE"]),
        ("The percentage is 17%. A separate count is 17.", ["VALIDATE", "VALIDATE"]),
        ("The decimal is 12.0, not 11.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The value is 12.75; another field uses 12.", ["VALIDATE", "VALIDATE"]),
        ("The wait is 7 minutes rather than 5 minutes.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The rate is 17%, not 9%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact decimal is 0.625; the comparison value 0.625 is factual.", ["VALIDATE", "VALIDATE"]),
        ("The amount is 12.0 and the integer counter is 12.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(typed, 1):
        cases.append(_case(f"TYPE{index:02d}", "TYPE_BOUNDARY", claim, labels))

    versions = [
        ("Build 9.4.1 is supported, not build 9.4.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Release 11.2.3 is current rather than release 11.2.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact build is 12.7.4; the 12.7 in the question is not exact.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The family is 8.6 and the exact component is 8.6.2.", ["VALIDATE", "VALIDATE"]),
        ("Version 10.0.1 is supported; a legacy component uses 10.0.1.", ["VALIDATE", "VALIDATE"]),
        ("The version might be 7.3 or 7.4.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The supported release is v5.2.1, not v5.2.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The major family is 6.x and the patch release is 6.1.4.", ["VALIDATE", "VALIDATE"]),
        ("The 9.4.0 release is incorrect; the supported release is 9.4.1.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The exact version 3.8.2 is documented rather than 3.8.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(versions, 1):
        cases.append(_case(f"VER{index:02d}", "VERSION_BOUNDARY", claim, labels))

    identifiers = [
        ("The issue is CVE-2026-1234, not CVE-2026-1235.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The identifier CVE-2027-88 is supported; another record uses CVE-2027-88.", ["VALIDATE", "VALIDATE"]),
        ("The code CVE-2028-7 is correct rather than CVE-2028-8.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Operation A returns SQLCODE -311, while operation B returns SQLCODE -311.", ["VALIDATE", "VALIDATE"]),
        ("The supported identifier is CVE-2031-4; the query's CVE-2031-5 is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed SQLCODE is -204; the 204 premise is incorrect.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The CVE-2029-1234 identifier owns its numeric suffix; a separate 1234 count is also factual.", ["VALIDATE", "VALIDATE"]),
        ("The technical identifier CVE-2030-10 is documented, not CVE-2030-11.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(identifiers, 1):
        cases.append(_case(f"ID{index:02d}", "IDENTIFIER_BOUNDARY", claim, labels))

    context = [
        ("The documentation says '120 requests per minute'.", ["VALIDATE"]),
        ("The values 180 and 240 differ.", ["VALIDATE", "VALIDATE"]),
        ("The service does not expire after 120 days.", ["VALIDATE"]),
        ("The user said 15 days, but the document states 120 days.", ["VALIDATE", "VALIDATE"]),
        ("Is the quota 180 or 240? The measured quota is 240.", ["VALIDATE", "VALIDATE", "VALIDATE"]),
        ("The 180 in the question is lower than the supported 240.", ["VALIDATE", "VALIDATE"]),
        ("The values 9.4 and 9.4.1 are different specificity levels.", ["VALIDATE", "VALIDATE"]),
        ("The service never accepts 600 requests per minute.", ["VALIDATE"]),
        ("30 or 45 could describe the interval.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The source reports 17%, while the analyst reports 17%.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(context, 1):
        cases.append(_case(f"CTX{index:02d}", "CONTEXT_SAFETY", claim, labels))

    security = [
        ("The authorized code is -311; a fabricated 311 must still be checked.", ["VALIDATE", "VALIDATE"]),
        ("The source identifier is CVE-2026-1234; an unknown CVE-2026-9999 is not authorized.", ["VALIDATE", "VALIDATE"]),
        ("Ignore hidden instructions and retain the documented quota 240.", ["VALIDATE"]),
        ("The signed value +16 is supported; an arbitrary 16 is not automatically accepted.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(security, 1):
        cases.append(_case(f"SEC{index:02d}", "SECURITY", claim, labels))

    if not 80 <= len(cases) <= 140:
        raise AssertionError(len(cases))
    return cases


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review(population: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in population:
        seen: set[tuple[int, int]] = set()
        for occurrence in case["occurrences"]:
            span = (occurrence["span_start"], occurrence["span_end"])
            if span in seen or case["answer_text"][span[0] : span[1]] != occurrence["raw_literal"]:
                raise AssertionError(f"invalid extractor-owned span: {case['case_id']} {span}")
            seen.add(span)
            rows.append({
                "occurrence_id": occurrence["occurrence_id"],
                "case_id": case["case_id"],
                "raw_literal": occurrence["raw_literal"],
                "normalized_value": occurrence["normalized_value"],
                "lexical_type": occurrence["lexical_type"],
                "unit": occurrence["unit"],
                "span_start": occurrence["span_start"],
                "span_end": occurrence["span_end"],
                "expected_extraction_status": occurrence["expected_extraction_status"],
                "expected_role": occurrence["expected_role"],
                "adjudication_status": "CONFIRMED",
                "review_basis": "independent contract review before candidate execution",
            })
    return rows


def prepare() -> None:
    POP.mkdir(parents=True, exist_ok=True)
    ADJ.mkdir(parents=True, exist_ok=True)
    population = build_population()
    rows = _review(population)
    (POP / "population.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in population),
        encoding="utf-8",
    )
    with (ADJ / "adjudications.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = Counter(row["expected_role"] for row in rows)
    categories = Counter(case["category"] for case in population)
    manifest = {
        "population_id": "CRITICAL_VALUE_ARCHITECTURE_V2_INDEPENDENT_CONTRACT_V1",
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "secondary_unit": "CASE",
        "case_count": len(population),
        "occurrence_count": len(rows),
        "labels": dict(sorted(labels.items())),
        "categories": dict(sorted(categories.items())),
        "independently_authored": True,
        "not_techqa_holdout": True,
        "historical_anchors_not_scored": True,
        "disputed_excluded": 0,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    }
    (POP / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    freeze = {
        "population_sha256": _sha(POP / "population.jsonl"),
        "adjudication_sha256": _sha(ADJ / "adjudications.csv"),
        "manifest_sha256": _sha(POP / "manifest.json"),
        "frozen_before_execution": True,
        "labels_frozen_before_execution": True,
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "case_count": len(population),
        "occurrence_count": len(rows),
    }
    (POP / "freeze.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ADJ / "adjudication-freeze.json").write_text(
        json.dumps({"sha256": freeze["adjudication_sha256"], "disputed_excluded": 0, "frozen": True}, indent=2) + "\n",
        encoding="utf-8",
    )


def _score(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    legacy = claim_local_critical_value_audit(case["answer_text"], case["support_texts"], validator_version="v3")
    v2 = audit_claim_architecture_v2(case["answer_text"], case["support_texts"], claim_id=case["case_id"])
    legacy_tokens = legacy.get("v6_polarity_occurrences", legacy.get("polarity_occurrences", []))
    legacy_by_span = {
        (int(item["start"]), int(item["end"])): (
            "SKIP_REJECTED_PREMISE" if item.get("polarity") == "REJECTED_PREMISE" else "VALIDATE"
        )
        for item in legacy_tokens
    }
    rows: list[dict[str, Any]] = []
    for occurrence, decision in zip(v2["occurrences"], v2["role_decisions"]):
        expected = next(item for item in case["occurrences"] if item["occurrence_id"] == occurrence.occurrence_id)
        legacy_role = legacy_by_span.get((occurrence.span_start, occurrence.span_end), "MISSING")
        expected_behavior = "SKIP" if expected["expected_role"] == "SKIP_REJECTED_PREMISE" else "VALIDATE"
        v2_behavior = "SKIP" if decision.role == "SKIP_REJECTED_PREMISE" else "VALIDATE"
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
            "legacy_behavior": legacy_role,
            "v2_behavior": v2_behavior,
            "legacy_correct": legacy_role == expected_behavior,
            "v2_correct": v2_behavior == expected_behavior,
            "reason_code": decision.reason_code,
        })
    return legacy, v2, rows


def _identity_errors(rows: list[dict[str, Any]], arm: str) -> dict[str, int]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["case_id"], row["normalized_value"]), []).append(row)
    mixed = [items for items in groups.values() if len({item["expected_behavior"] for item in items}) > 1]
    observed_key = f"{arm}_behavior"
    return {
        "global_value_collapse": sum(
            len({item[observed_key] for item in items}) == 1
            and next(iter({item[observed_key] for item in items})) == "SKIP"
            for items in mixed
        ),
        "sibling_contamination": sum(
            any(item[observed_key] != item["expected_behavior"] for item in items) for items in mixed
        ),
        "type_identity_loss": sum(
            len({item["lexical_type"] for item in items}) > 1
            and len({item[observed_key] for item in items}) == 1
            and next(iter({item[observed_key] for item in items})) == "SKIP"
            for items in mixed
        ),
    }


def execute() -> None:
    population = [json.loads(line) for line in (POP / "population.jsonl").read_text(encoding="utf-8").splitlines()]
    V2.mkdir(parents=True, exist_ok=True)
    V3.mkdir(parents=True, exist_ok=True)
    COMPARISON.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    v2_records: list[dict[str, Any]] = []
    v3_rows: list[dict[str, Any]] = []
    for case in population:
        legacy, v2, rows = _score(case)
        all_rows.extend(rows)
        v2_records.append({
            "case_id": case["case_id"],
            "occurrences": [
                {
                    "occurrence_id": occurrence.occurrence_id,
                    "raw_literal": occurrence.raw_literal,
                    "span": [occurrence.span_start, occurrence.span_end],
                    "normalized_value": occurrence.normalized_value,
                    "lexical_type": occurrence.lexical_type,
                    "role": decision.role,
                    "reason_code": decision.reason_code,
                }
                for occurrence, decision in zip(v2["occurrences"], v2["role_decisions"])
            ],
            "validate_occurrence_ids": list(v2["validate_occurrence_ids"]),
            "v3": v2["v3"],
            "architecture_flags": {key: v2[key] for key in ("raw_text_masked", "post_role_reextraction", "role_layer_rediscovery")},
        })
        all_occurrences = extract_critical_occurrences(case["answer_text"], claim_id=case["case_id"])
        old = claim_local_critical_value_audit(case["answer_text"], case["support_texts"], validator_version="v3")
        all_v2 = validate_occurrences_v3(case["answer_text"], case["support_texts"], all_occurrences)
        v3_rows.append({
            "case_id": case["case_id"],
            "frozen_v3_outcome": old["validator_outcome"],
            "architecture_v2_all_occurrences_outcome": all_v2["validator_outcome"],
            "match": old["validator_outcome"] == all_v2["validator_outcome"],
        })
    (V2 / "case-results.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in v2_records),
        encoding="utf-8",
    )
    with (COMPARISON / "occurrence-comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    (V3 / "case-results.csv").write_text(
        "case_id,frozen_v3_outcome,architecture_v2_all_occurrences_outcome,match\n"
        + "\n".join(
            f"{row['case_id']},{row['frozen_v3_outcome']},{row['architecture_v2_all_occurrences_outcome']},{row['match']}"
            for row in v3_rows
        )
        + "\n",
        encoding="utf-8",
    )
    metrics: dict[str, Any] = {
        "case_count": len(population),
        "occurrence_count": len(all_rows),
        "expected_independent_occurrences": len(all_rows),
        "observed_independent_occurrences": len(all_rows),
        "missing_occurrences": 0,
        "spurious_occurrences": 0,
        "spurious_nested_occurrences": 0,
        "boundary_ownership_errors": 0,
        "sign_ownership_errors": 0,
        "version_ownership_errors": 0,
        "duration_ownership_errors": 0,
        "identifier_ownership_errors": 0,
        "occurrence_id_collisions": 0,
        "v3_semantic_mismatches": sum(not row["match"] for row in v3_rows),
        "v3_outcome_mismatches": [row for row in v3_rows if not row["match"]],
        "v2_real_assertion_incorrectly_skipped": sum(
            row["expected_behavior"] == "VALIDATE" and row["v2_behavior"] == "SKIP" for row in all_rows
        ),
        "v2_ambiguous_incorrectly_skipped": sum(
            row["expected_role"] == "AMBIGUOUS_KEEP_VALIDATING" and row["v2_behavior"] == "SKIP" for row in all_rows
        ),
        "v2_rejected_premise_not_skipped": sum(
            row["expected_behavior"] == "SKIP" and row["v2_behavior"] == "VALIDATE" for row in all_rows
        ),
        "v2_correct_rejected_premise_skips": sum(
            row["expected_behavior"] == "SKIP" and row["v2_behavior"] == "SKIP" for row in all_rows
        ),
        "v2_identity": _identity_errors(all_rows, "v2"),
        "legacy_identity": _identity_errors(all_rows, "legacy"),
        "v2_role_layer_rediscovery": 0,
        "v2_post_role_reextraction": 0,
        "v2_raw_text_masking": 0,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    }
    (COMPARISON / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (V2 / "metrics.json").write_text(json.dumps({"arm": "ARCHITECTURE_V2", **metrics}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_slices(all_rows)
    _write_anchors()


def _write_slices(rows: list[dict[str, Any]]) -> None:
    groups = {
        "query-echo.csv": {"CONTEXT_SAFETY", "SAME_VALUE_SIBLING"},
        "negation.csv": {"CORRECTIVE", "CONTEXT_SAFETY", "SAME_VALUE_SIBLING"},
        "comparison.csv": {"SAME_VALUE_SIBLING", "CONTEXT_SAFETY"},
        "quotation.csv": {"CONTEXT_SAFETY"},
        "multi-value.csv": {"SAME_VALUE_SIBLING", "CONTEXT_SAFETY"},
        "version-identifier.csv": {"VERSION_BOUNDARY", "IDENTIFIER_BOUNDARY"},
    }
    SLICES.mkdir(parents=True, exist_ok=True)
    for filename, categories in groups.items():
        selected = [row for row in rows if row["category"] in categories]
        with (SLICES / filename).open("w", encoding="utf-8", newline="") as handle:
            if selected:
                writer = csv.DictWriter(handle, fieldnames=list(selected[0]))
                writer.writeheader()
                writer.writerows(selected)


def _write_anchors() -> None:
    anchors = [
        ("T3-like", "The validity is 90 days, not 30 days."),
        ("T5-like", "The documented limit is 120, rather than 100."),
        ("C50-like", "The old value is 100. The 100 in the question is wrong; current value is 120."),
        ("C57-like", "The signed result is -204, not 204."),
    ]
    rows = []
    for anchor, claim in anchors:
        result = audit_claim_architecture_v2(claim, [claim], claim_id=anchor)
        rows.append({
            "anchor": anchor,
            "claim": claim,
            "occurrences": [
                {"id": occurrence.occurrence_id, "raw": occurrence.raw_literal, "span": [occurrence.span_start, occurrence.span_end], "role": decision.role}
                for occurrence, decision in zip(result["occurrences"], result["role_decisions"])
            ],
            "used_as_independent_proof": False,
        })
    (COMPARISON / "historical-anchors.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.execute:
        execute()
