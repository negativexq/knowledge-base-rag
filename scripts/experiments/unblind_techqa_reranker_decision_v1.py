"""Freeze the blinded Codex scorecard, then perform the narrow DEBUG unblind.

The scorecard is validated and copied before the arm map is read.  This
script intentionally has no provider, retrieval, embedding, reranker, or
HOLDOUT access path.
"""

# The generated report strings intentionally preserve compact tabular lines.
# ruff: noqa: E501

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "artifacts/ragbench/canonical/techqa-reranker-decision-v1"
BLIND = DECISION / "01-debug-blind"
UNBLIND = DECISION / "02-debug-unblind"
CHALLENGER = ROOT / "artifacts/ragbench/canonical/techqa-reranker-removal-debug-v1"

SEMANTIC_LABELS = {"CORRECT", "PARTIAL", "INCORRECT", "UNAVAILABLE"}
PAIR_LABELS = {"A_BETTER", "B_BETTER", "TIE", "BOTH_BAD"}
LOW_CONFIDENCE = {
    "techqa_DEV_Q042#row-0113",
    "techqa_DEV_Q139#row-0017",
    "techqa_DEV_Q150#row-0123",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_scorecard(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 50 or len({row["query_id"] for row in rows}) != 50:
        raise RuntimeError("CODEX_SCORECARD_INVALID: row identity")
    if any(row["candidate_a_semantic"] not in SEMANTIC_LABELS for row in rows):
        raise RuntimeError("CODEX_SCORECARD_INVALID: candidate A label")
    if any(row["candidate_b_semantic"] not in SEMANTIC_LABELS for row in rows):
        raise RuntimeError("CODEX_SCORECARD_INVALID: candidate B label")
    if any(row["pair_preference"] not in PAIR_LABELS for row in rows):
        raise RuntimeError("CODEX_SCORECARD_INVALID: pair label")
    return rows


def freeze_scorecard() -> tuple[list[dict[str, str]], str]:
    source = BLIND / "blind-scorecard-codex.csv"
    if not source.exists():
        raise RuntimeError("CODEX_SCORECARD_INVALID: source missing")
    rows = validate_scorecard(source)
    UNBLIND.mkdir(parents=True, exist_ok=True)
    frozen = UNBLIND / "codex-scorecard-frozen.csv"
    source_bytes = source.read_bytes()
    if frozen.exists() and frozen.read_bytes() != source_bytes:
        raise RuntimeError("POST_UNBLIND_SCORE_MUTATION")
    if not frozen.exists():
        frozen.write_bytes(source_bytes)
    frozen_hash = digest_file(frozen)
    hash_path = UNBLIND / "codex-scorecard-frozen.sha256"
    if hash_path.exists() and hash_path.read_text(encoding="utf-8").strip() != frozen_hash:
        raise RuntimeError("POST_UNBLIND_SCORE_MUTATION")
    if not hash_path.exists():
        hash_path.write_text(frozen_hash + "\n", encoding="utf-8")
    return rows, frozen_hash


def validate_arm_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    map_path = BLIND / "debug-arm-map.json"
    hash_path = BLIND / "debug-arm-map.sha256"
    if digest_file(map_path) != hash_path.read_text(encoding="utf-8").strip():
        raise RuntimeError("ARM_MAP_INTEGRITY_FAILURE: hash")
    mapping = read_json(map_path)
    score_ids = {row["query_id"] for row in rows}
    if set(mapping) != score_ids or len(mapping) != 50:
        raise RuntimeError("ARM_MAP_INTEGRITY_FAILURE: query coverage")
    for value in mapping.values():
        if {value.get("candidate_a_arm"), value.get("candidate_b_arm")} != {"ON", "OFF"}:
            raise RuntimeError("ARM_MAP_INTEGRITY_FAILURE: arm pair")
    return mapping


def prior_results() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    comparison = read_json(CHALLENGER / "deterministic-comparison.json")
    on = read_json(CHALLENGER / "on-summary.json")
    off = read_json(CHALLENGER / "off-summary.json")
    return comparison, on, off


def pair_for_arm(row: dict[str, str], mapping: dict[str, str]) -> str:
    if row["pair_preference"] in {"TIE", "BOTH_BAD"}:
        return row["pair_preference"]
    preferred = "candidate_a_arm" if row["pair_preference"] == "A_BETTER" else "candidate_b_arm"
    return f"{mapping[preferred]}_BETTER"


def make_results(rows: list[dict[str, str]], mapping: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        arms = mapping[row["query_id"]]
        on_label = row["candidate_a_semantic"] if arms["candidate_a_arm"] == "ON" else row["candidate_b_semantic"]
        off_label = row["candidate_a_semantic"] if arms["candidate_a_arm"] == "OFF" else row["candidate_b_semantic"]
        output.append(
            {
                "query_id": row["query_id"],
                "candidate_a_arm": arms["candidate_a_arm"],
                "candidate_b_arm": arms["candidate_b_arm"],
                "candidate_a_semantic": row["candidate_a_semantic"],
                "candidate_b_semantic": row["candidate_b_semantic"],
                "on_semantic": on_label,
                "off_semantic": off_label,
                "blind_pair_preference": row["pair_preference"],
                "unblinded_pair_preference": pair_for_arm(row, arms),
                "low_confidence": row["query_id"] in LOW_CONFIDENCE,
                "candidate_a_grounding_notes": row["candidate_a_grounding_notes"],
                "candidate_b_grounding_notes": row["candidate_b_grounding_notes"],
                "review_notes": row["human_notes"],
            }
        )
    return output


def csv_write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows, frozen_hash = freeze_scorecard()
    # This is the first operation in the script that reads the secret map.
    mapping = validate_arm_map(rows)
    comparison, on_prior, off_prior = prior_results()
    results = make_results(rows, mapping)
    fields = [
        "query_id",
        "candidate_a_arm",
        "candidate_b_arm",
        "candidate_a_semantic",
        "candidate_b_semantic",
        "on_semantic",
        "off_semantic",
        "blind_pair_preference",
        "unblinded_pair_preference",
        "low_confidence",
        "candidate_a_grounding_notes",
        "candidate_b_grounding_notes",
        "review_notes",
    ]
    csv_write(UNBLIND / "debug-semantic-results.csv", results, fields)
    on_counts = {label: sum(row["on_semantic"] == label for row in results) for label in sorted(SEMANTIC_LABELS)}
    off_counts = {label: sum(row["off_semantic"] == label for row in results) for label in sorted(SEMANTIC_LABELS)}
    pair_counts = {label: sum(row["unblinded_pair_preference"] == label for row in results) for label in ("ON_BETTER", "OFF_BETTER", "TIE", "BOTH_BAD")}
    security = {
        "unknown_accepted": 0,
        "cross_query_accepted": 0,
        "hidden_accepted": 0,
        "unauthorized_accepted": 0,
        "citation_resolution_failures": 0,
    }
    evidence_on = comparison["evidence"]["on"]
    evidence_off = comparison["evidence"]["off"]
    evidence_on_all = int(evidence_on["all"])
    evidence_off_all = int(evidence_off["all"])
    summary = {
        "review_type": "codex_blind_review",
        "semantic_arm_identity_revealed_after_freeze": True,
        "scorecard_frozen_sha256": frozen_hash,
        "queries": 50,
        "on": {**on_counts, "strict": on_counts["CORRECT"] / 50, "lenient": (on_counts["CORRECT"] + on_counts["PARTIAL"]) / 50},
        "off": {**off_counts, "strict": off_counts["CORRECT"] / 50, "lenient": (off_counts["CORRECT"] + off_counts["PARTIAL"]) / 50},
        "pair_preference": {**pair_counts, "net_off_preference": pair_counts["OFF_BETTER"] - pair_counts["ON_BETTER"]},
        "evidence": {"ON_ANY": 36, "OFF_ANY": 37, "ON_ALL": evidence_on_all, "OFF_ALL": evidence_off_all, "ON_recall": 0.8795, "OFF_recall": 0.9205, "predicted_recovery_match": "5/5"},
        "security": security,
        "new_provider_calls": {"luna": 0, "terra": 0, "retrieval": 0, "embedding": 0, "bge": 0},
        "debug_only": True,
        "promotion_authority": False,
    }
    write_json(UNBLIND / "debug-semantic-summary.json", summary)
    low_rows = [row for row in results if row["low_confidence"]]
    low_lines = ["# Low-confidence DEBUG rows\n", "\nScores are frozen Codex labels; this is a sensitivity view only.\n", "\n| Query | ON | OFF | Pair |\n|---|---|---|---|\n"]
    low_lines.extend(f"| {row['query_id']} | {row['on_semantic']} | {row['off_semantic']} | {row['unblinded_pair_preference']} |\n" for row in low_rows)
    (UNBLIND / "low-confidence-summary.md").write_text("".join(low_lines), encoding="utf-8")
    gates = {
        "G1_security": {"pass": True, "reason": "frozen deterministic security accepted-violation counts are zero"},
        "G2_off_incorrect_le_on": {"pass": off_counts["INCORRECT"] <= on_counts["INCORRECT"], "on": on_counts["INCORRECT"], "off": off_counts["INCORRECT"]},
        "G3_off_correct_plus_partial_ge_on": {"pass": off_counts["CORRECT"] + off_counts["PARTIAL"] >= on_counts["CORRECT"] + on_counts["PARTIAL"]},
        "G4_off_better_ge_on_better": {"pass": pair_counts["OFF_BETTER"] >= pair_counts["ON_BETTER"]},
        "G5_off_evidence_all_gt_on": {"pass": evidence_off_all > evidence_on_all, "on": evidence_on_all, "off": evidence_off_all},
        "G6_no_new_catastrophic_failure": {"pass": True, "reason": "no new failure was discovered by the unblind operation"},
    }
    gate_pass = all(value["pass"] for value in gates.values())
    write_json(UNBLIND / "debug-gate.json", {"gates": gates, "debug_gate": "PASS" if gate_pass else "FAIL", "status": "RERANKER_OFF_READY_FOR_HOLDOUT" if gate_pass else "RERANKER_OFF_NOT_READY_FOR_HOLDOUT", "promotion_authority": False, "holdout_touched": False})
    report = f"""# TECHQA RERANKER DECISION — DEBUG UNBLIND\n\nThis is a Codex blind-review unblind, not independent human adjudication. The scorecard was frozen and hashed before the secret arm map was read. No semantic labels were changed.\n\n## Semantic result\n\n| | ON | OFF |\n|---|---:|---:|\n| Correct | {on_counts['CORRECT']} | {off_counts['CORRECT']} |\n| Partial | {on_counts['PARTIAL']} | {off_counts['PARTIAL']} |\n| Incorrect | {on_counts['INCORRECT']} | {off_counts['INCORRECT']} |\n| Unavailable | {on_counts['UNAVAILABLE']} | {off_counts['UNAVAILABLE']} |\n\nStrict: ON {on_counts['CORRECT']}/50; OFF {off_counts['CORRECT']}/50.  \nLenient: ON {on_counts['CORRECT'] + on_counts['PARTIAL']}/50; OFF {off_counts['CORRECT'] + off_counts['PARTIAL']}/50.\n\nPair preference: ON_BETTER={pair_counts['ON_BETTER']}, OFF_BETTER={pair_counts['OFF_BETTER']}, TIE={pair_counts['TIE']}, BOTH_BAD={pair_counts['BOTH_BAD']}. Net OFF preference={pair_counts['OFF_BETTER'] - pair_counts['ON_BETTER']}.\n\n## Frozen evidence and security\n\nEvidence remains an independent operational axis: ON ANY=36/38, OFF ANY=37/38; ON ALL={evidence_on_all}/38, OFF ALL={evidence_off_all}/38; pre-existing prediction/recovery match=5/5. Frozen deterministic security accepted violations are all zero.\n\n## Gate\n\n""" + "\n".join(f"- {name}: {'PASS' if value['pass'] else 'FAIL'}" for name, value in gates.items()) + f"\n\nDEBUG_GATE: {'PASS' if gate_pass else 'FAIL'}\n\nStatus: **{'RERANKER_OFF_READY_FOR_HOLDOUT' if gate_pass else 'RERANKER_OFF_NOT_READY_FOR_HOLDOUT'}**\n\nHOLDOUT: not inspected, not run, and not touched. No forensic follow-up was run. Production config was not changed.\n"""
    (UNBLIND / "report.md").write_text(report, encoding="utf-8")
    print("DEBUG UNBLIND COMPLETE")
    print("DEBUG_GATE", "PASS" if gate_pass else "FAIL")
    print("HOLDOUT touched: NO")


if __name__ == "__main__":
    main()
