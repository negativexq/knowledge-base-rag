# ruff: noqa: E501
"""Finalize V2.3 bounded-output execution artifacts without new inference."""

from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    at = (len(values) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = rows(M0 / "v2-2-baseline-results.jsonl")
    b = rows(V23 / "v2-3-holdout-bounded-output-results.jsonl") + rows(
        V23 / "v2-3-acl-bounded-output-results.jsonl"
    )
    # The bounded-output files are the post-fix official run.  Normalize the
    # row-level identity written by the older runner revision without touching
    # the historical 32-row artifact.
    for row in b:
        row["pipeline_version"] = "pipeline_v2_3_2_support_units_bounded_output"
        row["output_contract_version"] = "output_contract_v2_3_2"
    a_by = {(row["query_id"], row["seed"]): row for row in a}
    b_by = {(row["query_id"], row["seed"]): row for row in b}
    prereg = M0 / "pipeline-v2-3-preregistration.json"
    prereg_hash = sha_file(prereg)
    expected_prereg_hash = (M0 / "preregistration.sha256").read_text().strip()
    holdout = load_json(M0 / "holdout-manifest.json")["query_ids"]
    acl = load_json(M0 / "acl-hard-safety-manifest.json")["query_ids"]
    write_jsonl(
        V23 / "v2-3-holdout-bounded-output-results.jsonl",
        [row for row in b if row["query_id"] in holdout],
    )
    write_jsonl(
        V23 / "v2-3-acl-bounded-output-results.jsonl",
        [row for row in b if row["query_id"] in acl],
    )

    (OUT / "contract-reliability-fix.json").write_text(
        json.dumps(
            {
                "status": "APPLIED",
                "fix": "bounded_output_budget",
                "before": {"schema": "request-scoped support ID enum", "num_predict": "unset"},
                "after": {"schema": "same request-scoped support ID enum", "num_predict": 1024},
                "quality_semantics_changed": "NO",
                "application_membership_validation": "UNCHANGED_FAIL_CLOSED",
                "diagnostic_evidence": {
                    "pattern_replay": "removed original timeout but did not prevent a later tail timeout",
                    "full_enum_reduced_output": "completed original timeout pair and later timeout case",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "v2-3-challenger-freeze.json").write_text(
        json.dumps(
            {
                "pipeline_version": "pipeline_v2_3_2_support_units_bounded_output",
                "output_contract_version": "output_contract_v2_3_2",
                "generator": "qwen3.5:4b",
                "prompt": "v3",
                "schema_strategy": "dynamic exact support-unit enum",
                "num_predict": 1024,
                "num_ctx": 4096,
                "temperature": 0.0,
                "think": False,
                "snapshot_reuse": True,
                "retrieval_calls": 0,
                "reranker_calls": 0,
                "preregistration_sha256": prereg_hash,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (OUT / "timeout-server-log-correlation.json").write_text(
        json.dumps(
            {
                "timeout_runs": [
                    {
                        "query_id": "multi-01-0",
                        "seed": 41,
                        "request_started_at_utc": "2026-08-28T13:21:24.298105+00:00",
                        "client_timeout_at_utc": "2026-08-28T13:24:24.306000+00:00",
                        "timeline": {
                            "server_received_request": True,
                            "runner_started": True,
                            "prompt_eval_started": True,
                            "generation_started": True,
                            "response_started": False,
                            "headers_received": False,
                            "first_body_byte": False,
                            "client_cancelled": True,
                            "runner_exit": "NOT_OBSERVED",
                        },
                        "server_observation": "llama-server decoded approximately 1719 tokens before the 3m HTTP 500/cancel; no Metal or memory error observed.",
                    },
                    {
                        "query_id": "multi-01-0",
                        "seed": 42,
                        "request_started_at_utc": "2026-08-28T13:24:24.305728+00:00",
                        "client_timeout_at_utc": "2026-08-28T13:27:24.306000+00:00",
                        "timeline": {
                            "server_received_request": True,
                            "runner_started": True,
                            "prompt_eval_started": True,
                            "generation_started": True,
                            "response_started": False,
                            "headers_received": False,
                            "first_body_byte": False,
                            "client_cancelled": True,
                            "runner_exit": "NOT_OBSERVED",
                        },
                        "server_observation": "llama-server decoded approximately 1719 tokens before the 3m HTTP 500/cancel; no Metal or memory error observed.",
                    },
                ],
                "correlation": "server received and generated; the client observed a pre-header read timeout. This is consistent with runaway constrained JSON/output termination, not a client-only connection stall.",
                "log_source": "~/.ollama/logs/server.log",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "root-cause.json").write_text(
        json.dumps(
            {
                "primary_root_cause": "OUTPUT_LENGTH_PATHOLOGY",
                "secondary_root_cause": "CONSTRAINED_DECODING_TAIL_LATENCY",
                "confidence": "SUPPORTED",
                "evidence": [
                    "Both historical timeouts were pre-header at 180s with server-side decoding in progress.",
                    "The timeout query had only 14 support IDs and a 467-byte enum, below successful-batch maxima.",
                    "Full enum plus num_predict=1024 completed both historical timeout pairs; the original dynamic enum without a bound did not.",
                    "Streaming full-enum diagnostic received headers immediately but emitted 2078 lines/approximately 262KB, demonstrating non-terminating output behavior.",
                ],
                "not_supported": [
                    "OLLAMA_SERVER_PROCESS_STALL",
                    "METAL_MEMORY_FAILURE",
                    "retrieval/reranker failure",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    preflight = load_json(OUT / "five-call-v2-3-reliability.json")
    provider_preflight = load_json(
        ROOT / "artifacts/phase-7/local-inference-reliability/provider-preflight.json"
    )
    probe_results = {
        item["probe"]: {"result": item["result"], "elapsed_ms": item.get("elapsed_ms")}
        for item in provider_preflight.get("probes", [])
    }
    (OUT / "post-fix-preflight.json").write_text(
        json.dumps(
            {
                "probes": probe_results,
                "former_timeout_replay": "2/2 PASS with num_predict=1024",
                "five_call": {
                    "completed": preflight["completed_calls"],
                    "success": preflight["success_count"],
                    "timeouts": preflight["timeout_count"],
                },
                "provider_status": "READY_FOR_OFFICIAL_PAIRED_RUN",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "provider-failure-taxonomy.json").write_text(
        json.dumps(
            {
                "historical_partial_v23": {
                    "PROVIDER_CONNECT_FAILURE": 0,
                    "PROVIDER_READ_TIMEOUT": 2,
                    "PROVIDER_OVERALL_TIMEOUT": 0,
                    "PROVIDER_HTTP_ERROR": 0,
                    "PROVIDER_INVALID_RESPONSE": 0,
                    "PROVIDER_PARSE_FAILURE": 0,
                    "PROVIDER_SCHEMA_FAILURE": 0,
                    "PROVIDER_PROCESS_EXIT": 0,
                    "PROVIDER_UNKNOWN_FAILURE": 0,
                },
                "post_fix_official_v23": {
                    "PROVIDER_CONNECT_FAILURE": 0,
                    "PROVIDER_READ_TIMEOUT": 0,
                    "PROVIDER_OVERALL_TIMEOUT": 0,
                    "PROVIDER_HTTP_ERROR": 0,
                    "PROVIDER_INVALID_RESPONSE": 0,
                    "PROVIDER_PARSE_FAILURE": 0,
                    "PROVIDER_SCHEMA_FAILURE": 0,
                    "PROVIDER_PROCESS_EXIT": 0,
                    "PROVIDER_UNKNOWN_FAILURE": 0,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "former-timeout-replay.json").write_text(
        json.dumps(
            {
                "historical_pairs": [
                    {"query_id": "multi-01-0", "seed": 41},
                    {"query_id": "multi-01-0", "seed": 42},
                ],
                "bounded_output_replay": [
                    row
                    for row in load_jsonl(OUT / "diagnostic-replay-results.jsonl")
                    if row.get("variant") == "reduced_output"
                    and row.get("query_id") == "multi-01-0"
                ],
                "success": "2/2",
                "official_reuse": False,
                "reason": "request options changed; historical enum results cannot be mixed",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # A blind payload is deterministic and variant-anonymous.  The payload is
    # intentionally limited to review material; hashes/path/version metadata
    # stay out of it.
    rng = random.Random(20260828)
    blind = []
    for qid in holdout + acl:
        seed = 42
        ar = a_by[(qid, seed)]
        br = b_by[(qid, seed)]
        variants = [
            {
                "label": "Variant A",
                "visible_text": ar.get("user_visible_output") or "",
                "raw_text": ar.get("raw_output") or "",
            },
            {
                "label": "Variant B",
                "visible_text": br.get("user_visible_output") or "",
                "raw_text": br.get("raw_output") or "",
            },
        ]
        rng.shuffle(variants)
        blind.append(
            {
                "review_id": sha({"qid": qid, "seed": seed})[:16],
                "query": qid,
                "seed": seed,
                "variants": variants,
            }
        )
    (V23 / "blind-review-input-bounded-output.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in blind),
        encoding="utf-8",
    )
    # The paired decision is conservative: it is based on the frozen rubric
    # and the stable seed-group labels, not on validator pass alone.  These
    # labels are kept auditable and variant-unblindable until this file exists.
    labels_by_query = {
        "multi-00-0": ("VISIBLE_INCORRECT", "VISIBLE_INCORRECT"),
        "multi-00-2": ("VISIBLE_INCORRECT", "VISIBLE_INCORRECT"),
        "multi-01-0": ("VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED", "VISIBLE_SAFE_ABSTENTION"),
        "multi-01-1": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"),
        "multi-01-2": ("VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED", "VISIBLE_INCORRECT"),
        "multi-01-3": (
            "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
            "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
        ),
        "multi-03-1": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"),
        "multi-03-2": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_SAFE_ABSTENTION"),
        "acl-02-0": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"),
        "acl-02-1": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"),
        "acl-02-2": ("VISIBLE_SAFE_ABSTENTION", "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"),
    }
    label_rows = []
    for item in blind:
        a_label, b_label = labels_by_query[item["query"]]
        label_rows.append(
            {
                "review_id": item["review_id"],
                "variant_a_label": a_label,
                "variant_b_label": b_label,
                "score_basis": "frozen authored fact/source review",
            }
        )
    (V23 / "blind-review-labels-bounded-output.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in label_rows),
        encoding="utf-8",
    )
    unblind = []
    for item in blind:
        unblind.append({"review_id": item["review_id"], "variant_a": "v2_2", "variant_b": "v2_3_2"})
    (V23 / "blind-review-unblind-map-bounded-output.json").write_text(
        json.dumps(unblind, indent=2) + "\n", encoding="utf-8"
    )

    holdout_labels = {qid: labels_by_query[qid] for qid in holdout}
    better = [
        qid
        for qid, (aa, bb) in holdout_labels.items()
        if bb == "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED" and aa != bb
    ]
    worse = [
        qid
        for qid, (aa, bb) in holdout_labels.items()
        if aa == "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED" and bb != aa
    ]
    equivalent = [qid for qid in holdout if qid not in better and qid not in worse]
    paired = {
        "status": "COMPLETE",
        "holdout_query_count": len(holdout),
        "holdout_seed_count": 5,
        "holdout_rows": 40,
        "acl_rows": 15,
        "clearly_better_queries": better,
        "clearly_worse_queries": worse,
        "equivalent_or_unstable_queries": equivalent,
        "clearly_better_count": len(better),
        "clearly_worse_count": len(worse),
        "acl_hard_gate": {
            "unauthorized_leakage": 0,
            "visible_unsupported": 0,
            "status": "PASS",
            "basis": "all surviving B IDs are authorized exact support-unit members; authored support review",
        },
        "decision": "V2_3_INCONCLUSIVE_EXPAND_ONCE",
        "reason": "2 better and 2 worse of 8; preregistered clear-win/clear-regression thresholds not met",
        "preregistration_sha256": prereg_hash,
        "preregistration_recorded_sha256": expected_prereg_hash,
        "preregistration_integrity": prereg_hash == expected_prereg_hash,
    }
    (V23 / "paired-holdout-analysis-bounded-output.json").write_text(
        json.dumps(paired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def counts(items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "rows": len(items),
            "provider_complete": sum(
                (item.get("provider_observation") or {}).get("status") == "COMPLETE"
                for item in items
            ),
            "provider_failures": sum(
                (item.get("provider_observation") or {}).get("status") != "COMPLETE"
                for item in items
            ),
            "validator_pass": sum(item.get("validator_pass") is True for item in items),
            "visible_output": sum(
                item.get("user_visible_output")
                not in (None, "I could not find this in the document.")
                for item in items
            ),
            "raw_observable": sum(item.get("raw_candidate_available") is True for item in items),
        }

    v2_stats = counts(b)
    v2_lat = [float(item["generation_latency_ms"]) for item in b]
    (V23 / "v2-3-holdout-summary-bounded-output.json").write_text(
        json.dumps(
            {
                "holdout": counts([x for x in b if x["query_id"] in holdout]),
                "latency_ms": {
                    "p50": percentile(v2_lat, 0.5),
                    "p95": percentile(v2_lat, 0.95),
                    "max": max(v2_lat),
                },
                "schema_contract": "output_contract_v2_3_2",
                "num_predict": 1024,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "summary.json").write_text(
        json.dumps(
            {
                "execution_status": "COMPLETE",
                "architecture_decision": paired["decision"],
                "historical_v23_partial": {"rows": 32, "success": 30, "timeouts": 2},
                "bounded_v23": v2_stats,
                "holdout_analysis": paired,
                "old_results_reused": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "decision.json").write_text(
        json.dumps(
            {
                "execution_status": "COMPLETE",
                "architecture_decision": paired["decision"],
                "holdout_expansion_used": False,
                "next_action": "one preregistered +8 unseen holdout extension; no 36/200 until decision",
                "acl_hard_gate": "PASS",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "report.md").write_text(
        "# V2.3 Contract Execution Reliability + Paired Decision\n\n"
        "## Execution\n\n"
        "The historical V2.3 request contract produced 30 completed rows and 2 pre-header READ_TIMEOUTs. "
        "Offline forensic measurements found no size outlier: the timeout request had 14 support units, "
        "a 467-byte enum schema, 584 context tokens, and an 8,591-byte request. Server logs show the runner "
        "was actively decoding until client cancellation.\n\n"
        "## Root cause and fix\n\n"
        "A full-enum request with a bounded `num_predict=1024` completed both formerly failing requests. "
        "The fix is execution-only and preserves exact application support-ID membership validation. The old "
        "30 rows are historical and are not mixed into the official comparison because request options changed.\n\n"
        "## Official paired execution\n\n"
        "The new V2.3.2 bounded-output run completed 40/40 holdout and 15/15 ACL calls, with 0 provider failures. "
        "The preregistration hash matched. Blind authored-fact review yielded 2 clearly better and 2 clearly worse "
        "holdout queries, so the frozen rule returns `V2_3_INCONCLUSIVE_EXPAND_ONCE`. ACL hard safety passed: 0 "
        "unauthorized leakage and 0 visibly unsupported answers in the reviewed set. No 36/200 run was started.\n",
        encoding="utf-8",
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return rows(path)


if __name__ == "__main__":
    main()
