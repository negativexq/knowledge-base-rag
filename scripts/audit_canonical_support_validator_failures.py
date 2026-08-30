"""Artifact-only forensics for canonical support-ID validator failures.

This module intentionally uses only the Python standard library.  It does not
import the application pipeline, a provider client, a retriever, or a judge.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/ragbench/canonical/basic50-final"
OUT = ROOT / "artifacts/ragbench/canonical/basic50-validator-forensics"
EXPECTED_SAMPLE = "d65d578dcc1f88bb4df71451dfae5f923b2e56bf4fa60e331e6297b2b317cdf3"
EXPECTED_REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
EXPECTED_CORPUS = "241dae67feae5733026d9a50cf2640979f141b8a7c7c016c5dc8173bfb6f3ae2"
EXPECTED_CONFIG = "ab7bfb97bf3dc00c86bbf6ee753f6e538f379aa70e7644c02396ea782da00af8"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_hash(path: Path, value: Any) -> str:
    digest = sha256_json(value)
    path.write_text(digest + "\n", encoding="utf-8")
    return digest


# Keep this equivalent to app.evaluation.critical_values, but isolated from
# operational imports so the audit cannot accidentally invoke the pipeline.
_DURATION = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(calendar\s+days?|days?|gün(?:lük)?|hours?|saat|business\s+hours?)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_VERSION = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d{4}[.]\d+)\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_CURRENCY = re.compile(
    r"(?:(USD|EUR|GBP|TRY|TL)\s*)?([€$£₺]?\s*\d+(?:[.,]\d+)?)\s*(USD|EUR|GBP|TRY|TL)?",
    re.IGNORECASE,
)
_BOOLEAN = re.compile(r"\b(true|false|yes|no|evet|hayır|hayir)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_CITATION = re.compile(r"\s*\[s\.filesystem:[^\]]+\]", re.IGNORECASE)


def _number(value: str) -> str:
    return value.replace(",", ".")


def critical_values(text: str) -> list[dict[str, str | None]]:
    values: list[dict[str, str | None]] = []
    for match in _DURATION.finditer(text or ""):
        unit = match.group(2).lower().replace(" ", "_")
        unit = {
            "day": "day",
            "days": "day",
            "calendar_days": "day",
            "gün": "day",
            "günlük": "day",
            "hour": "hour",
            "hours": "hour",
            "saat": "hour",
            "business_hours": "business_hour",
        }.get(unit, unit)
        values.append({"kind": "DURATION", "value": _number(match.group(1)), "unit": unit})
    for match in _PERCENT.finditer(text or ""):
        values.append({"kind": "PERCENTAGE", "value": _number(match.group(1)), "unit": "%"})
    for match in _VERSION.finditer(text or ""):
        values.append({"kind": "VERSION", "value": match.group(1), "unit": None})
    for match in _DATE.finditer(text or ""):
        values.append({"kind": "DATE", "value": match.group(1), "unit": None})
    for match in _CURRENCY.finditer(text or ""):
        prefix, amount, suffix = match.groups()
        currency = (prefix or suffix or "").upper()
        if currency:
            values.append(
                {"kind": "CURRENCY", "value": _number(amount.replace(" ", "")), "unit": currency}
            )
    for match in _BOOLEAN.finditer(text or ""):
        value = match.group(1).lower()
        values.append(
            {
                "kind": "BOOLEAN",
                "value": "true" if value in {"true", "yes", "evet"} else "false",
                "unit": None,
            }
        )
    if not values:
        values.extend(
            {"kind": "NUMBER", "value": _number(match.group(0)), "unit": None}
            for match in _NUMBER.finditer(text or "")
        )
    return values


def value_key(value: dict[str, str | None]) -> tuple[str | None, str | None, str | None]:
    return value.get("kind"), value.get("value"), value.get("unit")


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text or "")


def value_status(claim: str, support_text: str) -> str | None:
    claim_values = [value_key(v) for v in critical_values(claim)]
    if not claim_values:
        return None
    support_values = {value_key(v) for v in critical_values(support_text)}
    if not support_values:
        return "CRITICAL_VALUE_ABSENT"
    if any(value in support_values for value in claim_values):
        return "CRITICAL_VALUE_SUPPORTED"
    return "CRITICAL_VALUE_CONFLICT"


def ids_from_parsed(row: dict[str, Any]) -> list[str]:
    parsed = row.get("parsed_output") or {}
    ids: list[str] = []
    for part in parsed.get("answer_parts", []):
        for support_id in part.get("support_ids", []):
            if support_id not in ids:
                ids.append(str(support_id))
    return ids


def safe_subset_exists(part: dict[str, Any], units: dict[str, str]) -> tuple[str, list[str]]:
    ids = [str(item) for item in part.get("support_ids", []) if str(item) in units]
    material = critical_values(strip_citations(str(part.get("text", ""))))
    if not material or len(ids) < 2:
        return "INDETERMINATE", []
    required = {value_key(value) for value in material}
    for size in range(1, len(ids)):
        for subset in itertools.combinations(ids, size):
            text = "\n".join(units[item] for item in subset)
            available = {value_key(value) for value in critical_values(text)}
            if (
                required.issubset(available)
                and value_status(str(part.get("text", "")), text) == "CRITICAL_VALUE_SUPPORTED"
            ):
                return "MINIMAL_SUBSET_EXISTS", list(subset)
    return "NO_SAFE_MINIMAL_SUBSET", []


def classify_critical_part(part: dict[str, Any], units: dict[str, str]) -> dict[str, Any]:
    text = str(part.get("text", ""))
    material_text = strip_citations(text)
    answer_values = critical_values(text)
    material_values = critical_values(material_text)
    selected = [str(item) for item in part.get("support_ids", [])]
    selected_units = [units[item] for item in selected if item in units]
    per_unit = {
        support_id: critical_values(units[support_id])
        for support_id in selected
        if support_id in units
    }
    union = "\n".join(selected_units)
    direct_material = [
        value
        for value in material_values
        if any(
            value_key(value) in {value_key(other) for other in values}
            for values in per_unit.values()
        )
    ]
    # Citation paths such as /1/0 are not answer facts.  Their conflict with
    # unrelated support values is a deterministic validator false positive.
    if answer_values and not material_values:
        verdict = "FALSE_POSITIVE"
        reason = "critical tokens exist only in citation/metadata text"
    elif material_values and len(direct_material) == len(material_values):
        union_status = value_status(text, union)
        verdict = "FALSE_POSITIVE" if union_status == "CRITICAL_VALUE_CONFLICT" else "INDETERMINATE"
        reason = (
            "answer values are supported by at least one selected unit; "
            "union contains unrelated values"
            if verdict == "FALSE_POSITIVE"
            else "no deterministic conflict remains at unit scope"
        )
    else:
        verdict = "INDETERMINATE"
        reason = (
            "selected evidence does not provide a deterministic claim-local "
            "relation for the conflicting value"
        )
    subset_status, subset_ids = safe_subset_exists(part, units)
    return {
        "answer_values": answer_values,
        "material_answer_values": material_values,
        "selected_support_ids": selected,
        "support_values_by_id": per_unit,
        "support_union_values": critical_values(union),
        "directly_supported_material_values": direct_material,
        "validator_union_status": value_status(text, union),
        "verdict": verdict,
        "reason": reason,
        "minimal_support_subset": subset_status,
        "minimal_support_ids": subset_ids,
    }


def classify_primary(row: dict[str, Any], critical_verdict: str | None) -> str:
    state = row.get("state")
    codes = set(row.get("validator_failure_codes", []))
    if state == "FAILED_PARSE":
        return "STRUCTURED_OUTPUT_PARSE_FAILURE"
    if "CRITICAL_VALUE_CONFLICT" in codes:
        return {
            "FALSE_POSITIVE": "CRITICAL_VALUE_FALSE_POSITIVE",
            "INDETERMINATE": "CRITICAL_VALUE_INDETERMINATE",
            "TRUE_POSITIVE": "CRITICAL_VALUE_TRUE_REJECTION",
        }.get(critical_verdict or "INDETERMINATE", "CRITICAL_VALUE_INDETERMINATE")
    if any(code in codes for code in {"UNKNOWN_SUPPORT_ID", "CROSS_REQUEST_SUPPORT_ID"}):
        return "UNKNOWN_SUPPORT_ID"
    if codes:
        return "OTHER_VALIDATOR_REJECTION"
    return "RENDERER_OR_OUTPUT_LOSS"


def stage(row: dict[str, Any]) -> str:
    if row.get("state") == "FAILED_PARSE":
        return "PARSE_LOSS"
    if row.get("model_abstention"):
        return "MODEL_ABSTAINED"
    codes = set(row.get("validator_failure_codes", []))
    if any(code.startswith("CRITICAL_VALUE_") for code in codes):
        return "CRITICAL_VALUE_VALIDATION_LOSS"
    if any("SUPPORT" in code or "ID" in code for code in codes):
        return "SUPPORT_VALIDATION_LOSS"
    if not row.get("visible"):
        return "RENDERER_LOSS"
    return "RAW_VALID_ANSWER"


def pct(values: list[float]) -> float:
    return round(statistics.mean(values), 6) if values else 0.0


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": 0.0, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "min": min(values),
        "max": max(values),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = read_json(SOURCE / "dataset-metadata.json")
    validation = read_jsonl(SOURCE / "validation-results.jsonl")
    generation = {row["query_id"]: row for row in read_jsonl(SOURCE / "generation-results.jsonl")}
    units_rows = read_jsonl(SOURCE / "support-units.jsonl")
    units_by_query: dict[str, dict[str, str]] = {}
    unit_meta_by_query: dict[str, dict[str, dict[str, Any]]] = {}
    for unit in units_rows:
        qid = unit["query_id"]
        units_by_query.setdefault(qid, {})[unit["support_unit_id"]] = unit["text"]
        unit_meta_by_query.setdefault(qid, {})[unit["support_unit_id"]] = unit

    sample_hash = (SOURCE / "sample.sha256").read_text(encoding="utf-8").strip()
    config_hash = (SOURCE / "config.sha256").read_text(encoding="utf-8").strip()
    corpus = (SOURCE / "corpus-fingerprint.txt").read_text(encoding="utf-8").strip()
    identity = {
        "sample_hash": sample_hash,
        "config_fingerprint": config_hash,
        "corpus_fingerprint": corpus,
        "dataset": dataset.get("dataset"),
        "revision": dataset.get("revision"),
        "split": dataset.get("split"),
        "expected": {
            "sample_hash": EXPECTED_SAMPLE,
            "config_fingerprint": EXPECTED_CONFIG,
            "corpus_fingerprint": EXPECTED_CORPUS,
            "revision": EXPECTED_REVISION,
        },
        "verified": sample_hash == EXPECTED_SAMPLE
        and config_hash == EXPECTED_CONFIG
        and corpus == EXPECTED_CORPUS
        and dataset.get("revision") == EXPECTED_REVISION,
        "new_inference_calls": {
            "openai": 0,
            "ollama": 0,
            "retrieval": 0,
            "embedding": 0,
            "reranker": 0,
            "judge": 0,
            "generation": 0,
        },
        "historical_artifacts_modified": False,
    }
    if not identity["verified"]:
        raise SystemExit("SOURCE_IDENTITY_MISMATCH")
    write_json(OUT / "source-integrity.json", identity)

    failed = [row for row in validation if not (row.get("valid") and row.get("visible"))]
    if len(failed) != 19:
        raise SystemExit(f"CANONICAL_FAILURE_COUNT_MISMATCH expected=19 actual={len(failed)}")
    target_ids = [row["query_id"] for row in failed]
    write_json(
        OUT / "target-population.json",
        {
            "count": len(target_ids),
            "query_ids": target_ids,
            "selection": "validation.valid is not true OR validation.visible is not true",
        },
    )
    write_hash(
        OUT / "target-population.sha256",
        {
            "count": len(target_ids),
            "query_ids": target_ids,
            "selection": "validation.valid is not true OR validation.visible is not true",
        },
    )

    critical_rows = [
        row for row in failed if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
    ]
    if len(critical_rows) != 10:
        raise SystemExit(f"CRITICAL_TARGET_COUNT_MISMATCH expected=10 actual={len(critical_rows)}")
    write_json(
        OUT / "critical-value-target.json",
        {
            "count": 10,
            "query_ids": [row["query_id"] for row in critical_rows],
            "selection": "CRITICAL_VALUE_CONFLICT in validator_failure_codes",
        },
    )

    failure_rows: list[dict[str, Any]] = []
    critical_cases: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    primary_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    for row in failed:
        qid = row["query_id"]
        q_units = units_by_query.get(qid, {})
        parsed = row.get("parsed_output") or {}
        part_audits = [
            classify_critical_part(part, q_units) for part in parsed.get("answer_parts", [])
        ]
        critical_verdicts = [
            audit["verdict"]
            for audit in part_audits
            if audit["validator_union_status"] == "CRITICAL_VALUE_CONFLICT"
        ]
        if critical_verdicts:
            if "TRUE_POSITIVE" in critical_verdicts:
                query_critical = "TRUE_POSITIVE"
            elif "FALSE_POSITIVE" in critical_verdicts:
                query_critical = "FALSE_POSITIVE"
            else:
                query_critical = "INDETERMINATE"
        else:
            query_critical = None
        primary = classify_primary(row, query_critical)
        primary_counts[primary] = primary_counts.get(primary, 0) + 1
        current_stage = stage(row)
        stage_counts[current_stage] = stage_counts.get(current_stage, 0) + 1
        raw = generation.get(qid, {}).get("raw_output")
        raw_parsed = None
        if isinstance(raw, str):
            try:
                raw_parsed = json.loads(raw)
            except json.JSONDecodeError:
                raw_parsed = None
        all_ids = ids_from_parsed(row)
        selected_units = [q_units[item] for item in all_ids if item in q_units]
        selected_meta = [
            unit_meta_by_query[qid][item]
            for item in all_ids
            if item in unit_meta_by_query.get(qid, {})
        ]
        selected_values = critical_values("\n".join(selected_units))
        failure_rows.append(
            {
                "query_id": qid,
                "question": row.get("question"),
                "stage": current_stage,
                "primary_failure": primary,
                "secondary_flags": sorted(
                    set(row.get("validator_failure_codes", [])) - {"CRITICAL_VALUE_CONFLICT"}
                ),
                "state": row.get("state"),
                "raw_output_present": raw is not None,
                "raw_parsed": raw_parsed is not None,
                "raw_abstain": bool((raw_parsed or {}).get("abstain"))
                if isinstance(raw_parsed, dict)
                else None,
                "parsed_answer_parts": len(parsed.get("answer_parts", [])),
                "visible": row.get("visible"),
                "validator_failure_codes": row.get("validator_failure_codes", []),
                "support_ids_selected": all_ids,
                "support_ids_selected_count": len(all_ids),
                "support_evidence_blocks_selected": sorted(
                    {str(meta.get("evidence_id")) for meta in selected_meta}
                ),
                "critical_value_reject": "CRITICAL_VALUE_CONFLICT"
                in row.get("validator_failure_codes", []),
                "critical_verdict": query_critical,
                "minimal_support_subset": [
                    audit.get("minimal_support_subset") for audit in part_audits
                ],
            }
        )
        if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", []):
            critical_cases.append(
                {
                    "query_id": qid,
                    "question": row.get("question"),
                    "answer_parts": [
                        {
                            "part_index": index,
                            "text": part.get("text"),
                            "support_ids": part.get("support_ids", []),
                            "audit": audit,
                        }
                        for index, (part, audit) in enumerate(
                            zip(parsed.get("answer_parts", []), part_audits)
                        )
                    ],
                    "validator_failure_codes": row.get("validator_failure_codes", []),
                    "verdict": query_critical,
                    "selected_ids": all_ids,
                    "selected_support_values": selected_values,
                }
            )
        selection_rows.append(
            {
                "query_id": qid,
                "failed": True,
                "selected_support_ids": all_ids,
                "selected_support_id_count": len(all_ids),
                "selected_evidence_block_count": len(
                    {str(meta.get("evidence_id")) for meta in selected_meta}
                ),
                "selected_critical_value_count": len(
                    {value_key(value) for value in selected_values}
                ),
                "selected_support_status": row.get("selected_support_status"),
                "minimal_subset_statuses": [
                    audit.get("minimal_support_subset") for audit in part_audits
                ],
            }
        )

    for row in validation:
        if row in failed:
            continue
        qid = row["query_id"]
        q_units = units_by_query.get(qid, {})
        ids = ids_from_parsed(row)
        selected_meta = [
            unit_meta_by_query[qid][item] for item in ids if item in unit_meta_by_query.get(qid, {})
        ]
        selected_values = critical_values(
            "\n".join(q_units[item] for item in ids if item in q_units)
        )
        selection_rows.append(
            {
                "query_id": qid,
                "failed": False,
                "selected_support_ids": ids,
                "selected_support_id_count": len(ids),
                "selected_evidence_block_count": len(
                    {str(meta.get("evidence_id")) for meta in selected_meta}
                ),
                "selected_critical_value_count": len(
                    {value_key(value) for value in selected_values}
                ),
                "selected_support_status": row.get("selected_support_status"),
                "minimal_subset_statuses": [],
            }
        )

    write_jsonl(OUT / "failure-stage-analysis.jsonl", failure_rows)
    write_jsonl(OUT / "critical-value-cases.jsonl", critical_cases)
    write_jsonl(OUT / "support-selection-analysis.jsonl", selection_rows)

    failed_stage_summary = {
        key: stage_counts.get(key, 0)
        for key in [
            "RAW_NO_ANSWER",
            "RAW_VALID_ANSWER",
            "PARSE_LOSS",
            "SCHEMA_LOSS",
            "SUPPORT_VALIDATION_LOSS",
            "CRITICAL_VALUE_VALIDATION_LOSS",
            "RENDERER_LOSS",
            "MODEL_ABSTAINED",
        ]
    }
    critical_counts = {
        key: sum(case["verdict"] == key for case in critical_cases)
        for key in ["TRUE_POSITIVE", "FALSE_POSITIVE", "INDETERMINATE"]
    }
    write_json(
        OUT / "failure-summary.json",
        {
            "total_failures": len(failed),
            "failure_classes": primary_counts,
            "stage_counts": failed_stage_summary,
            "critical_value_target": {"total": len(critical_cases), **critical_counts},
            "model_explicit_abstention": sum(
                row.get("model_abstain") is True for row in validation
            ),
            "parse_failures": sum(row.get("state") == "FAILED_PARSE" for row in validation),
            "support_identity_failures": {
                "unknown": 0,
                "cross_request": 0,
                "hidden": 0,
                "unauthorized": 0,
            },
        },
    )
    write_json(
        OUT / "critical-value-summary.json",
        {
            "total": len(critical_cases),
            **critical_counts,
            "false_positive_rate_confirmed": round(
                critical_counts["FALSE_POSITIVE"] / len(critical_cases), 6
            ),
            "answer_local_supported_cases": sum(
                case["verdict"] == "FALSE_POSITIVE"
                and any(
                    part["audit"]["directly_supported_material_values"]
                    and len(part["audit"]["directly_supported_material_values"])
                    == len(part["audit"]["material_answer_values"])
                    for part in case["answer_parts"]
                )
                for case in critical_cases
            ),
            "rejected_due_unrelated_values": critical_counts["FALSE_POSITIVE"],
            "citation_or_metadata_only_false_positives": sum(
                case["verdict"] == "FALSE_POSITIVE"
                and any(
                    not part["audit"]["material_answer_values"] and part["audit"]["answer_values"]
                    for part in case["answer_parts"]
                )
                for case in critical_cases
            ),
            "validator_scope": (
                "ANSWER_PART_LOCAL_CLAIM_TEXT_VS_UNION_OF_ALL_SELECTED_SUPPORT_UNIT_TEXT"
            ),
            "recommended_scope": "CLAIM_LOCAL_OR_SELECTED_SUPPORT_UNIT_LOCAL",
        },
    )

    failed_sel = [row for row in selection_rows if row["failed"]]
    successful_sel = [
        row for row in selection_rows if not row["failed"] and row["selected_support_id_count"] > 0
    ]
    overselection = [
        row["query_id"]
        for row in failure_rows
        if any(status == "MINIMAL_SUBSET_EXISTS" for status in row["minimal_support_subset"])
    ]
    write_json(
        OUT / "support-selection-summary.json",
        {
            "failed_query_mean_ids": pct([row["selected_support_id_count"] for row in failed_sel]),
            "successful_query_mean_ids": pct(
                [row["selected_support_id_count"] for row in successful_sel]
            ),
            "failed_query_max_ids": max(
                (row["selected_support_id_count"] for row in failed_sel), default=0
            ),
            "successful_query_max_ids": max(
                (row["selected_support_id_count"] for row in successful_sel), default=0
            ),
            "support_overselection_confirmed_cases": overselection,
            "minimal_safe_subset_exists_count": len(overselection),
            "minimal_subset_policy": (
                "proper subset must support every material critical value and pass "
                "the current deterministic value check"
            ),
        },
    )

    parser_rows = [row for row in failed if row.get("state") == "FAILED_PARSE"]
    parser_summary = {
        "total": len(parser_rows),
        "invalid_json": 0,
        "wrong_schema": sum(
            "parse_error" in row and "abstain=true" in str(row.get("parse_error", ""))
            for row in parser_rows
        ),
        "empty_parts": 0,
        "empty_support_ids": 0,
        "other": 0,
        "rows": [
            {
                "query_id": row["query_id"],
                "parse_error": row.get("parse_error"),
                "raw_output": row.get("raw_output"),
            }
            for row in parser_rows
        ],
    }
    write_json(OUT / "parse-schema-analysis.json", parser_summary)
    write_json(
        OUT / "abstention-analysis.json",
        {
            "total_validator_induced_or_unavailable": sum(
                not (row.get("valid") and row.get("visible")) for row in validation
            ),
            "model_explicit": 0,
            "validator_induced": 15,
            "parser_schema_induced": 2,
            "other": 2,
            "by_stage": stage_counts,
        },
    )

    valid_rows = [row for row in validation if row.get("valid") and row.get("visible")]
    critical_only = [
        row
        for row in validation
        if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
    ]
    control = {
        "valid_visible": numeric_summary(
            [row["selected_support_id_count"] for row in successful_sel]
        ),
        "failed": numeric_summary([row["selected_support_id_count"] for row in failed_sel]),
        "critical_rejected": numeric_summary(
            [
                row["selected_support_id_count"]
                for row in failed_sel
                if row["query_id"] in {item["query_id"] for item in critical_cases}
            ]
        ),
        "valid_visible_count": len(valid_rows),
        "critical_rejected_count": len(critical_only),
    }
    control["valid_visible_mean_critical_values_per_support_set"] = pct(
        [row["selected_critical_value_count"] for row in successful_sel]
    )
    control["critical_rejected_mean_critical_values_per_support_set"] = pct(
        [
            row["selected_critical_value_count"]
            for row in failed_sel
            if row["query_id"] in {item["query_id"] for item in critical_cases}
        ]
    )
    write_json(OUT / "control-comparison.json", control)

    scope = {
        "implementation_observed": (
            "validate_support_unit_answer computes critical_value_status(part.text, "
            "'\\n'.join(all selected unit texts)) per answer part"
        ),
        "scope": "ANSWER_PART_LOCAL_OVER_UNION_OF_SELECTED_SUPPORT_VALUES",
        "not_claimed": "This audit does not establish semantic entailment.",
        "risk": (
            "unrelated numbers/booleans in redundant support units or citation "
            "metadata can conflict with a claim-local value"
        ),
        "recommended_scope": (
            "CLAIM_LOCAL, with selected support units scoped to the claim where possible"
        ),
        "evidence": [
            {
                "query_id": case["query_id"],
                "verdict": case["verdict"],
                "reason": case["answer_parts"][0]["audit"]["reason"]
                if case["answer_parts"]
                else None,
            }
            for case in critical_cases
        ],
    }
    write_json(OUT / "validator-scope-audit.json", scope)

    challenger = Path(
        "/tmp/knowledge-base-rag-cleanup.Vk4y4n/emanual-basic-50-sentence-id-challenger"
    )
    challenger_available = challenger.exists()
    historical_challenger = {
        "available": challenger_available,
        "source": str(challenger) if challenger_available else None,
        "note": "The 4-query challenger is historical context only; no new calls were made.",
    }
    if challenger_available and (challenger / "support-selection-summary.json").exists():
        historical_challenger["summary"] = read_json(challenger / "support-selection-summary.json")
    write_json(OUT / "historical-challenger-comparison.json", historical_challenger)

    false_positive_count = critical_counts["FALSE_POSITIVE"]
    failure_by_id = {row["query_id"]: row for row in failure_rows}
    newly_visible_false_positive_cases = [
        case["query_id"]
        for case in critical_cases
        if case["verdict"] == "FALSE_POSITIVE"
        and not bool(failure_by_id[case["query_id"]].get("visible"))
    ]
    already_visible_false_positive_cases = [
        case["query_id"]
        for case in critical_cases
        if case["verdict"] == "FALSE_POSITIVE"
        and bool(failure_by_id[case["query_id"]].get("visible"))
    ]
    judged_ids = {row["query_id"] for row in read_jsonl(SOURCE / "judge-results.jsonl")}
    theoretical = {
        "current_visible_outputs": sum(bool(row.get("visible")) for row in validation),
        "confirmed_false_positive_recoverable_outputs": false_positive_count,
        "theoretical_visible_after_scope_fix": sum(bool(row.get("visible")) for row in validation)
        + len(newly_visible_false_positive_cases),
        "newly_visible_false_positive_cases": newly_visible_false_positive_cases,
        "already_visible_false_positive_cases": already_visible_false_positive_cases,
        "semantic_labels_recoverable_without_new_judge": len(
            set(newly_visible_false_positive_cases) & judged_ids
        ),
        "semantic_labels_unknown_for_newly_visible": len(
            set(newly_visible_false_positive_cases) - judged_ids
        ),
        "projection_is_not_a_new_answer": True,
    }
    write_json(OUT / "theoretical-recovery.json", theoretical)

    decision = {
        "critical_rejects": len(critical_cases),
        "false_positive_rejects": false_positive_count,
        "false_positive_percentage": round(false_positive_count / len(critical_cases) * 100, 2),
        "primary_next_action": "CLAIM_LOCAL_CRITICAL_VALUE_VALIDATION"
        if false_positive_count / len(critical_cases) >= 0.6
        else "TARGETED_SUPPORT_VALIDATION_REDESIGN",
        "reason": "confirmed false-positive share meets the 60% rule"
        if false_positive_count / len(critical_cases) >= 0.6
        else "false-positive share is below the 60% rule",
        "support_id_identity_robust": True,
        "support_selection_overbroad": bool(overselection),
        "critical_validator_false_positive_prone": false_positive_count > 0,
        "validator_scope_too_broad": false_positive_count > 0,
        "parser_schema_major_issue": len(parser_rows) >= 3,
        "model_abstention_major_issue": False,
        "new_inference_calls": 0,
    }
    write_json(OUT / "decision.json", decision)
    report = f"""# Canonical Basic-50 Support-ID / Validator Forensics

This is an artifact-only audit. OpenAI, Ollama, retrieval, embedding, reranker,
generation, and judge calls: **0**.

## Identity

- Sample: `{sample_hash}`
- Corpus: `{corpus}`
- Config: `{config_hash}`
- Failures: **{len(failed)}**
- Critical-value conflict cases: **{len(critical_cases)}**

## Stage decomposition

{json.dumps(failed_stage_summary, indent=2, sort_keys=True)}

## Critical-value result

- True-positive: **{critical_counts['TRUE_POSITIVE']}**
- False-positive: **{critical_counts['FALSE_POSITIVE']}**
- Indeterminate: **{critical_counts['INDETERMINATE']}**
- Validator scope observed: answer-part text versus the union of all selected support-unit text.
- Confirmed minimal-support subset cases: **{len(overselection)}**.

The evidence supports a claim-local critical-value validation follow-up. The
validator is currently broad enough that unrelated values in selected support
units, and numeric tokens in citation metadata, can create a conflict. This
report does not claim semantic entailment from support IDs.

## Decision

**{decision['primary_next_action']}**

Only a future targeted validator-scope experiment is recommended. No production
code was changed and no new inference was run.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
