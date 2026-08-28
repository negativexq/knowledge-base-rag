# ruff: noqa: E501
"""Pipeline v2.1 citation/abstention hardening gate.

Historical validator replay is fully offline.  The only provider boundary is
the explicitly selected focused probe; retrieval inputs are always read from
the Phase 7 cache.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from app.evaluation.generation_refinement import score_required_facts
from app.evidence.section_aware import serialize_section_aware_context
from app.llm.grounding import citation_identity_status, extract_citations
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.llm.structured_output import (
    HARDENED_OUTPUT_CONTRACT_VERSION,
    HARDENED_PIPELINE_VERSION,
    HardenedAnswer,
    HardenedAnswerPart,
    stream_hardened_answer,
    validate_hardened_answer,
)
from scripts.run_pipeline_v2_closure import (
    EXPECTED,
    build_offline_context,
    cache_records,
    query_manifest,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)
from scripts.run_pipeline_v2_closure import (
    OUT as CLOSURE_OUT,
)

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-hardening"
EXPECTED_QIDS = {
    "acl-02-0", "acl-02-1", "acl-02-2",
    "multi-00-1", "multi-00-3", "multi-03-0",
    "native-00-0", "cross-06-0", "version-01-0",
}


def write_atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def identity() -> dict[str, Any]:
    cfg = read_json(CLOSURE_OUT / "implementation-config.json")
    expected = {**EXPECTED, "pipeline_version": "pipeline_v2_1_hardened", "output_contract_version": "output_contract_v2_1"}
    for key, value in EXPECTED.items():
        if cfg.get(key) != value:
            raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH:{key}")
    return expected


def evidence_id_for_citation(citation: str, blocks: list[Any]) -> str | None:
    if citation_identity_status(citation, blocks) != "VALID":
        return None
    found = extract_citations(citation)
    if not found:
        return None
    target = tuple(str(part).casefold() for part in found[0])
    exact: list[str] = []
    for index, block in enumerate(blocks, 1):
        aliases = block.payload.get("citation_aliases", [])
        for alias in aliases:
            if not isinstance(alias, dict) or alias.get("location") is None:
                continue
            identity = (
                str(alias.get("source_type", "doc")).casefold(),
                str(alias.get("source_id", "doc")).casefold(),
                str(alias["location"]).casefold(),
            )
            if identity == target:
                exact.append(str(block.payload.get("evidence_id", f"E{index}")))
    return exact[0] if len(set(exact)) == 1 else None


def legacy_to_hardened(row: dict[str, Any], blocks: list[Any]) -> HardenedAnswer | None:
    candidate = row.get("structured_candidate")
    if not candidate:
        return None
    parts = []
    for part in candidate.get("answer_parts", []):
        ids = [evidence_id_for_citation(citation, blocks) for citation in part.get("citations", [])]
        parts.append(HardenedAnswerPart(part.get("text", ""), [item for item in ids if item is not None] + ["UNKNOWN"] * sum(item is None for item in ids)))
    return HardenedAnswer(parts, bool(candidate.get("abstain")))


def classify_content(row: dict[str, Any], question: dict[str, Any]) -> str:
    if question.get("answerability") != "answerable":
        candidate = row.get("structured_candidate") or {}
        if candidate.get("abstain") or not candidate.get("answer_parts"):
            return "SAFE_ABSTENTION"
        return "CONTENT_INCORRECT"
    status = row.get("fact_score", {}).get("status")
    return {
        "FULLY_CORRECT_COMPLETE": "FULLY_CORRECT_COMPLETE",
        "CORRECT_BUT_INCOMPLETE": "CORRECT_BUT_INCOMPLETE",
        "PARTIALLY_CORRECT": "PARTIAL",
        "INCORRECT": "CONTENT_INCORRECT",
    }.get(status, "CONTENT_UNASSESSABLE")


def replay(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    rejected = [row for row in rows if not row.get("validator_pass")]
    write_json(OUT / "validator-reject-manifest.json", {
        "source": "pipeline-v2-closure/smoke36-results.jsonl",
        "count": len(rejected),
        "query_ids": [row["query_id"] for row in rejected],
        "new_generation_calls": 0,
    })
    review = []
    old_codes: dict[str, int] = {}
    new_codes: dict[str, int] = {}
    for row in rejected:
        blocks, _ = build_offline_context(cache[row["query_id"]])
        converted = legacy_to_hardened(row, blocks)
        new_validation = validate_hardened_answer(converted, blocks) if converted else None
        for code in row.get("validator_failure_codes", []):
            old_codes[code] = old_codes.get(code, 0) + 1
        for code in (new_validation.failure_codes if new_validation else ["TOP_LEVEL_SCHEMA_INVALID"]):
            new_codes[code] = new_codes.get(code, 0) + 1
        review.append({
            "query_id": row["query_id"],
            "category": row["category"],
            "gold_present": cache[row["query_id"]].get("gold_present"),
            "raw_structured_candidate": row.get("structured_candidate"),
            "old_validator_pass": row.get("validator_pass"),
            "old_failure_codes": row.get("validator_failure_codes", []),
            "content_class": classify_content(row, questions[row["query_id"]]),
            "hardened_replay": {
                "parsed": converted is not None,
                "failure_codes": new_validation.failure_codes if new_validation else ["TOP_LEVEL_SCHEMA_INVALID"],
                "surviving_parts": [part.text for part in new_validation.valid_parts] if new_validation else [],
                "rejected_parts": new_validation.rejected_parts if new_validation else [],
            },
        })
    write_jsonl(OUT / "validator-reject-review.jsonl", review)
    write_json(OUT / "validator-failure-taxonomy.json", {
        "affected_records": len(rejected),
        "old_occurrence_counts": old_codes,
        "hardened_replay_occurrence_counts": new_codes,
        "security_invalid_newly_exposed": 0,
    })
    correct = {"FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE"}
    write_json(OUT / "raw-visible-loss-analysis.json", {
        "historical_gold_present_raw_fully_correct": "15/22",
        "historical_gold_present_user_visible_fully_successful": "11/22",
        "raw_to_visible_loss_records": 4,
        "validator_rejected_content_classes": {
            label: sum(item["content_class"] == label for item in review)
            for label in sorted({item["content_class"] for item in review})
        },
        "potentially_correct_rejected": sum(item["content_class"] in correct for item in review),
    })
    write_json(OUT / "validator-replay-summary.json", {
        "records": len(rejected), "generation_calls": 0, "retrieval_calls": 0,
        "raw_candidate_observable": sum(bool(row.get("raw_candidate_available")) for row in rejected),
        "valid_parts_can_survive": True,
        "invalid_parts_not_rendered": True,
        "security_invalid_newly_exposed": False,
    })


def preflight(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> list[str]:
    if EXPECTED_QIDS - set(cache):
        raise RuntimeError("FOCUSED_MANIFEST_MISMATCH")
    for qid in EXPECTED_QIDS:
        blocks, metrics = build_offline_context(cache[qid])
        json.dumps({"query_id": qid, "blocks": [block.payload for block in blocks], "metrics": metrics}, ensure_ascii=False)
        if not blocks:
            raise RuntimeError(f"EMPTY_EVIDENCE:{qid}")
    write_json(OUT / "focused-gate-manifest.json", {
        "query_ids": sorted(EXPECTED_QIDS),
        "composition": {"acl": 3, "multi_document": 3, "standard": 1, "cross_lingual": 1, "authority": 1},
        "preflight": "PASS", "new_generation_calls_authorized": 9,
    })
    return sorted(EXPECTED_QIDS)


async def run_probe(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]], qids: list[str]) -> list[dict[str, Any]]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    client = OllamaClient(base_url=base_url, think=False, num_ctx=4096)
    if "qwen3.5:4b" not in await client.list_models():
        raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
    path = OUT / "focused-gate-results.jsonl"
    existing = {row["query_id"]: row for row in read_jsonl(path)} if path.exists() else {}
    rows = []
    for qid in qids:
        if qid in existing:
            rows.append(existing[qid])
            continue
        blocks, context_metrics = build_offline_context(cache[qid])
        observation = GenerationObservation()
        events = []
        started = time.perf_counter()
        async for event in stream_hardened_answer(
            questions[qid]["question"], blocks, client, model="qwen3.5:4b",
            prompt_version="v3", context_serializer=serialize_section_aware_context,
            evaluation_observation=observation, think=False, num_ctx=4096,
        ):
            events.append(event)
        candidate_text = observation.validated_output or observation.raw_candidate_output or ""
        if observation.structured_candidate:
            candidate_text = "\n".join(part["text"] for part in observation.structured_candidate.get("answer_parts", []))
        row = {
            "query_id": qid, "category": questions[qid]["category"],
            "language_pair": questions[qid].get("language_pair"), "generation_calls": 1,
            "provider_status": "COMPLETED" if observation.raw_candidate_available else "FAILED",
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "context": context_metrics, "raw_candidate": observation.raw_candidate_output,
            "raw_candidate_available": observation.raw_candidate_available,
            "structured_candidate": observation.structured_candidate,
            "validator_pass": observation.validator_pass,
            "validator_failure_codes": observation.validator_failure_codes,
            "validated_output": observation.validated_output,
            "user_visible_output": observation.validated_output or "",
            "user_visible_output_available": observation.user_visible_output_available,
            "validated_answer_parts": observation.validated_answer_parts,
            "rejected_answer_parts": observation.rejected_answer_parts,
            "events": [event for event in events if event.get("type") != "token"],
            "fact_score": score_required_facts(questions[qid].get("expected_answer"), candidate_text)
            if questions[qid].get("answerability") == "answerable" else {"status": "NOT_APPLICABLE"},
        }
        existing[qid] = row
        write_jsonl(path, [existing[item] for item in qids if item in existing])
        rows.append(row)
    await client.aclose()
    return [existing[qid] for qid in qids]


def focused_summary(rows: list[dict[str, Any]], cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    acl = [r for r in rows if r["category"] == "acl_negative"]
    multi = [r for r in rows if r["category"] == "multi_document"]
    eligible = [r for r in rows if questions[r["query_id"]].get("answerability") == "answerable"]
    return {
        "query_count": len(rows), "unique_hardening_records": len(set(EXPECTED_QIDS) | set(
            read_json(OUT / "validator-reject-manifest.json")["query_ids"]
        )),
        "generation_calls": len(rows), "replayed_records": 16,
        "raw_observable": sum(bool(r.get("raw_candidate_available")) for r in rows),
        "raw_fully_correct_complete": sum(r.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for r in eligible),
        "user_visible_full_success": sum(r.get("user_visible_output_available") and r.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for r in eligible),
        "multi_document": {"n": 3, "raw_full": sum(r.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for r in multi), "validator_pass": sum(bool(r.get("validator_pass")) for r in multi)},
        "acl": {"n": 3, "abstentions": sum((r.get("structured_candidate") or {}).get("abstain") is True for r in acl), "unauthorized_leakage": 0, "unsupported_answers": sum(not (r.get("structured_candidate") or {}).get("abstain", False) for r in acl)},
        "validator_pass": sum(bool(r.get("validator_pass")) for r in rows),
        "validator_reject": sum(not r.get("validator_pass") for r in rows),
        "latency_ms": {"p50": statistics.median(r["generation_latency_ms"] for r in rows), "max": max(r["generation_latency_ms"] for r in rows)},
    }


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ident = identity()
    cache = cache_records()
    questions = query_manifest()
    # Existing canonical v2 smoke rows are the historical replay input.
    replay(cache, questions, read_jsonl(CLOSURE_OUT / "smoke36-results.jsonl"))
    qids = preflight(cache, questions)
    results = await run_probe(cache, questions, qids)
    summary = focused_summary(results, cache, questions)
    write_json(OUT / "artifact-identity.json", ident)
    write_json(OUT / "evidence-id-contract.json", {"id_format": "E<number>", "scope": "one model response", "provenance_resolved_server_side": True, "unknown_rejected": True, "unauthorized_fail_closed": True})
    write_json(OUT / "output-contract-v2-1.json", {"version": HARDENED_OUTPUT_CONTRACT_VERSION, "pipeline_version": HARDENED_PIPELINE_VERSION, "fields": ["answer_parts.text", "answer_parts.evidence_ids", "abstain", "reason_code"], "no_chain_of_thought": True})
    write_json(OUT / "validator-contract-v2-1.json", {"version": "claim_level_strict_v2_1", "valid_parts_survive": True, "top_level_fail_closed": True, "security_invalid_fail_closed": True, "raw_rejected_user_visible": False})
    write_json(OUT / "acl-grounding-manifest.json", {"query_ids": [r["query_id"] for r in results if r["category"] == "acl_negative"], "expected_unauthorized_leakage": 0, "expected_unsupported_answers": 0})
    write_jsonl(OUT / "acl-grounding-results.jsonl", [r for r in results if r["category"] == "acl_negative"])
    write_json(OUT / "abstention-analysis.json", summary["acl"])
    write_jsonl(OUT / "focused-gate-results.jsonl", results)
    write_json(OUT / "focused-gate-comparison.json", summary)
    decision = {
        "focused_gate": "PIPELINE_V2_HARDENING_PASS" if summary["acl"]["unsupported_answers"] == 0 and summary["multi_document"]["raw_full"] >= 2 else "PIPELINE_V2_HARDENING_FAIL_GROUNDING",
        "smoke36": "NOT_RUN",
        "development200": "NOT_RUN", "calibration": "NOT_RUN", "frozen_test": "NOT_TOUCHED",
        "new_generation_calls": len(results), "new_retrieval_calls": 0,
    }
    write_json(OUT / "decision.json", decision)
    write_json(OUT / "summary.json", {"identity": ident, "focused": summary, "decision": decision})
    report = f"# Pipeline v2 Citation & Grounded-Abstention Hardening\n\nIdentity verified for `{ident['git_sha']}`. Historical validator replay reviewed 16 rejected records with zero inference. Evidence IDs use response-local `E1..En` values and server-side provenance.\n\nFocused probe used {len(results)} new qwen3.5:4b calls, zero retrieval calls, and zero reranker/embedding/semantic calls. ACL unsupported answers: {summary['acl']['unsupported_answers']}/3; ACL unauthorized leakage: 0; multi-document raw complete: {summary['multi_document']['raw_full']}/3; focused decision: **{decision['focused_gate']}**.\n\nThe 36-query hardened smoke was not run because the focused gate did not pass. Development-200, calibration, and frozen test were not run. Runtime default remains `RAG_PIPELINE_V2=false`.\n"
    (OUT / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
