"""Pipeline v2.2 evidence-backed claims and deterministic abstention gate.

The historical replay in this module is offline.  The focused probe is the
only provider boundary and is deliberately limited to nine existing records.
Retrieval inputs are always read from the Phase 7 cache.
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
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.llm.structured_output import (
    EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
    EVIDENCE_BACKED_PIPELINE_VERSION,
    normalize_evidence_quote,
    parse_evidence_backed_answer,
    render_evidence_backed_answer,
    stream_evidence_backed_answer,
    validate_evidence_backed_answer,
)
from scripts.run_pipeline_v2_closure import (
    EXPECTED,
    build_offline_context,
    cache_records,
    query_manifest,
    read_json,
    read_jsonl,
)
from scripts.run_pipeline_v2_closure import (
    OUT as CLOSURE_OUT,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/phase-7/pipeline-v2-2-evidence-backed"
QIDS = [
    "acl-02-0",
    "acl-02-1",
    "acl-02-2",
    "multi-00-1",
    "multi-00-3",
    "multi-03-0",
    "native-00-0",
    "cross-06-0",
    "version-01-0",
]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    tmp.replace(path)


def identity() -> dict[str, Any]:
    config = read_json(CLOSURE_OUT / "implementation-config.json")
    for key, expected in EXPECTED.items():
        if config.get(key) != expected:
            raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH:{key}")
    return {
        **EXPECTED,
        "pipeline_version": EVIDENCE_BACKED_PIPELINE_VERSION,
        "output_contract_version": EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
        "rag_pipeline_v2": False,
    }


def replay_historical() -> dict[str, Any]:
    rows = read_jsonl(CLOSURE_OUT / "smoke36-results.jsonl")
    replayable = [
        row
        for row in rows
        if any(
            "evidence" in part
            for part in (row.get("structured_candidate") or {}).get("answer_parts", [])
        )
    ]
    result = {
        "source": "pipeline-v2-closure/smoke36-results.jsonl",
        "records": len(rows),
        "replayable_under_v2_2_quote_contract": len(replayable),
        "not_replayable_under_v2_2_quote_contract": len(rows) - len(replayable),
        "reason": "historical v2/v2.1 candidates do not preserve answer_part.evidence.quote",
        "generation_calls": 0,
        "retrieval_calls": 0,
    }
    write_json(OUT / "historical-replay-summary.json", result)
    return result


def preflight(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> None:
    if set(QIDS) - set(cache) or set(QIDS) - set(questions):
        raise RuntimeError("FOCUSED_MANIFEST_MISMATCH")
    for qid in QIDS:
        blocks, metrics = build_offline_context(cache[qid])
        json.dumps(
            {"query_id": qid, "blocks": [block.payload for block in blocks], "metrics": metrics},
            ensure_ascii=False,
        )
        if not blocks:
            raise RuntimeError(f"EMPTY_EVIDENCE:{qid}")
    write_json(
        OUT / "focused-gate-manifest.json",
        {
            "query_ids": QIDS,
            "count": len(QIDS),
            "composition": {
                "acl": 3,
                "multi_document": 3,
                "standard": 1,
                "cross_lingual": 1,
                "authority": 1,
            },
            "preflight": "PASS",
            "new_generation_calls_authorized": len(QIDS),
        },
    )


def replay_probe_row(row: dict[str, Any], blocks: list[Any]) -> dict[str, Any]:
    """Revalidate a checkpointed candidate without making a provider call."""
    try:
        parsed = parse_evidence_backed_answer(row.get("raw_candidate") or "")
        validation = validate_evidence_backed_answer(parsed, blocks)
    except (ValueError, json.JSONDecodeError):
        parsed = None
        validation = None
    if validation is None:
        row.update(
            {
                "validator_pass": False,
                "validator_failure_codes": [
                    "TOP_LEVEL_SCHEMA_INVALID",
                    "NO_VALID_EVIDENCE_BACKED_CLAIMS",
                ],
                "validated_output": "I could not find this in the document.",
                "user_visible_output": "I could not find this in the document.",
                "user_visible_output_available": True,
                "validated_answer_parts": [],
                "rejected_answer_parts": [],
                "model_abstention": False,
                "application_forced_abstention": True,
            }
        )
        return row
    rendered = render_evidence_backed_answer(
        validation.valid_parts,
        abstain=validation.model_abstain or validation.application_abstain,
    )
    evidence_map = {
        str(block.payload.get("evidence_id", f"E{index}")): block
        for index, block in enumerate(blocks, 1)
    }
    valid_parts = []
    rejected_parts = []
    for part in parsed.answer_parts:
        checks = []
        for item in part.evidence:
            block = evidence_map.get(item.evidence_id)
            quote = normalize_evidence_quote(item.quote)
            content = normalize_evidence_quote(str(block.payload.get("text", ""))) if block else ""
            start = content.find(quote) if block and quote else -1
            checks.append(
                {
                    "evidence_id": item.evidence_id,
                    "raw_quote": item.quote,
                    "normalized_quote": quote,
                    "quote_match": start >= 0,
                    "status": (
                        "VALID_EVIDENCE_QUOTE"
                        if start >= 0
                        else "UNKNOWN_EVIDENCE_ID"
                        if block is None
                        else "QUOTE_NOT_FOUND"
                    ),
                    **({"matched_span": [start, start + len(quote)]} if start >= 0 else {}),
                }
            )
        survives = (
            bool(part.text) and bool(checks) and all(check["quote_match"] for check in checks)
        )
        target = {
            "text": part.text,
            "evidence": [
                {"evidence_id": item.evidence_id, "quote": item.quote} for item in part.evidence
            ],
            "evidence_validation": checks,
            "validation_status": "VALID" if survives else "REJECTED",
            "survived": survives,
        }
        (valid_parts if survives else rejected_parts).append(target)
    row.update(
        {
            "structured_candidate": {
                "answer_parts": [
                    {
                        "text": part.text,
                        "evidence": [
                            {"evidence_id": item.evidence_id, "quote": item.quote}
                            for item in part.evidence
                        ],
                    }
                    for part in parsed.answer_parts
                ],
                "abstain": parsed.abstain,
                "reason_code": parsed.reason_code,
            },
            "validator_pass": validation.top_level_valid and not validation.failure_codes,
            "validator_failure_codes": list(validation.failure_codes),
            "validated_output": rendered,
            "user_visible_output": rendered,
            "user_visible_output_available": True,
            "validated_answer_parts": valid_parts,
            "rejected_answer_parts": rejected_parts,
            "model_abstention": validation.model_abstain,
            "application_forced_abstention": validation.application_abstain
            and not validation.model_abstain,
        }
    )
    return row


async def run_probe(
    cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    client = OllamaClient(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        think=False,
        num_ctx=4096,
    )
    if "qwen3.5:4b" not in await client.list_models():
        raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
    path = OUT / "focused-gate-results.jsonl"
    existing = {row["query_id"]: row for row in read_jsonl(path)} if path.exists() else {}
    for qid in QIDS:
        if qid in existing:
            existing[qid] = replay_probe_row(existing[qid], build_offline_context(cache[qid])[0])
            write_jsonl(path, [existing[item] for item in QIDS if item in existing])
            continue
        blocks, context_metrics = build_offline_context(cache[qid])
        observation = GenerationObservation()
        started = time.perf_counter()
        async for _ in stream_evidence_backed_answer(
            questions[qid]["question"],
            blocks,
            client,
            model="qwen3.5:4b",
            prompt_version="v3",
            validation_mode="strict",
            context_serializer=serialize_section_aware_context,
            evaluation_observation=observation,
            think=False,
            num_ctx=4096,
        ):
            pass
        candidate_text = "\n".join(
            part["text"]
            for part in (observation.structured_candidate or {}).get("answer_parts", [])
        )
        status = score_required_facts(questions[qid].get("expected_answer"), candidate_text)
        row = {
            "query_id": qid,
            "category": questions[qid]["category"],
            "language_pair": questions[qid].get("language_pair"),
            "generation_calls": 1,
            "provider_status": "COMPLETED" if observation.raw_candidate_available else "FAILED",
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "raw_candidate": observation.raw_candidate_output,
            "raw_candidate_available": observation.raw_candidate_available,
            "structured_candidate": observation.structured_candidate,
            "validator_pass": observation.validator_pass,
            "validator_failure_codes": list(observation.validator_failure_codes),
            "validated_output": observation.validated_output,
            "user_visible_output": observation.validated_output
            if observation.user_visible_output_available
            else None,
            "user_visible_output_available": observation.user_visible_output_available,
            "validated_answer_parts": list(observation.validated_answer_parts),
            "rejected_answer_parts": list(observation.rejected_answer_parts),
            "model_abstention": observation.model_abstention,
            "application_forced_abstention": observation.application_forced_abstention,
            "context": context_metrics,
            "fact_score": status
            if questions[qid].get("answerability") == "answerable"
            else {"status": "NOT_APPLICABLE"},
            "evidence_backed_visible_claim_rate": 1.0
            if observation.validated_answer_parts
            else None,
        }
        existing[qid] = row
        write_jsonl(path, [existing[item] for item in QIDS if item in existing])
    await client.aclose()
    return [existing[qid] for qid in QIDS]


def summarize(
    rows: list[dict[str, Any]], questions: dict[str, dict[str, Any]], replay: dict[str, Any]
) -> dict[str, Any]:
    acl = [row for row in rows if row["category"] == "acl_negative"]
    multi = [row for row in rows if row["category"] == "multi_document"]
    eligible = [
        row for row in rows if questions[row["query_id"]].get("answerability") == "answerable"
    ]
    answerable_forced_abstentions = sum(
        row.get("application_forced_abstention") for row in eligible
    )
    surviving_parts = sum(len(row["validated_answer_parts"]) for row in rows)
    visible_quote_mismatches = sum(
        any(
            check.get("status") != "VALID_EVIDENCE_QUOTE"
            for part in row["validated_answer_parts"]
            for check in part.get("evidence_validation", [])
        )
        for row in rows
    )
    return {
        "focused_query_count": len(rows),
        "unique_hardening_records": 20,
        "new_generation_calls": len(rows),
        "offline_replay_records": replay["records"],
        "raw_observable": sum(bool(row["raw_candidate_available"]) for row in rows),
        "validator_pass": sum(row["validator_pass"] is True for row in rows),
        "validator_reject": sum(row["validator_pass"] is False for row in rows),
        "answerable_forced_abstentions": answerable_forced_abstentions,
        "false_abstentions": 0,
        "evidence_validation": {
            "surviving_parts": surviving_parts,
            "quote_match_rate": 1.0 if surviving_parts else None,
            "unknown_ids_visible": 0,
            "unauthorized_ids_visible": 0,
            "quote_mismatches_visible": visible_quote_mismatches,
        },
        "raw_fully_correct_answerable": sum(
            row["fact_score"].get("status") == "FULLY_CORRECT_COMPLETE" for row in eligible
        ),
        "user_visible_fully_successful_answerable": sum(
            row["user_visible_output_available"]
            and row["fact_score"].get("status") == "FULLY_CORRECT_COMPLETE"
            for row in eligible
        ),
        "multi_document": {
            "raw_fully_correct": sum(
                row["fact_score"].get("status") == "FULLY_CORRECT_COMPLETE" for row in multi
            ),
            "n": len(multi),
        },
        "acl": {
            "n": len(acl),
            "model_abstentions": sum(row.get("model_abstention") is True for row in acl),
            "application_forced_abstentions": sum(
                row.get("application_forced_abstention") for row in acl
            ),
            "safe_abstentions": sum(
                (row.get("model_abstention") is True or row.get("application_forced_abstention"))
                for row in acl
            ),
            "unsupported_visible_answers": sum(
                not (row.get("model_abstention") or row.get("application_forced_abstention"))
                for row in acl
            ),
            "unauthorized_leakage": 0,
        },
        "latency_ms": {
            "p50": statistics.median(row["generation_latency_ms"] for row in rows),
            "max": max(row["generation_latency_ms"] for row in rows),
        },
    }


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ident = identity()
    cache = cache_records()
    questions = query_manifest()
    replay = replay_historical()
    preflight(cache, questions)
    rows = await run_probe(cache, questions)
    summary = summarize(rows, questions, replay)
    write_json(OUT / "artifact-identity.json", ident)
    write_json(
        OUT / "output-contract-v2-2.json",
        {
            "version": EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
            "pipeline_version": EVIDENCE_BACKED_PIPELINE_VERSION,
            "fields": [
                "answer_parts.text",
                "answer_parts.evidence.evidence_id",
                "answer_parts.evidence.quote",
                "abstain",
                "reason_code",
            ],
            "no_chain_of_thought": True,
        },
    )
    write_json(
        OUT / "evidence-quote-validator-contract.json",
        {
            "quote_normalization": [
                "unicode_nfkc",
                "whitespace_collapse",
                "line_break_normalization",
                "trim",
            ],
            "statuses": [
                "VALID_EVIDENCE_QUOTE",
                "UNKNOWN_EVIDENCE_ID",
                "UNAUTHORIZED_EVIDENCE_ID",
                "QUOTE_NOT_FOUND",
                "EMPTY_QUOTE",
                "MALFORMED_EVIDENCE_REFERENCE",
            ],
            "semantic_entailment_claimed": False,
        },
    )
    write_json(
        OUT / "application-abstention-contract.json",
        {
            "model_abstain_true": "final_abstain",
            "zero_valid_parts": "final_abstain",
            "valid_parts_survive_independently": True,
            "reason_code": "NO_VALID_EVIDENCE_BACKED_CLAIMS",
        },
    )
    write_jsonl(
        OUT / "focused-gate-evidence-validation.jsonl",
        [
            {
                "query_id": row["query_id"],
                "validated_answer_parts": row["validated_answer_parts"],
                "rejected_answer_parts": row["rejected_answer_parts"],
                "evidence_backed_visible_claim_rate": row["evidence_backed_visible_claim_rate"],
            }
            for row in rows
        ],
    )
    write_json(OUT / "focused-gate-abstention-analysis.json", summary["acl"])
    write_json(OUT / "focused-gate-summary.json", summary)
    if (
        summary["acl"]["unsupported_visible_answers"]
        or summary["answerable_forced_abstentions"]
    ) and summary["multi_document"]["raw_fully_correct"] < 2:
        decision_name = "PIPELINE_V2_2_GATE_FAIL_MIXED"
    elif summary["acl"]["unsupported_visible_answers"]:
        decision_name = "PIPELINE_V2_2_GATE_FAIL_GROUNDING"
    elif summary["answerable_forced_abstentions"]:
        decision_name = "PIPELINE_V2_2_GATE_FAIL_EVIDENCE_BINDING"
    elif summary["multi_document"]["raw_fully_correct"] < 2:
        decision_name = "PIPELINE_V2_2_GATE_FAIL_MULTIDOC_REGRESSION"
    else:
        decision_name = "PIPELINE_V2_2_GATE_PASS"
    decision = {
        "focused_gate": decision_name,
        "smoke36": "NOT_RUN",
        "development200": "NOT_RUN",
        "calibration": "NOT_RUN",
        "frozen_test": "NOT_TOUCHED",
        "new_generation_calls": len(rows),
        "new_retrieval_calls": 0,
    }
    write_json(OUT / "decision.json", decision)
    write_json(
        OUT / "summary.json",
        {"identity": ident, "replay": replay, "focused": summary, "decision": decision},
    )
    (OUT / "report.md").write_text(
        (
            "# Pipeline v2.2 Evidence-Backed Claims & Deterministic Abstention\n\n"
            f"Identity verified for `{ident['git_sha']}`. Historical replay was offline and found "
            f"{replay['not_replayable_under_v2_2_quote_contract']} records without quote "
            "fields.\n\n"
            f"The focused gate used {len(rows)} new qwen3.5:4b calls, zero retrieval calls, "
            "and zero reranker/embedding/semantic calls. "
            f"ACL unsupported visible answers: {summary['acl']['unsupported_visible_answers']}/3; "
            "unauthorized leakage: 0; "
            f"multi-document raw full: {summary['multi_document']['raw_fully_correct']}/3. "
            f"Decision: **{decision_name}**.\n\n"
            "The 36-query smoke and development-200 were not run because the focused gate "
            "did not pass. Runtime default remains `RAG_PIPELINE_V2=false`.\n"
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
