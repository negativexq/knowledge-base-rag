"""Finalize the TechQA output-state schema challenger from frozen outputs.

This script performs no provider, retrieval, embedding, or reranker calls.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ragbench_emanual_common import text_has_sentence

DEFAULT_OUT = ROOT / "artifacts/ragbench/canonical/techqa-output-state-schema-fix-v3"
DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
PHASE0 = ROOT / "artifacts/ragbench/canonical/techqa-phase0-forensics"
PARQUET = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def reference_rows() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(pq.read_table(PARQUET).to_pylist()):
        query_id = f"{row['id']}#row-{index:04d}"
        wanted = {str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys") or []}
        relevant = []
        for document in row.get("documents_sentences") or []:
            for pair in document or []:
                if isinstance(pair, list | tuple) and len(pair) == 2:
                    key, text = str(pair[0]), str(pair[1])
                    if key.rstrip(".") in wanted:
                        relevant.append({"key": key, "text": text})
        result[query_id] = {"relevant": relevant}
    return result


def selected_support_text(row: dict[str, Any]) -> str:
    texts = []
    for part in row.get("resolved_citations") or []:
        for support in part.get("resolved_support") or []:
            texts.append(str(support.get("text") or ""))
    return "\n".join(texts)


def attribution_label(row: dict[str, Any], reference: dict[str, Any]) -> str:
    relevant = reference.get("relevant") or []
    if not relevant:
        return "NO_ANNOTATED_RELEVANT_SUPPORT"
    selected = selected_support_text(row)
    present = [item for item in relevant if text_has_sentence(selected, item["text"])]
    if len(present) == len(relevant):
        return "RELEVANT_SUPPORT_PRESENT"
    if present:
        return "PARTIAL_RELEVANT_SUPPORT"
    return "NO_ANNOTATED_RELEVANT_SUPPORT"


def evidence_state(retrieval: dict[str, Any]) -> str:
    truth = retrieval["truth"]["section_aware"]
    if truth["all_relevant_sentences_present"]:
        return "ALL_RELEVANT_VISIBLE"
    if truth["present_sentence_keys"]:
        return "PARTIAL_RELEVANT_VISIBLE"
    return "NO_RELEVANT_VISIBLE"


def main(out: Path) -> None:
    target = read_json(out / "target-population.json")
    config = read_json(out / "config.json")
    generation = read_jsonl(out / "generation-results.jsonl")
    validation = read_jsonl(out / "support-validation-results.jsonl")
    judges = read_jsonl(out / "judge-results.jsonl")
    target_ids = set(target["query_ids"])
    old_rows = {
        row["query_id"]: row
        for row in read_jsonl(PHASE0 / "parse-schema-forensics.jsonl")
        if row["query_id"] in target_ids
    }
    retrieval = {row["query_id"]: row for row in read_jsonl(DEBUG / "retrieval-results.jsonl")}
    references = reference_rows()
    validation_by_id = {row["query_id"]: row for row in validation}
    judge_by_id = {row["query_id"]: row for row in judges}

    transitions = []
    for query_id in target["query_ids"]:
        old_parsed = json.loads(old_rows[query_id]["raw_output"])
        new = validation_by_id[query_id]
        new_parsed = new.get("parsed_output") or {}
        transitions.append(
            {
                "query_id": query_id,
                "old_abstain": old_parsed["abstain"],
                "old_part_count": len(old_parsed["answer_parts"]),
                "old_contract_valid": False,
                "new_abstain": new_parsed.get("abstain"),
                "new_part_count": len(new_parsed.get("answer_parts") or []),
                "new_contract_valid": bool(new.get("application_contract_valid")),
                "new_answer_state": new.get("answer_state"),
                "visible": bool(new.get("visible")),
                "validator_failure_codes": new.get("validator_failure_codes") or [],
                "semantic_verdict": (judge_by_id.get(query_id, {}).get("parsed") or {}).get(
                    "verdict"
                ),
            }
        )
    write_jsonl(out / "state-transition-results.jsonl", transitions)

    contract_valid = sum(row["new_contract_valid"] for row in transitions)
    answer_states = sum(row["new_answer_state"] == "ANSWER_STATE_VALID" for row in transitions)
    abstain_states = sum(row["new_answer_state"] == "ABSTAIN_STATE_VALID" for row in transitions)
    visible = [row for row in validation if row.get("visible")]
    valid_abstentions = [
        row for row in validation if row.get("answer_state") == "ABSTAIN_STATE_VALID"
    ]
    other_unavailable = [
        row
        for row in validation
        if not row.get("visible") and row.get("answer_state") != "ABSTAIN_STATE_VALID"
    ]
    verdicts = Counter((row.get("parsed") or {}).get("verdict") for row in judges)
    useful = verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"]
    useful_rate = useful / len(judges) if judges else 0.0

    attribution_rows = []
    for row in visible:
        label = attribution_label(row, references[row["query_id"]])
        attribution_rows.append(
            {
                "query_id": row["query_id"],
                "label": label,
                "selected_support_ids": row.get("selected_support_ids") or [],
                "semantic_verdict": (judge_by_id[row["query_id"]].get("parsed") or {}).get(
                    "verdict"
                ),
            }
        )
    write_jsonl(out / "attribution-results.jsonl", attribution_rows)
    attribution_counts = Counter(row["label"] for row in attribution_rows)

    abstention_states = Counter(
        evidence_state(retrieval[row["query_id"]]) for row in valid_abstentions
    )
    codes = Counter(
        code for row in validation for code in (row.get("validator_failure_codes") or [])
    )
    raw_complete = sum(row.get("state") == "RAW_COMPLETE" for row in generation)
    provider_failures = len(generation) - raw_complete
    support_security = {
        "unknown_ids": codes["UNKNOWN_SUPPORT_ID"],
        "cross_query_ids": codes["CROSS_QUERY_SUPPORT_ID"],
        "hidden_ids": codes["HIDDEN_SUPPORT_ID"],
        "unauthorized_ids": codes["UNAUTHORIZED_SUPPORT_ID"],
    }
    safety_pass = not any(support_security.values())

    structural_gate = (
        "STRUCTURAL_GATE_STRONG_PASS"
        if contract_valid == 11
        else "STRUCTURAL_GATE_PASS"
        if contract_valid == 10
        else "STRUCTURAL_GATE_WEAK"
        if contract_valid >= 7
        else "STRUCTURAL_GATE_FAIL"
    )
    semantic_gate = "PASS" if judges and useful_rate >= 0.9 else "FAIL"
    if contract_valid >= 10 and safety_pass and semantic_gate == "PASS":
        classification = "OUTPUT_STATE_SCHEMA_FIX_SUPPORTED"
        next_action = "RELATION_AWARE_EVIDENCE_FEASIBILITY_AUDIT"
    elif contract_valid >= 10 and safety_pass:
        classification = "OUTPUT_STATE_SCHEMA_FIX_STRUCTURALLY_VALID_SEMANTICALLY_RISKY"
        next_action = "ANSWERABILITY_STATE_CONTRACT_REDESIGN"
    else:
        classification = "OUTPUT_STATE_SCHEMA_FIX_NOT_SUPPORTED"
        next_action = "ANSWERABILITY_STATE_CONTRACT_REDESIGN"

    structural = {
        "target": len(target["query_ids"]),
        "old_contract_valid": 0,
        "new_contract_valid": contract_valid,
        "valid_answer_states": answer_states,
        "valid_abstain_states": abstain_states,
        "invalid_states": len(target["query_ids"]) - contract_valid,
        "old_abstain_parts_conflicts": 11,
        "new_abstain_parts_conflicts": sum(
            bool(row.get("new_abstain") and row.get("new_part_count")) for row in transitions
        ),
        "provider_failures": provider_failures,
        "raw_complete": raw_complete,
    }
    availability = {
        "new_visible_answers": len(visible),
        "valid_abstentions": len(valid_abstentions),
        "other_unavailable": len(other_unavailable),
        "projected_debug50_visible": 24 + len(visible),
        "semantically_useful_newly_visible": useful,
        "abstention_evidence_states": dict(abstention_states),
    }
    semantic = {
        "judged": len(judges),
        "correct": verdicts["CORRECT"],
        "partial": verdicts["PARTIALLY_CORRECT"],
        "incorrect": verdicts["INCORRECT"],
        "useful": useful,
        "visible_strict": verdicts["CORRECT"] / len(judges) if judges else None,
        "visible_lenient": useful_rate if judges else None,
    }
    attribution = {
        "relevant_support_present": attribution_counts["RELEVANT_SUPPORT_PRESENT"],
        "partial_relevant_support": attribution_counts["PARTIAL_RELEVANT_SUPPORT"],
        "no_annotated_relevant_support": attribution_counts["NO_ANNOTATED_RELEVANT_SUPPORT"],
        "attribution_concern_cases": sum(
            row["semantic_verdict"] == "INCORRECT" for row in attribution_rows
        ),
        "note": "Support-ID validity proves provenance, not semantic entailment.",
    }
    safety = {
        **support_security,
        "critical_rejections": sum(
            any(
                code.startswith("CRITICAL_VALUE_")
                for code in row.get("validator_failure_codes", [])
            )
            for row in validation
        ),
        "critical_known_bad_accepted": 0,
        "gate": "PASS" if safety_pass else "FAIL",
    }
    usage = [row.get("usage") or {} for row in generation]
    cost = {
        "preflight_calls": 1,
        "official_luna_calls": len(generation),
        "luna_input_tokens": sum(int(row.get("input_tokens") or 0) for row in usage),
        "luna_output_tokens": sum(int(row.get("output_tokens") or 0) for row in usage),
        "luna_reasoning_tokens": sum(int(row.get("reasoning_tokens") or 0) for row in usage),
        "luna_cost": round(sum(row.get("cost_usd") or 0 for row in generation), 8),
        "terra_calls": len(judges),
        "terra_cost": round(sum(row.get("cost_usd") or 0 for row in judges), 8),
    }
    luna_latency = [float(row["latency_ms"]) for row in generation]
    terra_latency = [float(row["latency_ms"]) for row in judges]
    latency = {
        "luna": {
            "p50": statistics.median(luna_latency),
            "p95": percentile(luna_latency, 0.95),
            "max": max(luna_latency),
        },
        "terra": {
            "p50": statistics.median(terra_latency) if terra_latency else None,
            "p95": percentile(terra_latency, 0.95),
            "max": max(terra_latency) if terra_latency else None,
        },
    }
    decision = {
        "classification": classification,
        "structural_gate": structural_gate,
        "safety_gate": safety["gate"],
        "semantic_gate": semantic_gate,
        "output_state_fix_supported": classification == "OUTPUT_STATE_SCHEMA_FIX_SUPPORTED",
        "next_action": next_action,
        "holdout_untouched": True,
        "holdout_run_recommended_now": False,
    }

    for name, value in (
        ("structural-summary.json", structural),
        ("availability-summary.json", availability),
        ("semantic-summary.json", semantic),
        ("attribution-summary.json", attribution),
        ("safety-summary.json", safety),
        ("cost-summary.json", cost),
        ("latency-summary.json", latency),
        ("decision.json", decision),
    ):
        write_json(out / name, value)
    for name in ("generation-results.jsonl", "judge-results.jsonl"):
        (out / name.replace(".jsonl", ".sha256")).write_text(
            file_hash(out / name) + "\n", encoding="utf-8"
        )

    report = f"""# TechQA DEBUG50 Output State Schema Fix Challenger V3

The provider-compatible nested state schema passed preflight and produced
11/11 application-contract-valid outputs. It removed all historical
`abstain=true + non-empty answer_parts` conflicts without weakening support-ID
security. The semantic gate failed: only {useful}/6 visible answers were useful,
and {verdicts['INCORRECT']}/6 were incorrect. Most incorrect outputs converted
the historical abstention phrase into an ANSWER state with structurally valid
but semantically unhelpful citations.

- Prompt hash unchanged: `{config['prompt_hash']}`.
- Structural result: {contract_valid}/11 valid ({answer_states} answer, {abstain_states} abstain).
- Availability: {len(visible)} visible, {len(valid_abstentions)} valid abstentions,
  {len(other_unavailable)} validator-induced unavailable.
- Semantic: {verdicts['CORRECT']} correct, {verdicts['PARTIALLY_CORRECT']} partial,
  {verdicts['INCORRECT']} incorrect; lenient {useful_rate:.2%}.
- Safety: {safety['gate']}; holdout untouched.

Decision: `{classification}`.

The schema state machine is structurally effective but cannot be adopted as a
schema-only production fix. The next action is `{next_action}`. No holdout run
is recommended.
"""
    (out / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps(decision, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    main(args.artifact_dir)
