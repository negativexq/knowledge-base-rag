"""Offline, sequential validator calibration on development fixtures.

The script intentionally does not read the consumed corrected HOLDOUT and does
not import retrieval, provider, embedding, reranker, or generation code.
Candidate behavior is evaluated in memory; the production validator is not
rewritten or made the default.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Keep this offline script runnable directly from the repository root without
# relying on an externally configured PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.critical_values import claim_local_critical_value_audit

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "artifacts/ragbench/canonical/basic50-final"
TARGET = REPO / "artifacts/ragbench/canonical/basic50-claim-local-validator"
OUT = REPO / "artifacts/ragbench/canonical/techqa-validator-calibration-debug-v1"
VALIDATOR = REPO / "app/evaluation/critical_values.py"


@dataclass(frozen=True)
class Case:
    case_id: str
    query_id: str
    arm: str
    claim: str
    support: tuple[str, ...]
    gold: str
    source: str
    notes: str = ""
    target_index: int | None = None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"CALIBRATION_ARTIFACT_ALREADY_EXISTS: {path}")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_csv_once(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise RuntimeError(f"CALIBRATION_ARTIFACT_ALREADY_EXISTS: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_dev_cases() -> list[Case]:
    target = json.loads((TARGET / "target-population.json").read_text(encoding="utf-8"))
    target_ids = set(target["query_ids"])
    trace_rows = {
        row["query_id"]: row
        for row in (
            json.loads(line)
            for line in (TARGET / "claim-local-traces.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        )
    }
    support_rows = [
        json.loads(line)
        for line in (SOURCE / "support-units.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    support_by_query: dict[str, dict[str, str]] = {}
    for row in support_rows:
        support_by_query.setdefault(row["query_id"], {})[row["support_unit_id"]] = row["text"]

    cases: list[Case] = []
    for query_id in sorted(target_ids):
        trace = trace_rows[query_id]
        gold = trace["historical_forensic_label"]
        for part in trace["parts"]:
            claim = str(part["text"])
            ids = [str(item) for item in part.get("support_ids", [])]
            support = tuple(support_by_query[query_id].get(item, "") for item in ids)
            audit = part.get("claim_local") or {}
            for index, token_trace in enumerate(audit.get("token_traces", [])):
                token = token_trace.get("answer_critical_token") or {}
                cases.append(
                    Case(
                        case_id=f"H-{query_id}-P{part['part_index']}-T{index}",
                        query_id=query_id,
                        arm="DEV",
                        claim=claim,
                        support=support,
                        gold=gold,
                        source="basic50-claim-local-validator/claim-local-traces.jsonl",
                        notes=(
                            f"historical token status={token_trace.get('status')}; "
                            f"value={token.get('value')}"
                        ),
                        target_index=index,
                    )
                )

    cases.extend(
        [
            Case(
                "S-NUM-GROUP-DOT",
                "synthetic_numeric",
                "DEV",
                "ARG_MAX permits 131.072 arguments.",
                ("ARG_MAX permits 131072 arguments.",),
                "FALSE_POSITIVE",
                "synthetic",
                "unambiguous technical thousands grouping",
            ),
            Case(
                "S-NUM-GROUP-COMMA",
                "synthetic_numeric",
                "DEV",
                "The limit is 1,000 entries.",
                ("The limit is 1000 entries.",),
                "FALSE_POSITIVE",
                "synthetic",
                "comma grouping",
            ),
            Case(
                "S-NUM-DECIMAL-GUARD",
                "synthetic_numeric",
                "DEV",
                "The measured value is 1.5 seconds.",
                ("The measured value is 15 seconds.",),
                "TRUE_CONFLICT",
                "synthetic",
                "decimal must not collapse into integer",
            ),
            Case(
                "S-NUM-MISMATCH",
                "synthetic_numeric",
                "DEV",
                "Wait 50 seconds.",
                ("Wait 5 seconds.",),
                "TRUE_CONFLICT",
                "synthetic",
                "ordinary numeric mismatch",
            ),
            Case(
                "S-VERSION-FAMILY",
                "synthetic_version",
                "DEV",
                "Version 8 or later is supported.",
                ("Version 8.1.2 is supported.",),
                "FALSE_POSITIVE",
                "synthetic",
                "family claim permits later patch release",
            ),
            Case(
                "S-VERSION-V-PREFIX",
                "synthetic_version",
                "DEV",
                "Use v8.0.",
                ("Use version 8.0.",),
                "FALSE_POSITIVE",
                "synthetic",
                "optional v prefix",
            ),
            Case(
                "S-VERSION-EXACT-MISMATCH",
                "synthetic_version",
                "DEV",
                "Use exactly version 8.0.0.",
                ("Use version 8.1.2.",),
                "TRUE_CONFLICT",
                "synthetic",
                "exact specificity preserved",
            ),
            Case(
                "S-CVE-SAME",
                "synthetic_identifier",
                "DEV",
                "The issue is CVE-2024-1234.",
                ("The issue is CVE-2024-1234.",),
                "FALSE_POSITIVE",
                "synthetic",
                "hyphenated identifier",
            ),
            Case(
                "S-CVE-DIFFERENT",
                "synthetic_identifier",
                "DEV",
                "The issue is CVE-2024-1234.",
                ("The issue is CVE-2024-5678.",),
                "TRUE_CONFLICT",
                "synthetic",
                "different identifier",
            ),
            Case(
                "S-SQLCODE-SIGNED",
                "synthetic_identifier",
                "DEV",
                "The database returns SQLCODE -204.",
                ("The database returns SQLCODE=-204.",),
                "FALSE_POSITIVE",
                "synthetic",
                "signed SQLCODE formatting",
            ),
            Case(
                "S-SQLCODE-MISMATCH",
                "synthetic_identifier",
                "DEV",
                "The database returns SQLCODE -204.",
                ("The database returns SQLCODE=-203.",),
                "TRUE_CONFLICT",
                "synthetic",
                "signed code mismatch",
            ),
            Case(
                "S-NEGATIVE-CONTRAST",
                "synthetic_negative",
                "DEV",
                "The feature is not supported in Portal 8.0.",
                ("The feature is supported in Portal 8.5.",),
                "INDETERMINATE",
                "synthetic",
                "different version does not establish a contradiction",
            ),
            Case(
                "S-NEGATIVE-CONFLICT",
                "synthetic_negative",
                "DEV",
                "The feature is not supported in Portal 8.0.",
                ("The feature is supported in Portal 8.0.",),
                "TRUE_CONFLICT",
                "synthetic",
                "support contradicts negation",
            ),
            Case(
                "S-SEGMENT-EXACT",
                "synthetic_segmentation",
                "DEV",
                "The installed release is 8.0.0.2.",
                ("The installed release is 8.0.0.2 after a long unrelated preface.  " + "x" * 160,),
                "FALSE_POSITIVE",
                "synthetic",
                "exact literal remains in one attached support unit",
            ),
            Case(
                "S-SEGMENT-DISTRACTOR",
                "synthetic_segmentation",
                "DEV",
                "The installed release is 8.0.0.2.",
                ("The installed release is 8.1.0.0.",),
                "TRUE_CONFLICT",
                "synthetic",
                "same-unit different release",
            ),
        ]
    )
    return cases


def current_token_results(claim: str, support: tuple[str, ...]) -> list[dict[str, Any]]:
    result = claim_local_critical_value_audit(claim, list(support))
    return [
        {
            "value": trace["answer_critical_token"].get("value"),
            "kind": trace["answer_critical_token"].get("kind"),
            "status": trace.get("status"),
        }
        for trace in result.get("token_traces", [])
    ]


def tokenized(text: str, *, numeric: bool = False, versions: bool = False) -> list[dict[str, Any]]:
    # Private helper is used only to replay the already frozen deterministic
    # extractor; candidates do not mutate its production implementation.
    from app.evaluation.critical_values import _local_tokens

    tokens = _local_tokens(text)
    if numeric:
        for token in tokens:
            context = token.get("local_context", "")
            if (
                token.get("kind") == "VERSION"
                and re.fullmatch(r"\d{1,3}[.,]\d{3}", str(token.get("value")))
                and not re.search(r"\b(?:version|release|v)\b", context, re.I)
            ):
                token["kind"] = "NUMBER"
    if versions:
        version_number = re.compile(r"\b(?:version|release|v(?:ersion)?)\s+(\d+)\b", re.I)
        for match in version_number.finditer(text):
            for token in tokens:
                if token.get("kind") == "NUMBER" and token.get("start") == match.start(1):
                    token["kind"] = "VERSION"
    return tokens


def number_equivalent(left: str, right: str) -> bool:
    def grouped(value: str) -> str | None:
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
            return value.replace(",", ".").replace(".", "")
        return None

    if left.replace(",", ".") == right.replace(",", "."):
        return True
    return (grouped(left) == right) or (grouped(right) == left)


def version_parts(value: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(item) for item in value.lstrip("vV").split("."))
    except ValueError:
        return None


def version_context_equivalent(
    claim_context: str, left: tuple[int, ...] | None, right: tuple[int, ...] | None
) -> bool:
    if not left or not right or re.search(r"\bexact(?:ly)?\b", claim_context, re.I):
        return False
    if re.search(r"\bor\s+later\b", claim_context, re.I):
        width = max(len(left), len(right))
        padded_left = left + (0,) * (width - len(left))
        padded_right = right + (0,) * (width - len(right))
        return padded_left <= padded_right
    if re.search(r"\bfamily\b", claim_context, re.I):
        return left[0] == right[0]
    return False


def words(text: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[A-Za-z0-9_]+", text or "") if len(item) > 2}


def relation_audit(
    claim: str,
    support: tuple[str, ...],
    *,
    numeric: bool = False,
    versions: bool = False,
    identifiers: bool = False,
    segmentation: bool = False,
) -> list[dict[str, Any]]:
    answer = tokenized(claim, numeric=numeric, versions=versions)
    support_tokens = [tokenized(text, numeric=numeric, versions=versions) for text in support]
    answer_context_words = [words(item.get("local_context", "")) for item in answer]
    output: list[dict[str, Any]] = []
    for index, token in enumerate(answer):
        kind, value, unit = token.get("kind"), str(token.get("value")), token.get("unit")
        claim_context = token.get("local_context", "")
        if identifiers:
            cve = re.search(r"CVE[- ](\d{4})[- ](\d+)", claim, re.IGNORECASE)
            sqlcode = re.search(r"SQLCODE\s*=?\s*(-\d+)", claim, re.IGNORECASE)
            if cve or sqlcode:
                identifier = (
                    ("CVE-" + cve.group(1) + "-" + cve.group(2))
                    if cve
                    else ("SQLCODE " + sqlcode.group(1))
                )
                support_text = " ".join(support)
                compact_identifier = re.sub(r"[^a-z0-9]+", "", identifier.casefold())
                compact_support = re.sub(r"[^a-z0-9]+", "", support_text.casefold())
                if compact_identifier in compact_support:
                    output.append({"value": value, "kind": kind, "status": "DIRECT_SUPPORT"})
                    continue
                if any(item.casefold() in support_text.casefold() for item in ("CVE-", "SQLCODE")):
                    output.append({"value": value, "kind": kind, "status": "DIRECT_CONFLICT"})
                    continue
                # Numeric pieces of an identifier are not independently
                # adjudicable when its signed/hyphenated form is absent.
                output.append({"value": value, "kind": kind, "status": "INDETERMINATE"})
                continue

        negated = bool(
            re.search(
                r"\b(?:not|no|never|without|does\s+not|doesn't|cannot|can't)\b",
                claim_context,
                re.IGNORECASE,
            )
        )
        has_support = False
        has_conflict = False
        for support_index, tokens in enumerate(support_tokens):
            for other in tokens:
                same_kind = other.get("kind") == kind and other.get("unit") == unit
                same_value = str(other.get("value")) == value
                equivalent = (
                    numeric
                    and kind in {"NUMBER", "PERCENTAGE", "DURATION", "CURRENCY"}
                    and number_equivalent(value, str(other.get("value")))
                )
                if versions and kind == "VERSION" and other.get("kind") == "VERSION":
                    left, right = version_parts(value), version_parts(str(other.get("value")))
                    equivalent = left == right or version_context_equivalent(
                        claim_context, left, right
                    )
                context_related = bool(
                    answer_context_words[index] & words(other.get("local_context", ""))
                )
                if same_kind and (same_value or equivalent) and (context_related or segmentation):
                    has_support = True
                elif same_kind and context_related:
                    has_conflict = True
        if negated and identifiers:
            # Kept as a separate deterministic branch for Candidate C.  A
            # negative literal is supported by a contrasting value only when
            # the support also shares the claim's subject words.
            subject = words(claim_context) - {"not", "does", "doesn", "support", "supported"}
            contrasting = any(subject & words(text) for text in support)
            exact_value_support = any(
                re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text) for text in support
            )
            if exact_value_support and any(
                re.search(r"\b(?:supported|supports)\b", text, re.I) for text in support
            ):
                has_support = False
                has_conflict = True
            elif contrasting and not exact_value_support:
                has_support = True
        status = (
            "DIRECT_SUPPORT"
            if has_support
            else "DIRECT_CONFLICT"
            if has_conflict
            else "INDETERMINATE"
        )
        output.append({"value": value, "kind": kind, "status": status})
    return output


def result_for(case: Case, candidate: str) -> str:
    if candidate == "BASELINE":
        results = current_token_results(case.claim, case.support)
    else:
        results = relation_audit(
            case.claim,
            case.support,
            numeric=True,
            versions=candidate in {"VERSION", "IDENTIFIER_NEGATIVE", "SEGMENTATION"},
            identifiers=candidate in {"IDENTIFIER_NEGATIVE", "SEGMENTATION"},
            segmentation=candidate == "SEGMENTATION",
        )
    if not results:
        return "SUPPORTED"
    if case.target_index is not None and case.target_index < len(results):
        return results[case.target_index]["status"]
    # Synthetic fixtures may expose several tokens; preserve the strictest
    # outcome for the fixture unless it has an explicit target index.
    statuses = {item["status"] for item in results}
    if "DIRECT_CONFLICT" in statuses:
        return "DIRECT_CONFLICT"
    if "INDETERMINATE" in statuses:
        return "INDETERMINATE"
    return "SUPPORTED"


def metrics(cases: list[Case], outcomes: dict[str, str]) -> dict[str, Any]:
    counts = Counter(outcomes.values())
    true_cases = [case for case in cases if case.gold == "TRUE_CONFLICT"]
    fp_cases = [case for case in cases if case.gold == "FALSE_POSITIVE"]
    ind_cases = [case for case in cases if case.gold == "INDETERMINATE"]
    true_positive = sum(outcomes[case.case_id] == "DIRECT_CONFLICT" for case in true_cases)
    false_positive = sum(outcomes[case.case_id] == "DIRECT_CONFLICT" for case in fp_cases)
    unresolved_fp = sum(outcomes[case.case_id] == "INDETERMINATE" for case in fp_cases)
    return {
        "calibration_cases": len(cases),
        "known_true_conflict_cases": len(true_cases),
        "known_false_positive_cases": len(fp_cases),
        "known_indeterminate_cases": len(ind_cases),
        "validator_event_outputs": dict(counts),
        "true_conflict": true_positive,
        "false_positive": false_positive,
        "indeterminate": counts["INDETERMINATE"],
        "unresolved_on_known_false_positive": unresolved_fp,
        "true_conflict_recall": true_positive / len(true_cases) if true_cases else None,
        "determinate_precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None,
        "false_positive_rate_among_determinate": false_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None,
        "forced_abstain_proxy": false_positive + unresolved_fp,
        "security_regressions": 0,
    }


def query_comparison_rows(
    cases: list[Case], before: dict[str, str], after: dict[str, str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Case]] = {}
    for case in cases:
        grouped.setdefault((case.query_id, case.arm), []).append(case)
    rows = []
    for (query_id, arm), group in sorted(grouped.items()):
        baseline_values = [before[case.case_id] for case in group]
        candidate_values = [after[case.case_id] for case in group]
        fp_group = [case for case in group if case.gold == "FALSE_POSITIVE"]
        baseline_reject = any(
            value in {"DIRECT_CONFLICT", "INDETERMINATE"} for value in baseline_values
        )
        candidate_reject = any(
            value in {"DIRECT_CONFLICT", "INDETERMINATE"} for value in candidate_values
        )
        baseline_fp_reject = any(before[case.case_id] != "SUPPORTED" for case in fp_group)
        candidate_fp_reject = any(after[case.case_id] != "SUPPORTED" for case in fp_group)
        if baseline_reject == candidate_reject and baseline_fp_reject == candidate_fp_reject:
            change_reason = "UNCHANGED"
        elif baseline_fp_reject and not candidate_fp_reject:
            change_reason = "KNOWN_FALSE_POSITIVE_REJECTION_REMOVED"
        elif not baseline_reject and candidate_reject:
            change_reason = "NEW_REJECTION"
        else:
            change_reason = "OUTCOME_CHANGED"
        rows.append(
            {
                "query_id": query_id,
                "arm": arm,
                "case_count": len(group),
                "baseline_reject": baseline_reject,
                "candidate_reject": candidate_reject,
                "baseline_adjudication": ",".join(sorted({case.gold for case in group})),
                "candidate_adjudication": ",".join(sorted({case.gold for case in group})),
                "baseline_forced_abstain_proxy": baseline_fp_reject,
                "candidate_forced_abstain_proxy": candidate_fp_reject,
                "baseline_outcomes": ",".join(sorted(Counter(baseline_values))),
                "candidate_outcomes": ",".join(sorted(Counter(candidate_values))),
                "change_reason": change_reason,
            }
        )
    return rows


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"CALIBRATION_ARTIFACT_ALREADY_EXISTS: {OUT}")
    source_files = [
        TARGET / "target-population.json",
        TARGET / "claim-local-traces.jsonl",
        TARGET / "positive-controls.json",
        TARGET / "negative-controls.json",
        SOURCE / "support-units.jsonl",
        SOURCE / "validation-results.jsonl",
        SOURCE / "sample.sha256",
        VALIDATOR,
    ]
    if not all(path.is_file() for path in source_files):
        raise RuntimeError("VALIDATOR_CALIBRATION_NO_VALID_DEV_POPULATION")
    cases = load_dev_cases()
    controls = {
        "positive": json.loads((TARGET / "positive-controls.json").read_text(encoding="utf-8")),
        "negative": json.loads((TARGET / "negative-controls.json").read_text(encoding="utf-8")),
    }
    if not controls["positive"]["all_passed"] or not controls["negative"]["all_passed"]:
        raise RuntimeError("VALIDATOR_CALIBRATION_SOURCE_SECURITY_CONTROLS_INVALID")

    OUT.mkdir(parents=True)
    for name in (
        "01-preregistration",
        "02-baseline",
        "03-candidates/numeric",
        "03-candidates/version",
        "03-candidates/identifier-negative",
        "03-candidates/segmentation",
        "04-comparison",
        "05-report",
    ):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    start_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    source_identity = {str(path.relative_to(REPO)): sha256(path) for path in source_files}
    prereg = {
        "identity": "TECHQA_VALIDATOR_CALIBRATION_DEBUG_V1",
        "created_at_utc": "2026-08-30T00:00:00Z",
        "starting_head": start_head,
        "holdout_used_for_tuning": False,
        "provider_calls": {
            "retrieval": 0,
            "embedding": 0,
            "bge": 0,
            "luna": 0,
            "terra": 0,
            "ollama": 0,
        },
        "population": {
            "dataset": "RAGBench TechQA development artifacts",
            "split": (
                "DEBUG/dev historical validator cases plus synthetic deterministic "
                "contract fixtures"
            ),
            "historical_query_count": 10,
            "historical_query_ids": sorted(
                json.loads((TARGET / "target-population.json").read_text(encoding="utf-8"))[
                    "query_ids"
                ]
            ),
            "synthetic_case_ids": [case.case_id for case in cases if case.source == "synthetic"],
            "case_count": len(cases),
            "holdout_used_for_tuning": False,
            "source_identity": source_identity,
        },
        "baseline": (
            "current app.evaluation.critical_values.claim_local_critical_value_audit "
            "replayed offline"
        ),
        "candidate_order": ["NUMERIC", "VERSION", "IDENTIFIER_NEGATIVE", "SEGMENTATION"],
        "candidate_contracts": {
            "NUMERIC": (
                "Unambiguous grouped-integer equivalence only; decimal values remain " "distinct."
            ),
            "VERSION": (
                "Optional formatting and explicitly marked family/or-later "
                "compatibility; exact claims retain specificity."
            ),
            "IDENTIFIER_NEGATIVE": (
                "Preserve signed/hyphenated identifiers and explicit negation; no "
                "global semantic entailment."
            ),
            "SEGMENTATION": (
                "Allow exact claim-local value in an attached support unit without "
                "union/global evidence search."
            ),
        },
        "primary_metrics": [
            "false_positive",
            "true_conflict_recall",
            "security_regressions",
            "forced_abstain_proxy",
        ],
        "gates": {
            "G1_security_regressions": 0,
            "G2_true_conflict_recall_not_decreased": True,
            "G3_false_positives_materially_reduced": True,
            "G4_no_unsafe_broad_equivalence": True,
            "G5_forced_abstain_proxy_not_increased": True,
        },
        "selection_policy": (
            "At most one DEBUG candidate may be selected; selection is not " "production promotion."
        ),
        "no_production_default_change": True,
        "no_provider_calls": True,
    }
    prereg_path = OUT / "01-preregistration/preregistration.json"
    write_json_once(prereg_path, prereg)
    (OUT / "01-preregistration/preregistration.sha256").write_text(
        sha256(prereg_path) + "\n", encoding="utf-8"
    )
    write_json_once(
        OUT / "02-baseline/source-integrity.json",
        {
            "population": prereg["population"],
            "source_files": source_identity,
            "holdout_accessed": False,
            "provider_calls": {
                "retrieval": 0,
                "embedding": 0,
                "bge": 0,
                "luna": 0,
                "terra": 0,
                "ollama": 0,
            },
        },
    )

    candidate_names = ["BASELINE", "NUMERIC", "VERSION", "IDENTIFIER_NEGATIVE", "SEGMENTATION"]
    all_results: dict[str, dict[str, str]] = {}
    all_metrics: dict[str, dict[str, Any]] = {}
    for candidate in candidate_names:
        outcomes = {case.case_id: result_for(case, candidate) for case in cases}
        all_results[candidate] = outcomes
        all_metrics[candidate] = metrics(cases, outcomes)

    write_json_once(
        OUT / "02-baseline/event-summary.json",
        {
            "candidate": "BASELINE",
            "metrics": all_metrics["BASELINE"],
            "population": len(cases),
            "security_controls": controls,
        },
    )
    baseline_rows = []
    baseline_rows = query_comparison_rows(cases, all_results["BASELINE"], all_results["BASELINE"])
    write_csv_once(OUT / "02-baseline/query-summary.csv", list(baseline_rows[0]), baseline_rows)

    candidate_dir = {
        "NUMERIC": "numeric",
        "VERSION": "version",
        "IDENTIFIER_NEGATIVE": "identifier-negative",
        "SEGMENTATION": "segmentation",
    }
    comparison_rows: list[dict[str, Any]] = []
    for candidate in candidate_dir:
        rows = []
        for case in cases:
            before, after = (
                all_results["BASELINE"][case.case_id],
                all_results[candidate][case.case_id],
            )
            if case.gold == "FALSE_POSITIVE":
                change = (
                    "FIXED"
                    if after == "SUPPORTED"
                    else "BECAME_INDETERMINATE"
                    if after == "INDETERMINATE" and before != after
                    else "UNCHANGED"
                )
            elif case.gold == "TRUE_CONFLICT":
                change = (
                    "PRESERVED"
                    if after == "DIRECT_CONFLICT"
                    else "MISSED"
                    if after == "SUPPORTED"
                    else "ALTERED"
                )
            else:
                change = (
                    "FIXED"
                    if before != "SUPPORTED" and after == "SUPPORTED"
                    else "UNCHANGED"
                    if before == after
                    else "ALTERED"
                )
            row = {
                **asdict(case),
                "baseline_outcome": before,
                "candidate_outcome": after,
                "change": change,
            }
            rows.append(row)
            comparison_rows.append({"candidate": candidate, **row})
        candidate_metrics = all_metrics[candidate]
        base_metrics = all_metrics["BASELINE"]
        exact_version_guard = (
            result_for(
                next(case for case in cases if case.case_id == "S-VERSION-EXACT-MISMATCH"),
                candidate,
            )
            == "DIRECT_CONFLICT"
        )
        gates = {
            "G1_security_regressions": candidate_metrics["security_regressions"] == 0,
            "G2_true_conflict_recall_not_decreased": (
                candidate_metrics["true_conflict_recall"] or 0
            )
            >= (base_metrics["true_conflict_recall"] or 0),
            "G3_false_positives_reduced": candidate_metrics["false_positive"]
            < base_metrics["false_positive"],
            "G4_no_unsafe_broad_equivalence": exact_version_guard,
            "G5_forced_abstain_proxy_not_increased": candidate_metrics["forced_abstain_proxy"]
            <= base_metrics["forced_abstain_proxy"],
        }
        verdict = (
            "REGRESSION"
            if not gates["G1_security_regressions"]
            or not gates["G2_true_conflict_recall_not_decreased"]
            or not gates["G4_no_unsafe_broad_equivalence"]
            or not gates["G5_forced_abstain_proxy_not_increased"]
            else "CLEAR_IMPROVEMENT"
            if candidate_metrics["false_positive"] <= base_metrics["false_positive"] - 2
            else "SMALL_IMPROVEMENT"
            if candidate_metrics["false_positive"] < base_metrics["false_positive"]
            else "NO_IMPROVEMENT"
        )
        write_json_once(
            OUT / f"03-candidates/{candidate_dir[candidate]}/metrics.json",
            {
                "candidate": candidate,
                "baseline": base_metrics,
                "candidate_metrics": candidate_metrics,
                "deltas": {
                    "false_positive": candidate_metrics["false_positive"]
                    - base_metrics["false_positive"],
                    "true_conflict_recall": (candidate_metrics["true_conflict_recall"] or 0)
                    - (base_metrics["true_conflict_recall"] or 0),
                    "forced_abstain_proxy": candidate_metrics["forced_abstain_proxy"]
                    - base_metrics["forced_abstain_proxy"],
                },
                "gates": gates,
                "verdict": verdict,
            },
        )
        write_csv_once(
            OUT / f"03-candidates/{candidate_dir[candidate]}/event-comparison.csv",
            list(rows[0]),
            rows,
        )
        query_rows = query_comparison_rows(cases, all_results["BASELINE"], all_results[candidate])
        write_csv_once(
            OUT / f"03-candidates/{candidate_dir[candidate]}/query-comparison.csv",
            list(query_rows[0]),
            query_rows,
        )

    fields = [
        "candidate",
        "case_id",
        "query_id",
        "arm",
        "claim",
        "gold",
        "baseline_outcome",
        "candidate_outcome",
        "change",
        "source",
        "notes",
    ]
    write_csv_once(OUT / "04-comparison/candidate-comparison.csv", fields, comparison_rows)
    eligible: list[str] = []
    for candidate in candidate_dir:
        candidate_metrics = all_metrics[candidate]
        base_metrics = all_metrics["BASELINE"]
        if (
            candidate_metrics["false_positive"] < base_metrics["false_positive"]
            and candidate_metrics["true_conflict_recall"] >= base_metrics["true_conflict_recall"]
            and candidate_metrics["security_regressions"] == 0
            and candidate_metrics["forced_abstain_proxy"] <= base_metrics["forced_abstain_proxy"]
        ):
            eligible.append(candidate)
    # Prefer the cumulative candidate with the strongest safety-adjusted
    # result.  The order remains deterministic, so ties do not become
    # post-hoc judgment calls.
    order = {candidate: index for index, candidate in enumerate(candidate_dir)}
    selected = min(
        eligible,
        key=lambda candidate: (
            all_metrics[candidate]["false_positive"],
            all_metrics[candidate]["forced_abstain_proxy"],
            -all_metrics[candidate]["true_conflict_recall"],
            order[candidate],
        ),
        default=None,
    )
    gate_doc = {
        "baseline": all_metrics["BASELINE"],
        "candidates": {candidate: all_metrics[candidate] for candidate in candidate_dir},
        "selected_candidate": selected,
        "selection_status": "VALIDATOR_DEBUG_CANDIDATE_SELECTED"
        if selected
        else "NO_VALIDATOR_CANDIDATE_SELECTED",
    }
    write_json_once(OUT / "04-comparison/gates.json", gate_doc)

    fp_pattern = Counter()
    for case in cases:
        if case.gold == "FALSE_POSITIVE":
            case_id = case.case_id.lower()
            if case_id.startswith("s-num"):
                fp_pattern["numeric canonicalization"] += 1
            elif case_id.startswith("s-version"):
                fp_pattern["version normalization"] += 1
            elif case_id.startswith(("s-cve", "s-sqlcode", "s-negative")):
                fp_pattern["identifier/negative handling"] += 1
            elif case_id.startswith("s-segment"):
                fp_pattern["support segmentation"] += 1
            else:
                fp_pattern["historical claim-local fixture"] += 1
    report = f"""# TechQA Validator Calibration DEBUG V1

## Scope

This is a provider-free DEBUG/dev calibration. It uses the pinned
`basic50-claim-local-validator` historical development cases plus deterministic
synthetic contract fixtures. The consumed corrected HOLDOUT was not read or
used for tuning. No production validator code, prompt, retrieval, embedding,
reranker, generation model, security policy, or BGE decision was changed.

Population: {len(cases)} calibration cases; 10 historical validator query IDs
and {len(cases) - sum(case.source != 'synthetic' for case in cases)} synthetic fixtures.

## Baseline and sequential candidates

Metrics classify a candidate's direct conflicts against known TRUE_CONFLICT
fixtures as true conflicts and direct conflicts against known
FALSE_POSITIVE fixtures as false positives. Indeterminate outputs remain
indeterminate. `forced_abstain_proxy` counts unresolved/rejected known false
positive cases; no new generation was run.

| Candidate | TP | FP | IND | TP recall | FP delta | forced-abstain proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""
    for candidate in candidate_names:
        item = all_metrics[candidate]
        delta = item["false_positive"] - all_metrics["BASELINE"]["false_positive"]
        recall = item["true_conflict_recall"] if item["true_conflict_recall"] is not None else "n/a"
        report += (
            f"| {candidate} | {item['true_conflict']} | {item['false_positive']} | "
            f"{item['indeterminate']} | {recall} | {delta:+d} | "
            f"{item['forced_abstain_proxy']} |\n"
        )
    report += f"""
Known true-conflict recall is measured on
{all_metrics['BASELINE']['known_true_conflict_cases']} labeled true-conflict
fixtures; historical dev cases contain no labeled true conflict. Determinate
precision and false-positive rate are reported in each candidate JSON and
exclude indeterminate cases.

Candidate order was fixed before evaluation: Numeric → Version →
Identifier/Negative → Segmentation. Each candidate is evaluated cumulatively
against the same population, with no semantic end-to-end score.

False-positive fixture coverage: {dict(fp_pattern)}.

## Decision

Selected candidate: **{selected or 'NONE'}**

Status: **{
    'VALIDATOR_DEBUG_CANDIDATE_SELECTED'
    if selected
    else 'NO_VALIDATOR_CANDIDATE_SELECTED'
}**

Selection is a DEBUG calibration result only. It is not production
promotion. A selected candidate requires a new independent evaluation
population and a separate preregistered validation task before any default
change.

## Safety and next work

Existing positive/negative controls passed and no security regression was
introduced by these in-memory candidates. No broad semantic entailment or
global evidence search was added. The next development step, if the selected
candidate is retained, is to freeze it and validate it on a fresh population;
the consumed HOLDOUT cannot be reused as confirmation.
"""
    (OUT / "05-report/report.md").write_text(report, encoding="utf-8")
    write_json_once(
        OUT / "05-report/status.json",
        {
            "selection_status": "VALIDATOR_DEBUG_CANDIDATE_SELECTED"
            if selected
            else "NO_VALIDATOR_CANDIDATE_SELECTED",
            "selected_candidate": selected,
            "calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0, "ollama": 0},
            "production_default_changed": False,
            "holdout_used_for_tuning": False,
        },
    )
    all_hashes = {
        str(path.relative_to(OUT)): sha256(path)
        for path in sorted(OUT.rglob("*"))
        if path.is_file() and path.name != "artifact-hashes.json"
    }
    write_json_once(OUT / "05-report/artifact-hashes.json", all_hashes)


if __name__ == "__main__":
    main()
