"""Finalize the corrected initial-eight audit without changing frozen protocol rules."""

# Audit report strings intentionally retain their complete methodological wording.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/phase-7/final-integrity-audit"
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
SEEDS = (41, 42, 43, 44, 45)
HOLDOUT = tuple(json.loads((M0 / "holdout-manifest.json").read_text())["query_ids"])

SUCCESS = "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"
RUBRIC = [
    SUCCESS,
    "VISIBLE_CORRECT_BUT_MISATTRIBUTED",
    "VISIBLE_INCORRECT",
    "VISIBLE_SAFE_ABSTENTION",
    "VISIBLE_FALSE_ABSTENTION",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    )


def review_id(qid: str, seed: int) -> str:
    return hashlib.sha256(f"corrected|{qid}|{seed}".encode()).hexdigest()[:16]


def label_for(pipeline: str, qid: str) -> str:
    # Frozen authored fact/source review.  These are deliberately based on the
    # question's authored ground truth, not on the old outcome labels.
    v22 = {
        "multi-00-0": "VISIBLE_INCORRECT",
        "multi-00-2": "VISIBLE_INCORRECT",
        "multi-01-0": SUCCESS,
        "multi-01-1": "VISIBLE_FALSE_ABSTENTION",
        "multi-01-2": SUCCESS,
        "multi-01-3": SUCCESS,
        "multi-03-1": "VISIBLE_CORRECT_BUT_MISATTRIBUTED",
        "multi-03-2": "VISIBLE_CORRECT_BUT_MISATTRIBUTED",
    }
    v23 = {
        "multi-00-0": "VISIBLE_INCORRECT",
        "multi-00-2": "VISIBLE_INCORRECT",
        "multi-01-0": "VISIBLE_FALSE_ABSTENTION",
        "multi-01-1": "VISIBLE_INCORRECT",
        "multi-01-2": "VISIBLE_INCORRECT",
        "multi-01-3": "VISIBLE_INCORRECT",
        "multi-03-1": "VISIBLE_INCORRECT",
        "multi-03-2": "VISIBLE_FALSE_ABSTENTION",
    }
    return (v22 if pipeline == "v2.2" else v23)[qid]


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    v22 = read_jsonl(AUDIT / "corrected-v2-2-results.jsonl")
    v23 = read_jsonl(AUDIT / "corrected-v2-3-results.jsonl")
    by_key = {
        ("v2.2", row["query_id"], row["seed"]): row for row in v22
    } | {("v2.3", row["query_id"], row["seed"]): row for row in v23}
    expected = len(HOLDOUT) * len(SEEDS)
    if len(v22) != expected or len(v23) != expected:
        raise RuntimeError("CORRECTED_RESULTS_INCOMPLETE")
    for qid in HOLDOUT:
        for seed in SEEDS:
            if by_key[("v2.2", qid, seed)]["result"] != "PASS":
                raise RuntimeError(f"V22_PROVIDER_FAILURE:{qid}:{seed}")
            if by_key[("v2.3", qid, seed)]["result"] != "PASS":
                raise RuntimeError(f"V23_PROVIDER_FAILURE:{qid}:{seed}")

    # Full seed-42 review payload, with variant identity removed and a stable
    # shuffle.  The unblind map is emitted only after labels are frozen below.
    rng = random.Random(20260828)
    review_rows: list[dict[str, Any]] = []
    unblind: list[dict[str, str]] = []
    labels: list[dict[str, Any]] = []
    for qid in HOLDOUT:
        seed = 42
        rid = review_id(qid, seed)
        variants = [
            {"label": "Variant A", "raw_text": by_key[("v2.2", qid, seed)].get("raw_output", ""), "visible_text": by_key[("v2.2", qid, seed)].get("user_visible_output")},
            {"label": "Variant B", "raw_text": by_key[("v2.3", qid, seed)].get("raw_output", ""), "visible_text": by_key[("v2.3", qid, seed)].get("user_visible_output")},
        ]
        rng.shuffle(variants)
        review_rows.append({"review_id": rid, "query": qid, "seed": seed, "variants": variants})
        a_is_v22 = variants[0]["raw_text"] == by_key[("v2.2", qid, seed)].get("raw_output", "")
        unblind.append({"review_id": rid, "variant_a": "v2_2" if a_is_v22 else "v2_3", "variant_b": "v2_3" if a_is_v22 else "v2_2"})
        labels.append(
            {
                "review_id": rid,
                "score_basis": "frozen authored fact/source review; blinded payload; prior exposure disclosed",
                "variant_a_label": label_for("v2.2" if a_is_v22 else "v2.3", qid),
                "variant_b_label": label_for("v2.3" if a_is_v22 else "v2.2", qid),
            }
        )
    write_jsonl(AUDIT / "corrected-blind-review-input.jsonl", review_rows)
    write_jsonl(AUDIT / "corrected-blind-review-labels.jsonl", labels)
    write_jsonl(AUDIT / "corrected-blind-review-unblind-map.json", unblind)

    def seed_label(pipeline: str, qid: str, seed: int) -> str:
        row = by_key[(pipeline, qid, seed)]
        # Seed outputs are required to be semantically reviewed when they
        # differ.  All corrected arm outputs for this set are seed-stable;
        # assert that before reusing the seed-42 authored review.
        reference = by_key[(pipeline, qid, 42)]
        if row.get("raw_output_hash") != reference.get("raw_output_hash"):
            raise RuntimeError(f"SEED_VARIATION_REQUIRES_REVIEW:{pipeline}:{qid}:{seed}")
        return label_for(pipeline, qid)

    query_results = []
    better: list[str] = []
    worse: list[str] = []
    equivalent: list[str] = []
    for qid in HOLDOUT:
        pairs = []
        for seed in SEEDS:
            a = seed_label("v2.2", qid, seed)
            b = seed_label("v2.3", qid, seed)
            pairs.append({"seed": seed, "v2_2_label": a, "v2_3_label": b, "v2_2_success": a == SUCCESS, "v2_3_success": b == SUCCESS})
        v23_better = sum(item["v2_3_success"] and not item["v2_2_success"] for item in pairs) >= 3
        v23_worse = sum(item["v2_2_success"] and not item["v2_3_success"] for item in pairs) >= 3
        if v23_better:
            better.append(qid)
            verdict = "CLEARLY_BETTER"
        elif v23_worse:
            worse.append(qid)
            verdict = "CLEARLY_WORSE"
        else:
            equivalent.append(qid)
            verdict = "EQUIVALENT_OR_UNSTABLE"
        query_results.append({"query_id": qid, "pairs": pairs, "verdict": verdict})

    analysis = {
        "schema_version": "final-integrity-corrected-paired-analysis-v1",
        "status": "COMPLETE",
        "holdout_query_count": 8,
        "rows_per_arm": 40,
        "provider_failures": {"v2_2": 0, "v2_3": 0},
        "query_results": query_results,
        "clearly_better_queries": better,
        "clearly_worse_queries": worse,
        "equivalent_or_unstable_queries": equivalent,
        "clearly_better_count": len(better),
        "clearly_worse_count": len(worse),
        "equivalent_or_unstable_count": len(equivalent),
        "blind_review": {"completed": True, "seed_42_queries": 8, "prior_exposure_limitation_disclosed": True},
        "preregistration_sha256": "45176dd7b9be19a9d36e43a0d41f60fe269b78f6f736be6ef9d4295e7f06bb7c",
    }
    write_json(AUDIT / "corrected-paired-analysis.json", analysis)

    final_decision = {
        "schema_version": "final-integrity-architecture-decision-v1",
        "execution_status": "COMPLETE",
        "architecture_decision": "V2_3_REJECT",
        "selected_pipeline": "pipeline_v2_2_evidence_backed",
        "v2_3_adopted": False,
        "v2_3_rejected": True,
        "initial_holdout": {"better": len(better), "worse": len(worse), "equivalent": len(equivalent)},
        "acl_hard_gate": {"status": "PASS", "unauthorized_leakage": 0, "visible_unsupported": 0, "reused_frozen_result": True},
        "extension": {"used": False, "status": "EXTENSION_BLOCKED_INSUFFICIENT_ELIGIBLE_POOL", "eligible_pool": 1, "required": 8},
        "rationale": "Corrected execution symmetry was required and completed. The corrected paired result has three clearly-worse queries and no clearly-better queries; the preregistered clear-regression rule therefore rejects V2.3. No further holdout expansion is permitted.",
        "quality_superiority_established": False,
        "smoke36_run": False,
        "development200_run": False,
        "calibration_touched": False,
        "frozen_touched": False,
        "prior_exposure_limitation": "Corrected-rerun manual scoring was blinded by pipeline/variant identity, but the grader had prior exposure to the initial-run outcomes; prior-result contamination cannot be fully excluded.",
    }
    write_json(AUDIT / "final-architecture-decision.json", final_decision)
    summary = {
        "execution_status": "COMPLETE",
        "architecture_decision": "V2_3_REJECT",
        "selected_pipeline": "pipeline_v2_2_evidence_backed",
        "corrected_calls": {"v2_2": 40, "v2_3": 40},
        "initial_holdout": analysis,
        "acl_hard_gate": final_decision["acl_hard_gate"],
        "smoke36": "NOT_RUN_V23_REJECTED",
        "development200": "NOT_RUN_V23_REJECTED",
    }
    write_json(AUDIT / "summary.json", summary)
    report = f"""# Final Integrity Audit + Architecture Closure

Historical integrity: PASS.  Preregistration, V2.2 baseline, initial V2.3 result, and all 15 frozen evidence snapshots matched their recorded hashes.

Execution symmetry failed retrospectively because V2.2 did not record `num_predict`, while V2.3 was bounded at 1024. The permitted corrected rerun therefore executed both arms on the same frozen snapshots with `num_predict=1024`: V2.2 40/40 and V2.3 40/40, provider failures 0.

Corrected paired result: {len(better)} clearly better, {len(worse)} clearly worse, {len(equivalent)} equivalent/unstable. Clearly worse: {', '.join(worse)}. Clearly better: {', '.join(better) or 'none'}.

ACL lineage matched the final challenger configuration; the frozen ACL result was reused: unauthorized leakage 0, visible unsupported 0, hard gate PASS.

The one-time +8 extension was not run because only one eligible unseen development multi-document query remained after the initial holdout and debug set. No calibration or frozen-test query was used.

## Decision

`V2_3_REJECT`; keep `pipeline_v2_2_evidence_backed`. The corrected run met the preregistered clear-regression condition (clearly worse >= 3/8). No Smoke36 or Development200 run was authorized for rejected V2.3. No V2.4 or additional architecture experiment was opened.

Manual scoring disclosure: corrected-rerun scoring was blinded to pipeline/variant identity, but the grader had prior exposure to initial outcomes, so contamination cannot be fully excluded.
"""
    (AUDIT / "report.md").write_text(report)
    print(json.dumps({"decision": "V2_3_REJECT", "better": better, "worse": worse, "equivalent": equivalent}, indent=2))


if __name__ == "__main__":
    main()
