# ruff: noqa: E501
"""Write the offline Pipeline v2 closure artifacts from completed runs.

This module never creates a provider, retrieval, embedding, or reranker call.
It only rehydrates stored candidates and deterministic evidence metadata.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import score_required_facts
from app.llm.structured_output import AnswerPart, render_answer_parts
from scripts.run_pipeline_v2_closure import (
    EXPECTED,
    MULTIDOC,
    OUT,
    SELECTED,
    build_fact_annotations,
    build_offline_context,
    cache_records,
    fact_score,
    identity,
    query_manifest,
    read_jsonl,
    rescore_validator_record,
    write_json,
    write_jsonl,
)


def _content(row: dict[str, Any]) -> str:
    candidate = row.get("structured_candidate")
    if not candidate:
        return row.get("raw_candidate") or ""
    return render_answer_parts(
        [AnswerPart(part["text"], part.get("citations", [])) for part in candidate.get("answer_parts", [])],
        abstain=bool(candidate.get("abstain")),
    )


def _status_counts(rows: list[dict[str, Any]], eligible: set[str]) -> dict[str, int]:
    statuses = [row["fact_score"]["status"] for row in rows if row["query_id"] in eligible]
    return {status: statuses.count(status) for status in sorted(set(statuses))}


def _visible_status(row: dict[str, Any], questions: dict[str, dict[str, Any]]) -> str:
    if not row.get("user_visible_output_available"):
        return "NOT_USER_VISIBLE"
    return score_required_facts(
        questions[row["query_id"]].get("expected_answer"),
        row.get("validated_output") or "",
    )["status"]


def _facts_in_context(rows: list[dict[str, Any]], facts: dict[str, Any], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_query: dict[str, list[dict[str, Any]]] = {}
    for fact in facts["facts"]:
        by_query.setdefault(fact["required_fact_id"], []).append(fact)
    fact_rows = []
    for query in facts["queries"]:
        qid = query["query_id"]
        required = [fact for fact in facts["facts"] if fact["required_fact_id"] in {
            fid for component in query["required_components"] for fid in component["required_fact_ids"]
        }]
        anchors = chunks_from_cache(cache[qid])
        anchor_text = "\n".join(str(chunk.payload.get("text", "")) for chunk in anchors)
        blocks, _ = build_offline_context(cache[qid])
        block_text = "\n".join(str(block.payload.get("text", "")) for block in blocks)
        for fact in required:
            span = fact["supporting_text_span"]
            fact_rows.append({
                "query_id": qid,
                "required_fact_id": fact["required_fact_id"],
                "v1_anchor_contains_span": span in anchor_text,
                "v2_context_contains_span": span in block_text,
            })
    return {
        "annotated_fact_occurrences": len(fact_rows),
        "v1_fact_evidence_present": sum(item["v1_anchor_contains_span"] for item in fact_rows),
        "v2_fact_evidence_present": sum(item["v2_context_contains_span"] for item in fact_rows),
        "rows": fact_rows,
    }


def _write_contracts() -> None:
    write_json(OUT / "structured-output-contract.json", {
        "version": "output_contract_v2",
        "schema": {
            "answer_parts": [{"text": "string", "citations": ["canonical citation"]}],
            "abstain": "boolean",
        },
        "no_chain_of_thought": True,
        "renderer": "deterministic; emits only validated answer parts",
    })
    write_json(OUT / "validator-contract.json", {
        "version": "claim_level_strict",
        "part_codes": [
            "MALFORMED_CITATION_SYNTAX", "UNKNOWN_CITATION_ID", "UNAUTHORIZED_CITATION_ID",
            "MISSING_REQUIRED_CITATION", "OUTPUT_SCHEMA_FAILURE",
        ],
        "top_level_fail_closed": True,
        "unauthorized_fail_closed": True,
        "valid_parts_survive_independent_part_failure": True,
        "raw_rejected_output_user_visible": False,
    })


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ident = identity()
    facts = build_fact_annotations()
    cache = cache_records()
    questions = query_manifest()
    closure_path = OUT / "closure-gate-results-budgeted-v1.jsonl"
    smoke_path = OUT / "smoke36-results.jsonl"
    closure = read_jsonl(closure_path)
    smoke = read_jsonl(smoke_path)
    # Refresh all deterministic fields from the current validator without
    # contacting any provider.  This makes the artifact self-consistent with
    # the implementation now checked into the worktree.
    for rows, ids in ((closure, list(SELECTED)), (smoke, list(cache))):
        for row in rows:
            blocks, _ = build_offline_context(cache[row["query_id"]])
            rescore_validator_record(row, blocks)
            row["fact_score"] = fact_score(questions[row["query_id"]], _content(row), bool(row.get("raw_candidate_available")))
    write_jsonl(closure_path, closure)
    write_jsonl(smoke_path, smoke)

    answerable = {
        row["query_id"] for row in smoke
        if questions[row["query_id"]].get("answerability") == "answerable"
        and cache[row["query_id"]].get("gold_present") is True
    }
    closure_answerable = {row["query_id"] for row in closure}
    fact_presence = _facts_in_context(closure, facts, cache)
    closure_full = sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in closure)
    closure_visible = sum(
        _visible_status(row, questions) == "FULLY_CORRECT_COMPLETE"
        for row in closure
    )
    closure_multi = [row for row in closure if row["query_id"] in MULTIDOC]
    closure_latencies = [row["generation_latency_ms"] for row in closure]
    closure_summary = {
        "status": "CLOSURE_GATE_COMPLETED",
        "canonical_run": "budgeted-v1",
        "query_count": len(closure),
        "annotated_fact_count": len(facts["facts"]),
        "fact_evidence_completeness": fact_presence,
        "raw_fully_correct_complete": closure_full,
        "user_visible_full_success": closure_visible,
        "status_counts": _status_counts(closure, closure_answerable),
        "user_visible_status_counts": {
            status: sum(
                _visible_status(row, questions) == status
                for row in closure
                if row["query_id"] in closure_answerable
            )
            for status in sorted({_visible_status(row, questions) for row in closure if row["query_id"] in closure_answerable})
        },
        "multi_document": {
            "n": len(closure_multi),
            "fully_correct_complete": sum(r["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for r in closure_multi),
            "fact_coverages": [r["fact_score"].get("fact_coverage") for r in closure_multi],
        },
        "mean_fact_coverage": statistics.mean([r["fact_score"]["fact_coverage"] for r in closure if r["fact_score"].get("fact_coverage") is not None]),
        "raw_observable": sum(bool(r.get("raw_candidate_available")) for r in closure),
        "validator_pass": sum(bool(r.get("validator_pass")) for r in closure),
        "validator_failure_codes": sorted({code for r in closure for code in r.get("validator_failure_codes", [])}),
        "generation_latency_ms": {"p50": statistics.median(closure_latencies), "max": max(closure_latencies)},
        "calls": {"generation": len(closure), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
    }
    write_json(OUT / "closure-gate-comparison.json", closure_summary)
    write_json(OUT / "summary.json", closure_summary)
    write_json(OUT / "closure-gate-citation-analysis.json", {
        "identity_policy": "exact or unique case-insensitive authorized-context identity",
        "validator_failure_codes": sorted({code for r in closure for code in r.get("validator_failure_codes", [])}),
        "raw_candidates_observable": sum(bool(r.get("raw_candidate_available")) for r in closure),
        "claim_semantic_support": "deterministic/manual review only; no external judge",
    })
    write_json(OUT / "closure-gate-safety-analysis.json", {
        "acl_expansion": "same tenant/source/version only",
        "phase6_semantic_gate": "OFF",
        "raw_rejected_output_user_visible": False,
        "closure_acl_cases": "not included in the 10-query annotated closure set; evaluated in smoke36",
    })
    write_json(OUT / "closure-gate-latency.json", closure_summary["generation_latency_ms"])

    smoke_cats: dict[str, Any] = {}
    for category in sorted({r["category"] for r in smoke}):
        subset = [r for r in smoke if r["category"] == category]
        eligible = [r for r in subset if r["query_id"] in answerable]
        smoke_cats[category] = {
            "n": len(subset),
            "gold_present_answerable": len(eligible),
            "content_status_counts": _status_counts(smoke, {r["query_id"] for r in eligible}),
            "user_visible_full": sum(
                _visible_status(row, questions) == "FULLY_CORRECT_COMPLETE"
                for row in eligible
            ),
            "validator_pass": sum(bool(r.get("validator_pass")) for r in subset),
            "raw_observable": sum(bool(r.get("raw_candidate_available")) for r in subset),
            "user_visible": sum(bool(r.get("user_visible_output_available")) for r in subset),
        }
    smoke_summary = {
        "status": "SMOKE36_COMPLETED",
        "canonical_query_count": len(smoke),
        "gold_present_answerable": len(answerable),
        "content_status_counts": _status_counts(smoke, answerable),
        "user_visible_status_counts": {
            status: sum(
                _visible_status(row, questions) == status
                for row in smoke
                if row["query_id"] in answerable
            )
            for status in sorted({_visible_status(row, questions) for row in smoke if row["query_id"] in answerable})
        },
        "categories": smoke_cats,
        "fully_correct_complete_gold_present": sum(r["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for r in smoke if r["query_id"] in answerable),
        "user_visible_full_gold_present": sum(
            _visible_status(row, questions) == "FULLY_CORRECT_COMPLETE"
            for row in smoke
            if row["query_id"] in answerable
        ),
        "validator_pass": sum(bool(r.get("validator_pass")) for r in smoke),
        "user_visible_outputs": sum(bool(r.get("user_visible_output_available")) for r in smoke),
        "raw_observable": sum(bool(r.get("raw_candidate_available")) for r in smoke),
        "calls": {"generation": len(smoke), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "latency_ms": {"p50": statistics.median(r["generation_latency_ms"] for r in smoke), "max": max(r["generation_latency_ms"] for r in smoke)},
    }
    write_json(OUT / "smoke36-summary.json", smoke_summary)
    write_json(OUT / "smoke36-comparison.json", smoke_summary)
    write_json(OUT / "smoke36-slice-metrics.json", smoke_cats)
    _write_contracts()

    decision = {
        "closure_gate": "PIPELINE_V2_GATE_FAIL_MIXED",
        "closure_gate_reason": [
            "annotated evidence completeness passes for the 10-query set",
            "multi-document remains incomplete for 1/3 queries",
            "ACL/no-evidence unsupported answers remain in the 36-query smoke",
            "citation identity/strict validation remains non-perfect",
        ],
        "smoke36": "SMOKE36_FAIL",
        "development200": "NOT_RUN",
        "calibration": "NOT_RUN",
        "frozen_test": "NOT_TOUCHED",
        "ready_for_calibration": False,
        "next_action": "stop tuning; classify remaining issues as citation model behavior, grounding limitation, and generator quality ceiling before any separately approved hardening task",
    }
    write_json(OUT / "decision.json", decision)
    write_json(OUT / "pipeline-version.json", {
        "pipeline_version": "pipeline_v2_section_claims",
        "output_contract_version": "output_contract_v2",
        "default_enabled": False,
        "historical_v1_preserved": True,
    })
    report = f"""# Production RAG Pipeline v2 Closure\n\n## Identity\n\n```json\n{json.dumps(ident, ensure_ascii=False, indent=2, sort_keys=True)}\n```\n\n## Implementation\n\nPipeline v2 is implemented behind `RAG_PIPELINE_V2=false`. The default v1 runtime remains available. V2 uses tenant-scoped section-aware evidence blocks, structured `answer_parts`, per-part strict validation, and a deterministic renderer. Rejected raw candidates remain evaluation-only.\n\n## Corrected run\n\nThe first closure artifact was a preflight-defect run in which the provider did not honor the JSON contract. It is preserved historically. `closure-gate-results-budgeted-v1.jsonl` is the canonical corrected run after one permitted implementation correction (provider-native JSON schema plus explicit context budgeting). It used 10 generation calls.\n\nClosure raw fully correct/complete: **{closure_full}/{len(closure)}**. User-visible full success: **{closure_visible}/{len(closure)}**. Multi-document: **{closure_summary['multi_document']['fully_correct_complete']}/3**. Annotated fact evidence present: **{fact_presence['v2_fact_evidence_present']}/{fact_presence['annotated_fact_occurrences']}**.\n\n## Full smoke\n\nThe corrected v2 path also completed the existing 36-query smoke using the cached retrieval inputs. It made 36 generation calls and zero retrieval, embedding, reranker, or semantic-gate calls. Gold-present answerable content was fully correct/complete for **{smoke_summary['fully_correct_complete_gold_present']}/{len(answerable)}**; validator pass was **{smoke_summary['validator_pass']}/36**; raw candidates were observable for **{smoke_summary['raw_observable']}/36**.\n\nThe smoke is not a closure pass: ACL cases have no unauthorized leakage but unsupported answers remain possible under irrelevant authorized context, multi-document remains incomplete in one case, and citation identity/strict validation is not perfect. Development-200, calibration, and frozen test were not run.\n\n## Decision\n\n**PIPELINE_V2_GATE_FAIL_MIXED** / **SMOKE36_FAIL**. Do not promote v2 or lock configuration yet. Stop opening retrieval/model micro-experiments; the remaining blockers are bounded to citation behavior/contract observability, grounded abstention under irrelevant authorized context, and the residual generator quality ceiling.\n"""
    report = report.replace(
        f"Gold-present answerable content was fully correct/complete for **{smoke_summary['fully_correct_complete_gold_present']}/{len(answerable)}**; validator pass",
        f"Gold-present answerable raw content was fully correct/complete for **{smoke_summary['fully_correct_complete_gold_present']}/{len(answerable)}**; strict user-visible result was **{smoke_summary['user_visible_full_gold_present']}/{len(answerable)}**; validator pass",
    )
    (OUT / "report.md").write_text(report, encoding="utf-8")
    write_json(OUT / "implementation-config.json", {**EXPECTED, "pipeline_version": "pipeline_v2_section_claims", "output_contract_version": "output_contract_v2", "rag_pipeline_v2": False, "context_builder": "section_aware", "validator": "claim_level_strict", "default_enabled": False})
    print(json.dumps({"closure": closure_summary, "smoke36": smoke_summary, "decision": decision}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
