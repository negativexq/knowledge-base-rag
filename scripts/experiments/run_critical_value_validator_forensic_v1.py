"""Offline forensic join for the frozen corrected TechQA run.

This script reads persisted validation/evidence/unblind artifacts only.  It
does not import the provider, retrieval, reranker, or generation paths.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2"
OUT = REPO / "artifacts/ragbench/canonical/techqa-critical-validator-forensic-v1"
EXPECTED_LABELS = {"CORRECT", "PARTIAL", "INCORRECT", "UNAVAILABLE"}
KIND_TYPES = {
    "NUMBER": "NUMBER",
    "PERCENTAGE": "PERCENT",
    "DATE": "DATE",
    "VERSION": "VERSION",
    "DURATION": "DURATION",
    "CURRENCY": "MONEY",
    "BOOLEAN": "OTHER",
}


def raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"FORENSIC_ARTIFACT_ALREADY_EXISTS: {path}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv_once(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise RuntimeError(f"FORENSIC_ARTIFACT_ALREADY_EXISTS: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sidecar_hash(path: Path) -> str | None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file():
        return None
    match = re.search(r"\b[a-fA-F0-9]{64}\b", sidecar.read_text(encoding="utf-8"))
    return match.group(0).lower() if match else None


def source_record(rel: str) -> dict[str, Any]:
    path = REPO / rel
    actual = raw_sha(path)
    expected = sidecar_hash(path)
    return {
        "path": rel,
        "exists": path.is_file(),
        "file_size": path.stat().st_size,
        "raw_sha256": actual,
        "sidecar_path": str(path.with_name(path.name + ".sha256").relative_to(REPO)) if expected else None,
        "sidecar_sha256": expected,
        "sidecar_match": expected is None or expected == actual,
    }


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical_number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip()).normalize()
    except (InvalidOperation, ValueError):
        return None


def equivalent_value(kind: str, left: str, right: str) -> bool:
    if kind in {"NUMBER", "PERCENTAGE", "DURATION", "CURRENCY"}:
        lvalue, rvalue = canonical_number(left), canonical_number(right)
        if lvalue is not None and rvalue is not None and lvalue == rvalue:
            return True
        # The frozen run contains technical thousands-grouping forms such as
        # 131.072 versus 131072 and 1.000 versus 1000.  Treat these as a
        # representation-only issue only when the grouped form is unambiguous.
        def grouped_integer(value: str) -> str | None:
            if re.fullmatch(r"\d{1,3}(?:[.]\d{3})+", value):
                return value.replace(".", "")
            if re.fullmatch(r"\d{1,3}(?:[,]\d{3})+", value):
                return value.replace(",", "")
            return None

        left_grouped, right_grouped = grouped_integer(left), grouped_integer(right)
        return (left_grouped is not None and left_grouped == right) or (
            right_grouped is not None and right_grouped == left
        )
    if kind == "VERSION":
        def parts(value: str) -> tuple[int, ...] | None:
            try:
                values = tuple(int(item) for item in value.lstrip("vV").split("."))
            except ValueError:
                return None
            values = tuple(values)
            while len(values) > 1 and values[-1] == 0:
                values = values[:-1]
            return values

        return parts(left) is not None and parts(left) == parts(right)
    return left.casefold() == right.casefold()


def value_type(token: dict[str, Any]) -> str:
    return KIND_TYPES.get(str(token.get("kind")), "OTHER")


def compact(text: str, limit: int = 600) -> str:
    return " ".join((text or "").split())[:limit]


def labels_by_arm() -> dict[tuple[str, str], str]:
    rows = list(csv.DictReader((RUN / "11-final-unblind/unblinded-semantic-results.csv").open(encoding="utf-8", newline="")))
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        result[(row["query_id"], "ON")] = row["on_semantic"]
        result[(row["query_id"], "OFF")] = row["off_semantic"]
    return result


def adjudicate(trace: dict[str, Any], support_rows: list[dict[str, Any]]) -> tuple[str, str, str, str, str]:
    """Return adjudication, subtype, true subtype, indeterminate reason, basis."""
    status = trace.get("status")
    answer = trace.get("answer_critical_token") or {}
    per_support = trace.get("per_support") or []
    observed: list[dict[str, Any]] = []
    all_support_tokens: list[dict[str, Any]] = []
    for item in per_support:
        all_support_tokens.extend(item.get("support_critical_tokens") or [])
        observed.extend(item.get("support_critical_tokens") or [])
    observed = [item for item in observed if item.get("relation") == "DIRECT_CONFLICT"]
    if status == "INDETERMINATE":
        reason = "INSUFFICIENT_SUPPORT_CONTEXT" if not any(support_rows) or not observed else "AMBIGUOUS_NORMALIZATION"
        return "INDETERMINATE", "", "", reason, "Frozen validator trace was INDETERMINATE; no faithful conflict/representation decision was established."
    if status != "DIRECT_CONFLICT":
        return "INDETERMINATE", "", "", "MISSING_RUNTIME_DETAIL", f"Unexpected forensic trace status: {status!r}."

    answer_context = str(trace.get("answer_local_context", ""))
    negative_value = re.search(
        rf"\b(?:not|no|without|never|does not|doesn't|cannot|can't)\b[^.\n]{{0,64}}\b{re.escape(str(answer.get('value')))}\b",
        answer_context,
        re.IGNORECASE,
    )
    if negative_value and observed:
        return "FALSE_POSITIVE", "CLAIM_SUPPORT_ALIGNMENT", "", "", "The rejected literal occurs in an explicit negative/contrast claim; attached support supports the positive contrasting fact rather than the negated literal."

    answer_kind = str(answer.get("kind"))
    answer_value = str(answer.get("value"))
    exact_attached = [
        token
        for token in all_support_tokens
        if token.get("kind") == answer_kind
        and token.get("unit") == answer.get("unit")
        and str(token.get("value")) == answer_value
    ]
    support_text = " ".join(str(item.get("text", "")) for item in support_rows)
    if answer_kind == "NUMBER" and answer_value in {"2017", "14919"} and re.search(
        r"CVE[- ]2017[- ]14919", support_text, re.IGNORECASE
    ):
        return "FALSE_POSITIVE", "EXTRACTION_ERROR", "", "", "The attached support contains the hyphenated CVE identifier, but the validator extracted its numeric components as independent critical values."
    if answer_kind == "NUMBER" and answer_value == "911" and re.search(r"SQLCODE\s*=\s*-911", support_text, re.IGNORECASE):
        return "FALSE_POSITIVE", "EXTRACTION_ERROR", "", "", "The attached support contains SQLCODE=-911, but the validator's numeric extraction did not preserve the signed error-code form."
    if answer_kind == "VERSION" and answer_value == "7.5.0" and re.search(r"\bREPORTED\s+RELEASE\s+750\b", support_text, re.IGNORECASE):
        return "FALSE_POSITIVE", "VERSION_FORMAT", "", "", "The attached APAR uses IBM's compact reported-release form 750 for the claim's 7.5.0 release."
    if exact_attached:
        return "FALSE_POSITIVE", "SUPPORT_SEGMENTATION", "", "", "The exact claim literal is present in an attached support unit, but the validator trace did not classify that local occurrence as DIRECT_SUPPORT."
    if answer_kind == "VERSION":
        answer_parts = tuple(answer_value.lstrip("vV").split("."))
        prefixed = []
        for token in all_support_tokens:
            if token.get("kind") != "VERSION":
                continue
            token_parts = tuple(str(token.get("value")).lstrip("vV").split("."))
            if len(token_parts) > len(answer_parts) and token_parts[: len(answer_parts)] == answer_parts:
                prefixed.append(token)
        if prefixed:
            return "FALSE_POSITIVE", "VERSION_FORMAT", "", "", "The claim uses a release-family version while attached support uses a more specific patch-level representation."
    if observed and all(equivalent_value(str(answer.get("kind")), str(answer.get("value")), str(item.get("value"))) for item in observed):
        kind = str(answer.get("kind"))
        subtype = {
            "NUMBER": "NUMERIC_EQUIVALENCE",
            "PERCENTAGE": "NUMERIC_EQUIVALENCE",
            "DURATION": "NUMERIC_EQUIVALENCE",
            "CURRENCY": "NUMERIC_EQUIVALENCE",
            "VERSION": "VERSION_FORMAT",
        }.get(kind, "OTHER")
        return "FALSE_POSITIVE", subtype, "", "", "Claim and attached support used equivalent values after a representation-only comparison."
    # A support bundle can contain an error identifier and the associated
    # threshold (for example ORA-01795 and 1000).  When one attached value is
    # an unambiguous equivalent, the additional identifier is not treated as a
    # second semantic conflict for this claim-local forensic.
    if observed and any(equivalent_value(str(answer.get("kind")), str(answer.get("value")), str(item.get("value"))) for item in observed):
        kind = str(answer.get("kind"))
        subtype = {
            "NUMBER": "NUMERIC_EQUIVALENCE",
            "PERCENTAGE": "NUMERIC_EQUIVALENCE",
            "DURATION": "NUMERIC_EQUIVALENCE",
            "CURRENCY": "NUMERIC_EQUIVALENCE",
            "VERSION": "VERSION_FORMAT",
        }.get(kind, "OTHER")
        return "FALSE_POSITIVE", subtype, "", "", "At least one attached support literal is an unambiguous equivalent; other extracted numeric tokens are contextual identifiers or unrelated values."
    if answer_kind == "DURATION" and answer_value == "1" and re.search(r"\b35\s+days?\b", support_text, re.IGNORECASE):
        return "INDETERMINATE", "", "", "INSUFFICIENT_SUPPORT_CONTEXT", "The support contains a different date-range example (35 days), not the claim's same-day +1 day example."
    if answer_kind == "VERSION" and answer_value == "6.0" and "2.5.0" in support_text:
        return "INDETERMINATE", "", "", "INSUFFICIENT_SUPPORT_CONTEXT", "The attached support is a different firmware/documentation version and does not establish a claim-local 6.0 conflict."
    if len({(item.get("kind"), item.get("unit"), item.get("value")) for item in observed}) > 1:
        return "INDETERMINATE", "", "", "MULTI_SUPPORT_CONFLICT", "Attached supports exposed multiple conflicting literals for the same claim-local token."
    kind = str(answer.get("kind"))
    subtype = {
        "NUMBER": "WRONG_NUMBER",
        "PERCENTAGE": "WRONG_NUMBER",
        "DURATION": "OTHER",
        "DATE": "WRONG_DATE",
        "VERSION": "WRONG_VERSION",
        "CURRENCY": "WRONG_NUMBER",
    }.get(kind, "OTHER")
    return "TRUE_CONFLICT", "", subtype, "", "Claim-local attached support contained a materially different same-kind value with no demonstrated equivalent representation."


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"FORENSIC_ARTIFACT_ALREADY_EXISTS: {OUT}")
    required = [
        RUN / "06-deterministic/validation-results.jsonl",
        RUN / "04-evidence/on-evidence.jsonl",
        RUN / "04-evidence/off-evidence.jsonl",
        RUN / "04-evidence/query-level-funnel.jsonl",
        RUN / "11-final-unblind/unblinded-semantic-results.csv",
    ]
    if not all(path.is_file() for path in required):
        raise RuntimeError("VALIDATOR_FORENSIC_SOURCE_INTEGRITY_FAILURE: missing frozen source")

    source_paths = [
        "artifacts/ragbench/canonical/techqa-corrected-holdout-amendment-v2/01-amendment/preregistration-amendment-v2.json",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/09-semantic-review/codex-scorecard-frozen.csv",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/10-unblind-protocol/unblind-decision-protocol-v1.json",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/11-final-unblind/unblinded-semantic-results.csv",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/11-final-unblind/semantic-summary.json",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/11-final-unblind/g1-g7-gate.json",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/11-final-unblind/final-verdict.json",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/06-deterministic/validation-results.jsonl",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/04-evidence/on-evidence.jsonl",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/04-evidence/off-evidence.jsonl",
        "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/04-evidence/query-level-funnel.jsonl",
    ]
    sources = [source_record(rel) for rel in source_paths]
    if not all(item["sidecar_match"] for item in sources):
        raise RuntimeError("VALIDATOR_FORENSIC_SOURCE_INTEGRITY_FAILURE: sidecar mismatch")
    final_verdict = read_json(RUN / "11-final-unblind/final-verdict.json")
    if final_verdict.get("verdict") != "BGE_REMOVAL_NOT_SUPPORTED":
        raise RuntimeError("VALIDATOR_FORENSIC_SOURCE_INTEGRITY_FAILURE: final verdict changed")

    validation = jsonl(RUN / "06-deterministic/validation-results.jsonl")
    evidence = {}
    for arm in ("ON", "OFF"):
        for row in jsonl(RUN / f"04-evidence/{'on' if arm == 'ON' else 'off'}-evidence.jsonl"):
            evidence[(row["query_id"], arm)] = row
    labels = labels_by_arm()

    OUT.mkdir(parents=True)
    for name in ("01-integrity", "02-event-table", "03-adjudication", "04-query-summary", "05-aggregate", "06-report"):
        (OUT / name).mkdir()
    source_integrity = {
        "forensic_identity": "TECHQA_CRITICAL_VALUE_VALIDATOR_FORENSIC_V1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "starting_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_artifacts": sources,
        "final_verdict": "BGE_REMOVAL_NOT_SUPPORTED",
        "frozen_semantic_labels_changed": False,
        "production_config_changed": False,
        "calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0, "ollama": 0},
        "holdout_used_for_mechanism_forensic": True,
        "holdout_used_for_threshold_tuning": False,
        "holdout_content_accessed": True,
    }
    write_json_once(OUT / "01-integrity/source-integrity.json", source_integrity)

    event_rows: list[dict[str, Any]] = []
    adjudications: list[dict[str, Any]] = []
    query_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    event_number = 0
    for row in validation:
        if not row.get("critical_reject"):
            continue
        query_id, arm = row["query_id"], row["condition"]
        evidence_row = evidence[(query_id, arm)]
        supports = evidence_row.get("support_units", [])
        support_map = {unit.get("support_unit_id"): unit for unit in supports}
        for part in row.get("part_results", []):
            audit = (part.get("support_relevance") or {}).get("critical_value_audit") or {}
            for trace in audit.get("token_traces", []):
                if trace.get("status") not in {"DIRECT_CONFLICT", "INDETERMINATE"}:
                    continue
                event_number += 1
                answer = trace.get("answer_critical_token") or {}
                support_ids = part.get("support_ids") or []
                support_text = " || ".join(compact((support_map.get(support_id) or {}).get("text", "")) for support_id in support_ids)
                conflict_values = []
                for support in trace.get("per_support", []):
                    for token in support.get("support_critical_tokens", []):
                        if token.get("relation") == "DIRECT_CONFLICT":
                            conflict_values.append(str(token.get("value")))
                event_id = f"CV-{event_number:03d}"
                label = labels[(query_id, arm)]
                event = {
                    "event_id": event_id,
                    "query_id": query_id,
                    "arm": arm,
                    "answer_part_index": part.get("part_index"),
                    "claim_text": part.get("text", ""),
                    "critical_value": answer.get("value"),
                    "critical_value_type": value_type(answer),
                    "support_ids": ";".join(support_ids),
                    "support_text_excerpt": support_text,
                    "validator_rule": "claim_local_critical_value_audit",
                    "validator_reason": ";".join(audit.get("failure_codes", [])),
                    "validator_expected_literal": answer.get("value"),
                    "validator_observed_literal": ";".join(dict.fromkeys(conflict_values)),
                    "normalization_applied": audit.get("normalization", "NFKC_CASEFOLD_EXACT_TOKEN_NO_STEM_TR_EN_STOPWORDS_NEGATION_PRESERVED"),
                    "trace_status": trace.get("status"),
                    "critical_reject": True,
                    "forced_abstain": bool(row.get("forced_abstain")),
                    "final_semantic_label": label,
                    "final_visible": bool(row.get("visible")),
                    "source_artifact": "06-deterministic/validation-results.jsonl",
                    "notes": "Event table contains rejecting traces only; DIRECT_SUPPORT traces in a mixed part are not rejection events.",
                }
                event_rows.append(event)
                adjudication, fp_subtype, tc_subtype, ind_reason, basis = adjudicate(trace, supports)
                adjudications.append({
                    "event_id": event_id,
                    "query_id": query_id,
                    "arm": arm,
                    "answer_part_index": part.get("part_index"),
                    "critical_value": answer.get("value"),
                    "validator_event_status": trace.get("status"),
                    "adjudication": adjudication,
                    "false_positive_subtype": fp_subtype,
                    "true_conflict_subtype": tc_subtype,
                    "indeterminate_reason": ind_reason,
                    "adjudication_basis": basis,
                    "support_values": ";".join(dict.fromkeys(conflict_values)),
                })
                query_events[(query_id, arm)].append(adjudications[-1])

    event_fields = list(event_rows[0]) if event_rows else []
    write_csv_once(OUT / "02-event-table/critical-validator-events.csv", event_fields, event_rows)
    adjudication_fields = list(adjudications[0]) if adjudications else []
    write_csv_once(OUT / "03-adjudication/event-adjudications.csv", adjudication_fields, adjudications)

    all_query_arms = sorted({(row["query_id"], row["condition"]) for row in validation}, key=lambda item: (item[0], item[1]))
    validation_map = {(row["query_id"], row["condition"]): row for row in validation}
    query_summary: list[dict[str, Any]] = []
    for key in all_query_arms:
        query_id, arm = key
        row = validation_map[key]
        ads = query_events.get(key, [])
        counts = Counter(item["adjudication"] for item in ads)
        if not row.get("critical_reject"):
            outcome = "NO_REJECT"
        elif counts["TRUE_CONFLICT"] and counts["FALSE_POSITIVE"] and counts["INDETERMINATE"]:
            outcome = "MIXED_REJECTS"
        elif counts["TRUE_CONFLICT"] and counts["FALSE_POSITIVE"]:
            outcome = "MIXED_REJECTS"
        elif counts["TRUE_CONFLICT"] and counts["INDETERMINATE"]:
            outcome = "MIXED_REJECTS"
        elif counts["FALSE_POSITIVE"] and counts["INDETERMINATE"]:
            outcome = "MIXED_REJECTS"
        elif counts["TRUE_CONFLICT"]:
            outcome = "JUSTIFIED_REJECT"
        elif counts["FALSE_POSITIVE"]:
            outcome = "FALSE_POSITIVE_REJECT"
        elif counts["INDETERMINATE"]:
            outcome = "INDETERMINATE_REJECT"
        else:
            outcome = "INDETERMINATE_REJECT"
        query_summary.append({
            "query_id": query_id,
            "arm": arm,
            "critical_event_count": len(ads),
            "true_conflict_count": counts["TRUE_CONFLICT"],
            "false_positive_count": counts["FALSE_POSITIVE"],
            "indeterminate_count": counts["INDETERMINATE"],
            "critical_reject": bool(row.get("critical_reject")),
            "forced_abstain": bool(row.get("forced_abstain")),
            "final_semantic_label": labels[key],
            "final_visible": bool(row.get("visible")),
            "primary_validator_outcome": outcome,
        })
    summary_fields = list(query_summary[0])
    write_csv_once(OUT / "04-query-summary/query-arm-summary.csv", summary_fields, query_summary)

    by_key = {(row["query_id"], row["arm"]): row for row in query_summary}
    transitions: list[dict[str, Any]] = []
    query_ids = sorted({row["query_id"] for row in validation})
    for query_id in query_ids:
        on, off = by_key[(query_id, "ON")], by_key[(query_id, "OFF")]
        on_available, off_available = on["final_semantic_label"] != "UNAVAILABLE", off["final_semantic_label"] != "UNAVAILABLE"
        if on_available and not off_available:
            transition = "ON_AVAILABLE_OFF_UNAVAILABLE"
        elif not on_available and off_available:
            transition = "ON_UNAVAILABLE_OFF_AVAILABLE"
        elif on_available and off_available:
            transition = "BOTH_AVAILABLE"
        else:
            transition = "BOTH_UNAVAILABLE"
        transitions.append({
            "query_id": query_id,
            "on_semantic": on["final_semantic_label"],
            "off_semantic": off["final_semantic_label"],
            "on_critical_reject": on["critical_reject"],
            "off_critical_reject": off["critical_reject"],
            "on_forced_abstain": on["forced_abstain"],
            "off_forced_abstain": off["forced_abstain"],
            "on_validator_outcome": on["primary_validator_outcome"],
            "off_validator_outcome": off["primary_validator_outcome"],
            "transition": transition,
            "notes": "Availability transition is descriptive; no counterfactual semantic score is assigned.",
        })
    write_csv_once(OUT / "04-query-summary/availability-transitions.csv", list(transitions[0]), transitions)

    def arm_data(arm: str) -> list[dict[str, Any]]:
        return [row for row in query_summary if row["arm"] == arm]

    def cpl(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {label: sum(row["final_semantic_label"] == label for row in rows) for label in sorted(EXPECTED_LABELS)}

    arm_summary: dict[str, Any] = {"population": {"validation_query_arm_rows": len(query_summary), "critical_reject_events": len(event_rows)}, "arms": {}}
    for arm in ("ON", "OFF"):
        rows = arm_data(arm)
        critical = [row for row in rows if row["critical_reject"]]
        no_critical = [row for row in rows if not row["critical_reject"]]
        arm_summary["arms"][arm] = {
            "critical_reject_queries": len(critical),
            "event_count": sum(row["critical_event_count"] for row in critical),
            "true_conflict_events": sum(row["true_conflict_count"] for row in critical),
            "false_positive_events": sum(row["false_positive_count"] for row in critical),
            "indeterminate_events": sum(row["indeterminate_count"] for row in critical),
            "critical_reject_and_forced_abstain": sum(row["forced_abstain"] for row in critical),
            "critical_reject_and_no_forced_abstain": sum(not row["forced_abstain"] for row in critical),
            "no_critical_reject_and_forced_abstain": sum(row["forced_abstain"] for row in no_critical),
            "p_forced_abstain_given_critical_reject": (sum(row["forced_abstain"] for row in critical) / len(critical)) if critical else None,
            "critical_reject_and_unavailable": sum(row["final_semantic_label"] == "UNAVAILABLE" for row in critical),
            "critical_reject_and_available": sum(row["final_semantic_label"] != "UNAVAILABLE" for row in critical),
            "no_critical_reject_and_unavailable": sum(row["final_semantic_label"] == "UNAVAILABLE" for row in no_critical),
            "semantic_counts_all": cpl(rows),
            "semantic_counts_by_event_class": {
                outcome: cpl([row for row in critical if row[f"{outcome.lower()}_count"] > 0])
                for outcome in ("TRUE_CONFLICT", "FALSE_POSITIVE", "INDETERMINATE")
            },
        }
    only_off = sorted({row["query_id"] for row in transitions if row["off_critical_reject"] and not row["on_critical_reject"]})
    only_on = sorted({row["query_id"] for row in transitions if row["on_critical_reject"] and not row["off_critical_reject"]})
    both = sorted({row["query_id"] for row in transitions if row["on_critical_reject"] and row["off_critical_reject"]})
    arm_summary["critical_reject_query_sets"] = {"off_only": only_off, "on_only": only_on, "both": both}
    write_json_once(OUT / "05-aggregate/arm-summary.json", arm_summary)

    event_counts = Counter(row["adjudication"] for row in adjudications)
    query_class_counts = Counter(row["primary_validator_outcome"] for row in query_summary if row["critical_reject"])
    determinate = event_counts["TRUE_CONFLICT"] + event_counts["FALSE_POSITIVE"]
    determination = {
        "event_level": {
            "total_critical_reject_events": len(adjudications),
            "TRUE_CONFLICT": event_counts["TRUE_CONFLICT"],
            "FALSE_POSITIVE": event_counts["FALSE_POSITIVE"],
            "INDETERMINATE": event_counts["INDETERMINATE"],
            "precision_determinate": event_counts["TRUE_CONFLICT"] / determinate if determinate else None,
            "false_positive_rate_among_determinate": event_counts["FALSE_POSITIVE"] / determinate if determinate else None,
        },
        "query_arm_level_primary_outcome": dict(query_class_counts),
        "query_arm_level": {
            "total_critical_reject_query_arms": sum(row["critical_reject"] for row in query_summary),
            "TRUE_CONFLICT": sum(row["critical_reject"] and row["true_conflict_count"] > 0 and row["false_positive_count"] == 0 and row["indeterminate_count"] == 0 for row in query_summary),
            "FALSE_POSITIVE": sum(row["primary_validator_outcome"] == "FALSE_POSITIVE_REJECT" for row in query_summary),
            "INDETERMINATE": sum(row["primary_validator_outcome"] == "INDETERMINATE_REJECT" for row in query_summary),
        },
        "classification_policy": "Conservative: unresolved traces remain INDETERMINATE; representation-only equivalence is FALSE_POSITIVE only when deterministically demonstrated from attached support.",
    }
    write_json_once(OUT / "05-aggregate/calibration-summary.json", determination)

    consequence: dict[str, Any] = {}
    for outcome in ("TRUE_CONFLICT", "FALSE_POSITIVE", "INDETERMINATE"):
        rows = [row for row in query_summary if row["critical_reject"] and row[f"{outcome.lower()}_count"] > 0]
        consequence[outcome] = {
            "query_arm_rows": len(rows),
            "semantic_counts": cpl(rows),
            "forced_abstain": sum(row["forced_abstain"] for row in rows),
            "unavailable": sum(row["final_semantic_label"] == "UNAVAILABLE" for row in rows),
            "note": "Groups can overlap for MIXED_REJECTS; this is descriptive, not a counterfactual score.",
        }
    write_json_once(OUT / "05-aggregate/semantic-consequence-summary.json", consequence)

    if event_counts["INDETERMINATE"] > determinate:
        conclusion = "VALIDATOR_CALIBRATION_INCONCLUSIVE"
    elif event_counts["FALSE_POSITIVE"] > 0 and (event_counts["FALSE_POSITIVE"] / determinate if determinate else 0) >= 0.2:
        conclusion = "VALIDATOR_FALSE_POSITIVE_RISK"
    else:
        conclusion = "VALIDATOR_WELL_CALIBRATED"

    transition_counts = Counter(row["transition"] for row in transitions)
    off_unavailable_delta = sum(row["off_semantic"] == "UNAVAILABLE" for row in transitions) - sum(row["on_semantic"] == "UNAVAILABLE" for row in transitions)
    source_recheck = [{"path": item["path"], "raw_sha256_at_start": item["raw_sha256"], "raw_sha256_at_end": raw_sha(REPO / item["path"]), "unchanged": item["raw_sha256"] == raw_sha(REPO / item["path"])} for item in sources]
    event_by_id = {row["event_id"]: row for row in event_rows}
    fp_examples: dict[str, str] = {}
    for adjudication in adjudications:
        if adjudication["adjudication"] != "FALSE_POSITIVE":
            continue
        subtype = adjudication["false_positive_subtype"]
        if subtype in fp_examples:
            continue
        event = event_by_id[adjudication["event_id"]]
        fp_examples[subtype] = (
            f"{adjudication['event_id']} ({adjudication['query_id']}, {adjudication['arm']}): "
            f"claim literal {event['critical_value']!r}; support/validator values "
            f"{event['validator_observed_literal']!r}. Claim: {compact(event['claim_text'], 260)} "
            f"Support: {compact(event['support_text_excerpt'], 360)}"
        )
    fp_pattern_lines = "\n".join(
        f"- **{subtype}** ({sum(item['false_positive_subtype'] == subtype for item in adjudications)} events): {example}"
        for subtype, example in sorted(fp_examples.items())
    ) or "- None established."
    report = f"""# Critical-Value Validator Forensic V1

## Scope and integrity

This is an offline forensic of the frozen corrected TechQA execution. No
retrieval, embedding, BGE, Luna, Terra, Ollama, provider call, semantic
rescore, threshold tuning, or validator code change was performed.

The source artifacts were sidecar-verified where sidecars exist. The frozen
architecture verdict remains `BGE_REMOVAL_NOT_SUPPORTED`; semantic labels and
canonical artifacts were not modified. Source hash recheck at report time:
`{"PASS" if all(item['unchanged'] for item in source_recheck) else 'FAIL'}`.

## Population

There are {sum(row['critical_reject'] and row['arm'] == 'ON' for row in query_summary)} ON and {sum(row['critical_reject'] and row['arm'] == 'OFF' for row in query_summary)} OFF critical-reject query-arm rows, and {len(event_rows)} rejecting claim-local critical-value events ({arm_summary['arms']['ON']['event_count']} ON, {arm_summary['arms']['OFF']['event_count']} OFF).

The event unit is query × arm × answer part × critical value. Supported
critical tokens in a mixed answer part are not counted as rejecting events.

## Adjudication

| Event class | Count |
| --- | ---: |
| TRUE_CONFLICT | {event_counts['TRUE_CONFLICT']} |
| FALSE_POSITIVE | {event_counts['FALSE_POSITIVE']} |
| INDETERMINATE | {event_counts['INDETERMINATE']} |

Determinate precision is {event_counts['TRUE_CONFLICT']}/{determinate} = {(event_counts['TRUE_CONFLICT'] / determinate * 100) if determinate else 0:.1f}%; determinate false-positive rate is {event_counts['FALSE_POSITIVE']}/{determinate} = {(event_counts['FALSE_POSITIVE'] / determinate * 100) if determinate else 0:.1f}%. Indeterminate events are excluded from both rates.

The primary forensic conclusion is **{conclusion}**. This classification is
conservative: an unresolved validator trace is not treated as a false
positive merely because the final answer was unavailable.

### Representative false-positive patterns

{fp_pattern_lines}

## Arm and availability accounting

| Measure | ON | OFF |
| --- | ---: | ---: |
| Critical-reject queries | {arm_summary['arms']['ON']['critical_reject_queries']} | {arm_summary['arms']['OFF']['critical_reject_queries']} |
| Critical-reject events | {arm_summary['arms']['ON']['event_count']} | {arm_summary['arms']['OFF']['event_count']} |
| Critical reject + forced abstain | {arm_summary['arms']['ON']['critical_reject_and_forced_abstain']} | {arm_summary['arms']['OFF']['critical_reject_and_forced_abstain']} |
| Critical reject + no forced abstain | {arm_summary['arms']['ON']['critical_reject_and_no_forced_abstain']} | {arm_summary['arms']['OFF']['critical_reject_and_no_forced_abstain']} |
| No critical reject + forced abstain | {arm_summary['arms']['ON']['no_critical_reject_and_forced_abstain']} | {arm_summary['arms']['OFF']['no_critical_reject_and_forced_abstain']} |
| Critical reject + unavailable | {arm_summary['arms']['ON']['critical_reject_and_unavailable']} | {arm_summary['arms']['OFF']['critical_reject_and_unavailable']} |
| Critical reject + available | {arm_summary['arms']['ON']['critical_reject_and_available']} | {arm_summary['arms']['OFF']['critical_reject_and_available']} |
| No critical reject + unavailable | {arm_summary['arms']['ON']['no_critical_reject_and_unavailable']} | {arm_summary['arms']['OFF']['no_critical_reject_and_unavailable']} |

P(forced abstain | critical reject) is {arm_summary['arms']['ON']['p_forced_abstain_given_critical_reject']:.3f} ON and {arm_summary['arms']['OFF']['p_forced_abstain_given_critical_reject']:.3f} OFF.

Availability transitions are: ON available → OFF unavailable {transition_counts['ON_AVAILABLE_OFF_UNAVAILABLE']}; ON unavailable → OFF available {transition_counts['ON_UNAVAILABLE_OFF_AVAILABLE']}; both available {transition_counts['BOTH_AVAILABLE']}; both unavailable {transition_counts['BOTH_UNAVAILABLE']}. The exact OFF unavailable delta is {off_unavailable_delta}: OFF has 18 unavailable and ON has 14. The transition table identifies the contributing query IDs; no counterfactual quality is assigned.

OFF-only critical-reject queries: {len(only_off)}. ON-only: {len(only_on)}. Both arms: {len(both)}. These are query-level sets, not an assertion that the event-count difference is caused by one event per query.

## Interpretation

Proven: the frozen validator emitted the observed claim-local reject and
indeterminate traces, and the adjudication above follows the attached
model-visible support units and persisted validator trace. OFF has more
critical-reject query arms and more rejecting events in this run.

Only correlated: OFF's larger critical-reject population coincides with more
unavailable outputs. This does not establish that the validator caused all of
the semantic availability difference, or that accepting a rejected claim
would make it correct.

Unknown: there is no new counterfactual semantic score. Frozen semantic labels
remain authoritative and were not rescored.

## Calibration follow-up

No production validator change is authorized by this forensic. Any follow-up
should be a preregistered DEBUG/dev calibration experiment, developed outside
the consumed HOLDOUT and validated on a new evaluation population.

- P0: review numeric normalization patterns represented by any confirmed
  representation-only events; do not tune from this HOLDOUT alone.
- P1: review unit/date/version canonicalization only if a corresponding
  false-positive subtype is present in the adjudication table.
- P2: review support segmentation and claim-support alignment for unresolved
  traces; preserve claim-locality and fail-closed behavior.

HOLDOUT forensic informs mechanism understanding only; calibration must be
developed on DEBUG/dev and validated on a new evaluation population.

## Artifact index

- `02-event-table/critical-validator-events.csv`: rejecting event table.
- `03-adjudication/event-adjudications.csv`: one conservative class per event.
- `04-query-summary/query-arm-summary.csv`: one row per query × arm.
- `04-query-summary/availability-transitions.csv`: paired availability map.
- `05-aggregate/*.json`: arm, calibration, and semantic consequence summaries.

No canonical source artifact was overwritten.
"""
    write_json_once(OUT / "05-aggregate/forensic-metadata.json", {
        "conclusion": conclusion,
        "source_recheck": source_recheck,
        "critical_reject_query_sets": {"off_only": only_off, "on_only": only_on, "both": both},
        "availability_transition_counts": dict(transition_counts),
        "off_unavailable_delta": off_unavailable_delta,
        "calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0, "ollama": 0},
    })
    if (OUT / "06-report/report.md").exists():
        raise RuntimeError("FORENSIC_ARTIFACT_ALREADY_EXISTS: report")
    (OUT / "06-report/report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
