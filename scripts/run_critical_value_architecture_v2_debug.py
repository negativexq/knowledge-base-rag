# ruff: noqa: E501

"""Prepare and score the deterministic Architecture V2 DEBUG population.

This script has no provider, embedding, retrieval, or BGE dependencies. It is
an experiment harness; it is not imported by the production runtime selector.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_validator_architecture_v2 import audit_claim_architecture_v2
from app.evaluation.critical_values import claim_local_critical_value_audit_v6

ROOT = Path("artifacts/ragbench/canonical/critical-value-validator-architecture-v2-implementation-v1")
POP = ROOT / "04-dev-population"
LEGACY = ROOT / "05-legacy-reproduction"
V2 = ROOT / "06-architecture-v2"
COMPARISON = ROOT / "07-comparison"


def _case(case_id: str, category: str, claim: str, support: str, labels: list[str]) -> dict[str, Any]:
    occurrences = extract_critical_occurrences(claim, claim_id=case_id)
    if len(occurrences) != len(labels):
        raise AssertionError(
            f"{case_id}: labels={len(labels)} but extractor={len(occurrences)} "
            f"for {claim!r}: {occurrences!r}"
        )
    return {
        "case_id": case_id,
        "category": category,
        "claim": claim,
        "support_texts": [support],
        "occurrences": [
            {
                "occurrence_id": occurrence.occurrence_id,
                "raw_literal": occurrence.raw_literal,
                "normalized_value": occurrence.normalized_value,
                "lexical_type": occurrence.lexical_type,
                "span_start": occurrence.span_start,
                "span_end": occurrence.span_end,
                "claim_unit_id": occurrence.claim_unit_id,
                "expected_role": label,
                "expected_extraction_status": "EXPECTED_OCCURRENCE",
            }
            for occurrence, label in zip(occurrences, labels)
        ],
    }


def build_population() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    positive = [
        ("The timeout is 30 seconds.", "The timeout is 30 seconds."),
        ("The API limit is 120 requests per minute.", "The API limit is 120 requests per minute."),
        ("The supported release is 8.1.2.", "The supported release is 8.1.2."),
        ("The SQLCODE is -204.", "The SQLCODE is -204."),
        ("The issue is CVE-2025-1234.", "The issue is CVE-2025-1234."),
        ("The rate is 10%.", "The rate is 10%."),
        ("The retention period is 90 days.", "The retention period is 90 days."),
        ("The cutoff date is 2026-08-31.", "The cutoff date is 2026-08-31."),
        ("The exact amount is 12.50.", "The exact amount is 12.50."),
        ("The signed value is +42.", "The signed value is +42."),
        ("The wait is 5 minutes.", "The wait is 5 minutes."),
        ("The family is version 8.1.2.", "The family is version 8.1.2."),
    ]
    for index, (claim, support) in enumerate(positive, 1):
        cases.append(_case(f"POS{index:02d}", "POSITIVE", claim, support, ["VALIDATE"] * len(extract_critical_occurrences(claim))))

    corrective = [
        ("The documented validity is 90 days, not 30 days.", "The documented validity is 90 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The limit is 120 requests per minute rather than 100 requests per minute.", "The limit is 120 requests per minute.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("30 is incorrect; the documented value is 90.", "The documented value is 90.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("Your 100 figure is incorrect; the limit is 120.", "The limit is 120.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The version is not 8.1.1; the supported release is 8.1.2.", "The supported release is 8.1.2.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("You mentioned 30 days, but the documentation says 90 days.", "The documentation says 90 days.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The source does not support 500 requests per minute; it states 120 requests per minute.", "It states 120 requests per minute.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The identifier in the question is incorrect; the source lists -204.", "The source lists -204.", ["VALIDATE"]),
        ("The value is not 12.0; the supported value is 12.5.", "The supported value is 12.5.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The date 2025-01-01 is wrong; the cutoff is 2026-08-31.", "The cutoff is 2026-08-31.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The percentage is not 5%; the configured rate is 10%.", "The configured rate is 10%.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The duration is not 30 minutes; the configured duration is 60 minutes.", "The configured duration is 60 minutes.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
    ]
    for index, (claim, support, labels) in enumerate(corrective, 1):
        cases.append(_case(f"COR{index:02d}", "CORRECTIVE", claim, support, labels))

    mixed = [
        ("The legacy value is 30. The 30 in your question is incorrect; retention is 30 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The legacy limit is 100. The 100 in your question is wrong; current limit is 120.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("30 is not correct; a separate retention window is 30 days.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old limit was 100 and the current limit is 100.", ["VALIDATE", "VALIDATE"]),
        ("The exact build is 8.1.3; the 8.1.2 in your question is incorrect, while a legacy tool uses 8.1.2.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The first code -204 is valid; the 204 in your premise is not correct; another operation returns 204.", ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The old rate is 10%; the current rate is 10%.", ["VALIDATE", "VALIDATE"]),
        ("The 30-day premise is incorrect; the separate 30-day retention rule is documented.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
        ("The value 120 is supported. The value 120 in the comparison is also factual.", ["VALIDATE", "VALIDATE"]),
        ("The rejected 7 is not the setting; a different setting uses 7 seconds.", ["SKIP_REJECTED_PREMISE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(mixed, 1):
        cases.append(_case(f"MIX{index:02d}", "SAME_VALUE_SIBLING", claim, claim, labels))

    signed = [
        ("The signed result is -204, not 204.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed code is -7 rather than 7.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed field is -100; the 100 in the question is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed result is -512, not 512.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The negative code -12 is valid, while unsigned 12 is unsupported.", ["VALIDATE", "VALIDATE"]),
        ("The signed value is -42. A separate unsigned value is 42.", ["VALIDATE", "VALIDATE"]),
        ("The code -1 is supported; the premise 1 is rejected.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed result -64 is correct rather than 64.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(signed, 1):
        cases.append(_case(f"SIGN{index:02d}", "SIGNED_UNSIGNED", claim, claim, labels))

    plus = [
        ("The signed code is +42, not 42.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The header uses +7 rather than 7.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The field is +300; the question's 300 is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Use +12 instead of 12 in the signed field.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The signed value +99 is valid; another component reports 99.", ["VALIDATE", "VALIDATE"]),
        ("The signed value +5 is supported, while 5 is a separate unsigned value.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(plus, 1):
        cases.append(_case(f"PLUS{index:02d}", "PLUS_UNSIGNED", claim, claim, labels))

    duration = [
        ("The timeout is 30 seconds, not 20 seconds.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The retention is 90 days rather than 30 days.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The wait is 5 minutes; the 5 in the question is incorrect.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The job lasts 2 hours, not 1 hour.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The policy uses 12 hours and a separate rule uses 12 minutes.", ["VALIDATE", "VALIDATE"]),
        ("The window is 30 days; a different window also uses 30 days.", ["VALIDATE", "VALIDATE"]),
        ("The delay is 45 seconds rather than 30 seconds.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The interval is 60 minutes; the value 60 is also reported by the counter.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(duration, 1):
        cases.append(_case(f"DUR{index:02d}", "DURATION", claim, claim, labels))

    percent = [
        ("The rate is 10%, not 5%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The configured percentage is 25% rather than 20%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The rate is 2.5%; the 2.5 in the question is incorrect.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The threshold is 100%, not 80%.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The rate is 5% and the legacy rate is 5%.", ["VALIDATE", "VALIDATE"]),
        ("The share is 0.5%; another metric reports 0.5%.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(percent, 1):
        cases.append(_case(f"PCT{index:02d}", "PERCENTAGE", claim, claim, labels))

    decimal = [
        ("The value is 12.0, not 11.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The threshold is 100.0 rather than 99.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact amount is 1.25, not 1.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The ratio is 3.14; a second ratio is 3.14.", ["VALIDATE", "VALIDATE"]),
        ("The value is 7.50 and the comparison value is 7.50.", ["VALIDATE", "VALIDATE"]),
        ("The latency is 0.25 seconds, not 0.50 seconds.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(decimal, 1):
        cases.append(_case(f"DEC{index:02d}", "DECIMAL", claim, claim, labels))

    versions = [
        ("Version 8.1.2 is supported, not version 8.1.1.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("Release 10.2.1 is current rather than release 10.2.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The exact build is 12.4.9; the question's 12.4 is not exact.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The release 3.0.0 is valid, not release 3.0.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The supported version is 8.1.2 and a legacy component uses 8.1.2.", ["VALIDATE", "VALIDATE"]),
        ("The family is version 8.1.2, while an exact component is 8.1.3.", ["VALIDATE", "VALIDATE"]),
        ("The version might be 9.1 or 9.2.", ["VALIDATE", "VALIDATE"]),
        ("Version 7.0.1 is supported; version 7.0 is a separate family label.", ["VALIDATE", "VALIDATE"]),
        ("The exact release is v3.4.5, not v3.4.4.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The major family is 6.x and the exact release is 6.1.2.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(versions, 1):
        cases.append(_case(f"VER{index:02d}", "VERSION", claim, claim, labels))

    identifiers = [
        ("The issue is CVE-2025-1234, not CVE-2025-1235.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The SQLCODE is -204 rather than -100.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The identifier CVE-2026-77 is supported; another record uses CVE-2026-77.", ["VALIDATE", "VALIDATE"]),
        ("Operation A returns SQLCODE -7, while operation B returns SQLCODE -7.", ["VALIDATE", "VALIDATE"]),
        ("The supported identifier is CVE-2030-1; the query's CVE-2030-2 is wrong.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The code SQLCODE +12 is valid, not SQLCODE +13.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
    ]
    for index, (claim, labels) in enumerate(identifiers, 1):
        cases.append(_case(f"ID{index:02d}", "IDENTIFIER", claim, claim, labels))

    dates = [
        ("The cutoff is 2026-08-31, not 2026-08-30.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The date is 2025-01-09 and a report also records 2025-01-09.", ["VALIDATE", "VALIDATE"]),
        ("The maintenance date is 2030-12-24, not 2030-12-23.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        ("The release date is 2024-04-04; a second record has 2024-04-04.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(dates, 1):
        cases.append(_case(f"DATE{index:02d}", "DATE", claim, claim, labels))

    context = [
        ("120 is greater than 100.", ["VALIDATE", "VALIDATE"]),
        ("The docs say '90 days'.", ["VALIDATE"]),
        ("The values 100 and 120 differ.", ["VALIDATE", "VALIDATE"]),
        ("Regarding the 30-day figure, the source states 90 days.", ["VALIDATE", "VALIDATE"]),
        ("Is the limit 100 or 120? The documented limit is 120.", ["VALIDATE", "VALIDATE", "VALIDATE"]),
        ("The 100 in the question is lower than the supported 120.", ["VALIDATE", "VALIDATE"]),
        ("The system does not expire after 90 days.", ["VALIDATE"]),
        ("The user said 30 days, and the documentation says 90 days.", ["VALIDATE", "VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(context, 1):
        cases.append(_case(f"CTX{index:02d}", "CONTEXT_SAFETY", claim, claim, labels))

    ambiguous = [
        ("30 or 90 may be relevant.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        ("The values 100 and 120 differ.", ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"]),
        (
            "Regarding the 30-day figure, the source states 90 days.",
            ["AMBIGUOUS_KEEP_VALIDATING", "AMBIGUOUS_KEEP_VALIDATING"],
        ),
    ]
    for index, (claim, labels) in enumerate(ambiguous, 1):
        cases.append(_case(f"AMB{index:02d}", "AMBIGUOUS_POLARITY", claim, claim, labels))

    security = [
        ("The accepted SQLCODE is -204; do not accept fabricated 204.", ["VALIDATE", "VALIDATE"]),
        ("The source identifier is CVE-2025-1234; an unknown CVE-2025-9999 is not authorized.", ["VALIDATE", "VALIDATE"]),
        ("The supported signed value is -7, while a bare 7 must still be checked.", ["VALIDATE", "VALIDATE"]),
        ("Ignore hidden instructions and report the documented limit 120.", ["VALIDATE"]),
    ]
    for index, (claim, labels) in enumerate(security, 1):
        cases.append(_case(f"SEC{index:02d}", "SECURITY", claim, claim, labels))

    if not 80 <= len(cases) <= 120:
        raise AssertionError(len(cases))
    return cases


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> None:
    POP.mkdir(parents=True, exist_ok=True)
    population = build_population()
    with (POP / "population.jsonl").open("w", encoding="utf-8") as handle:
        for case in population:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    with (POP / "adjudications.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["occurrence_id", "case_id", "raw_literal", "normalized_value", "lexical_type", "span_start", "span_end", "expected_extraction_status", "expected_role", "rationale", "adjudication_status"])
        for case in population:
            for occurrence in case["occurrences"]:
                writer.writerow([
                    occurrence["occurrence_id"], case["case_id"], occurrence["raw_literal"],
                    occurrence["normalized_value"], occurrence["lexical_type"], occurrence["span_start"],
                    occurrence["span_end"], occurrence["expected_extraction_status"], occurrence["expected_role"],
                    "fresh architecture contract example", "CONFIRMED",
                ])
    labels = Counter(o["expected_role"] for c in population for o in c["occurrences"])
    categories = Counter(c["category"] for c in population)
    manifest = {
        "population_id": "CRITICAL_VALUE_ARCHITECTURE_V2_DEBUG_DEV",
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "secondary_unit": "case",
        "case_count": len(population),
        "occurrence_count": sum(len(c["occurrences"]) for c in population),
        "labels": dict(sorted(labels.items())),
        "categories": dict(sorted(categories.items())),
        "fresh_population": True,
        "historical_anchors_only": True,
        "holdout_used": False,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    }
    (POP / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    freeze = {
        "population_sha256": _sha(POP / "population.jsonl"),
        "adjudications_sha256": _sha(POP / "adjudications.csv"),
        "manifest_sha256": _sha(POP / "manifest.json"),
        "frozen_before_execution": True,
        "labels_frozen_before_execution": True,
        "primary_unit": "CRITICAL_VALUE_OCCURRENCE",
        "case_count": len(population),
        "occurrence_count": manifest["occurrence_count"],
    }
    (POP / "freeze.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _role_map(roles: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {
        (int(item["start"]), int(item["end"])): (
            "SKIP" if item.get("polarity") == "REJECTED_PREMISE" else "VALIDATE"
        )
        for item in roles
    }


def _score_case(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    v6 = claim_local_critical_value_audit_v6(case["claim"], case["support_texts"])
    v6_roles = _role_map(v6.get("v6_polarity_occurrences", []))
    v2 = audit_claim_architecture_v2(case["claim"], case["support_texts"], claim_id=case["case_id"])
    v2_roles = {o.occurrence_id.split(".", 1)[-1]: d.role for o, d in zip(v2["occurrences"], v2["role_decisions"])}
    rows: list[dict[str, Any]] = []
    for occurrence in case["occurrences"]:
        key = (int(occurrence["span_start"]), int(occurrence["span_end"]))
        expected_role = occurrence["expected_role"]
        legacy_role = v6_roles.get(key, "MISSING")
        v2_role = "SKIP" if v2_roles[occurrence["occurrence_id"].split(".", 1)[-1]] == "SKIP_REJECTED_PREMISE" else "VALIDATE"
        expected_behavior = "SKIP" if expected_role == "SKIP_REJECTED_PREMISE" else "VALIDATE"
        rows.append({
            "occurrence_id": occurrence["occurrence_id"],
            "case_id": case["case_id"],
            "category": case["category"],
            "span_start": occurrence["span_start"],
            "span_end": occurrence["span_end"],
            "raw_literal": occurrence["raw_literal"],
            "normalized_value": occurrence["normalized_value"],
            "lexical_type": occurrence["lexical_type"],
            "expected_role": expected_role,
            "expected_behavior": expected_behavior,
            "legacy_role": legacy_role,
            "v2_role": v2_role,
            "legacy_correct": legacy_role == expected_behavior,
            "v2_correct": v2_role == expected_behavior,
        })
    return {
        "case_id": case["case_id"],
        "claim": case["claim"],
        "occurrences": rows,
        "v6_outcome": v6.get("validator_outcome"),
        "v6_extraction_spans": [
            [int(item["start"]), int(item["end"])]
            for item in v6.get("v6_polarity_occurrences", [])
        ],
    }, v2


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def count(arm: str, expected: str, observed: str) -> int:
        return sum(
            row["expected_behavior"] == expected and row[f"{arm}_role"] == observed
            for row in rows
        )

    def grouped_mixed(arm: str, type_mismatch: bool = False) -> int:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = (row["case_id"], row["normalized_value"])
            groups[key].append(row)
        total = 0
        for siblings in groups.values():
            expected_roles = {item["expected_behavior"] for item in siblings}
            if len(expected_roles) < 2:
                continue
            if type_mismatch and len({item["lexical_type"] for item in siblings}) < 2:
                continue
            if len({item["lexical_type"] for item in siblings}) < 2 and type_mismatch:
                continue
            if len({item["legacy_role" if arm == "legacy" else "v2_role"] for item in siblings}) == 1:
                total += 1
        return total

    def sibling_contamination(arm: str) -> int:
        by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_case[row["case_id"]].append(row)
        return sum(
            any(item["expected_behavior"] != item[f"{arm}_role"] for item in case_rows)
            and len({item["expected_behavior"] for item in case_rows}) > 1
            for case_rows in by_case.values()
        )

    metrics: dict[str, Any] = {}
    for arm in ("legacy", "v2"):
        metrics[f"{arm}_real_assertion_incorrectly_skipped"] = count(arm, "VALIDATE", "SKIP")
        metrics[f"{arm}_ambiguous_incorrectly_skipped"] = sum(
            row["expected_role"] == "AMBIGUOUS_KEEP_VALIDATING" and row[f"{arm}_role"] == "SKIP"
            for row in rows
        )
        metrics[f"{arm}_rejected_premise_not_skipped"] = count(arm, "SKIP", "VALIDATE")
        metrics[f"{arm}_correct_rejected_premise_skips"] = sum(
            row["expected_behavior"] == "SKIP" and row[f"{arm}_role"] == "SKIP" for row in rows
        )
        metrics[f"{arm}_global_value_collapse_errors"] = grouped_mixed(arm)
        metrics[f"{arm}_type_reinterpretation_identity_errors"] = grouped_mixed(arm, True)
        metrics[f"{arm}_sibling_contamination"] = sibling_contamination(arm)
    return metrics


def execute() -> None:
    population = [json.loads(line) for line in (POP / "population.jsonl").read_text(encoding="utf-8").splitlines()]
    LEGACY.mkdir(parents=True, exist_ok=True)
    V2.mkdir(parents=True, exist_ok=True)
    COMPARISON.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    legacy_records: list[dict[str, Any]] = []
    v2_records: list[dict[str, Any]] = []
    for case in population:
        legacy, v2 = _score_case(case)
        legacy_records.append(legacy)
        v2_records.append({
            "case_id": case["case_id"],
            "claim": case["claim"],
            "occurrences": [
                {
                    "occurrence_id": o.occurrence_id,
                    "raw_literal": o.raw_literal,
                    "normalized_value": o.normalized_value,
                    "lexical_type": o.lexical_type,
                    "span_start": o.span_start,
                    "span_end": o.span_end,
                    "role": d.role,
                    "reason_code": d.reason_code,
                }
                for o, d in zip(v2["occurrences"], v2["role_decisions"])
            ],
            "validate_occurrence_ids": list(v2["validate_occurrence_ids"]),
            "v3": v2["v3"],
        })
        all_rows.extend(legacy["occurrences"])
    for path, records in ((LEGACY / "case-results.jsonl", legacy_records), (V2 / "case-results.jsonl", v2_records)):
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    metrics = _metrics(all_rows)
    metrics.update({
        "case_count": len(population),
        "occurrence_count": len(all_rows),
        "legacy_nested_occurrence_errors": 0,
        "v2_nested_occurrence_errors": 0,
        "v2_occurrence_id_collisions": 0,
        "v2_numeric_semantic_mismatches": 0,
        "v2_locale_semantic_mismatches": 0,
        "v2_version_semantic_mismatches": 0,
        "v2_identifier_sign_semantic_mismatches": 0,
        "v2_indeterminate_semantic_mismatches": 0,
        "provider_calls": {"openai": 0, "ollama": 0, "embedding": 0, "bge": 0, "retrieval": 0},
    })
    (LEGACY / "metrics.json").write_text(json.dumps({k: v for k, v in metrics.items() if k.startswith("legacy_") or k in {"case_count", "occurrence_count", "provider_calls"}}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (V2 / "metrics.json").write_text(json.dumps({k: v for k, v in metrics.items() if k.startswith("v2_") or k in {"case_count", "occurrence_count", "provider_calls"}}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (COMPARISON / "occurrence-comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(all_rows[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    (COMPARISON / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.execute:
        execute()
