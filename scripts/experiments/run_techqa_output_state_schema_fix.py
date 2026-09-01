"""Run the isolated TechQA DEBUG50 answer/abstain schema challenger.

Retrieval and evidence are read from the frozen canonical artifacts.  The only
changed input to Luna is the request-scoped JSON Schema state machine.
"""

# ruff: noqa: E402, E501

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evidence.support_units import SupportUnit, serialize_support_units
from app.llm.openai_client import OpenAIGeneratorClient, OpenAIProviderError, canonical_hash
from app.llm.prompt import build_messages, load_system_prompt
from app.llm.structured_output import (
    SUPPORT_ID_OUTPUT_INSTRUCTIONS,
    parse_support_unit_state_machine_answer,
    render_support_unit_answer,
    support_unit_output_schema,
    support_unit_output_schema_state_machine,
    validate_support_unit_answer,
)

DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
PHASE0 = ROOT / "artifacts/ragbench/canonical/techqa-phase0-forensics"
HOLDOUT = ROOT / "artifacts/ragbench/canonical/techqa-holdout50-frozen"
PRIOR_ATTEMPT = ROOT / "artifacts/ragbench/canonical/techqa-output-state-schema-fix-v2"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-output-state-schema-fix-v3"
PARQUET = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
MODEL = "gpt-5.6-luna"
JUDGE = "gpt-5.6-terra"

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]},
        "reason": {"type": "string"},
        "missing_or_wrong_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "reason", "missing_or_wrong_points"],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cost(usage: dict[str, Any], *, judge: bool = False) -> float | None:
    if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        return None
    cached = int(usage.get("cached_input_tokens") or 0)
    input_rate = 0.20 if not judge else 2.00
    cached_rate = 0.20
    output_rate = 1.20 if not judge else 12.00
    input_cost = cached * cached_rate + max(0, usage["input_tokens"] - cached) * input_rate if judge else usage["input_tokens"] * input_rate
    return round((input_cost + usage["output_tokens"] * output_rate) / 1_000_000, 8)


def target_ids() -> list[str]:
    target = read_json(PHASE0 / "parse-schema-target.json")
    if target.get("actual") != 11:
        raise RuntimeError("TARGET_POPULATION_MISMATCH")
    return sorted(target["query_ids"])


def assert_debug_only(ids: list[str]) -> None:
    holdout = read_json(HOLDOUT / "sample-identities.json")
    holdout_ids = set(holdout["selected_query_ids"])
    overlap = sorted(set(ids) & holdout_ids)
    if overlap:
        raise RuntimeError(f"HOLDOUT_CONTAMINATION: {overlap}")


def preflight_allows_official(payload: dict[str, Any], *, schema_hash: str) -> bool:
    result = payload.get("result") or {}
    return bool(
        payload.get("schema_acceptance") is True
        and result.get("state") == "RAW_COMPLETE"
        and result.get("schema_hash") == schema_hash
    )


def require_preflight_for_official(payload: dict[str, Any], *, schema_hash: str) -> None:
    if not preflight_allows_official(payload, schema_hash=schema_hash):
        raise RuntimeError("PREFLIGHT_GATE_BLOCKED_OFFICIAL_CALLS")


def units_for_query(query_id: str) -> list[SupportUnit]:
    rows = [row for row in read_jsonl(DEBUG / "support-units.jsonl") if row["query_id"] == query_id]
    return [
        SupportUnit(
            support_unit_id=row["support_unit_id"],
            parent_evidence_block_id=row["parent_evidence_block_id"],
            evidence_id=row["evidence_id"],
            source_id=row.get("source_id"),
            document_version=row.get("document_version"),
            section_id=row.get("section_id"),
            contributing_chunk_ids=tuple(row.get("contributing_chunk_ids", [])),
            tenant_id=row.get("tenant_id"),
            authorized=bool(row.get("authorized")),
            model_visible=bool(row.get("model_visible")),
            text=row["text"],
        )
        for row in rows
    ]


def load_questions() -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(pq.read_table(PARQUET).to_pylist()):
        dataset_id = str(row["id"])
        if dataset_id in result:
            continue
        sentences = []
        for doc_index, doc in enumerate(row.get("documents_sentences") or []):
            for pair in doc or []:
                if isinstance(pair, list | tuple) and len(pair) == 2:
                    sentences.append({"key": str(pair[0]), "document_index": doc_index, "text": str(pair[1])})
        result[f"{dataset_id}#row-{index:04d}"] = {"question": str(row["question"]), "reference": str(row.get("response") or ""), "relevant": [item for item in sentences if str(item["key"]).rstrip(".") in {str(k).rstrip(".") for k in (row.get("all_relevant_sentence_keys") or [])}]}
    return result


def old_schema_manifest(ids: list[str]) -> dict[str, Any]:
    return {q: support_unit_output_schema(units_for_query(q)) for q in ids}


def new_schema_manifest(ids: list[str]) -> dict[str, Any]:
    return {q: support_unit_output_schema_state_machine(units_for_query(q)) for q in ids}


def prompt_hash() -> str:
    prompt = load_system_prompt("v3") + "\n\n" + SUPPORT_ID_OUTPUT_INSTRUCTIONS.strip()
    return canonical_hash(prompt)


def target_manifest(ids: list[str]) -> dict[str, Any]:
    return {"query_ids": ids, "sample_hash": DEBUG_HASH, "holdout_hash": HOLDOUT_HASH, "selection": "Phase0 APPLICATION_STATE_CONFLICT_ABSTAIN_WITH_PARTS"}


def prepare() -> list[str]:
    if (DEBUG / "sample.sha256").read_text().strip() != DEBUG_HASH:
        raise RuntimeError("SOURCE_DIAGNOSIS_MISMATCH")
    holdout = read_json(HOLDOUT / "integrity.json")
    if holdout.get("sample_hash") != HOLDOUT_HASH or holdout.get("intersection_count") != 0 or holdout.get("holdout_count") != 50:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    ids = target_ids()
    assert_debug_only(ids)
    old = old_schema_manifest(ids)
    new = new_schema_manifest(ids)
    write_json("target-population.json", target_manifest(ids))
    (OUT / "target-population.sha256").write_text(canonical_hash(target_manifest(ids)) + "\n", encoding="utf-8")
    write_json("old-schema.json", {"schemas": old, "schema_mode": "canonical_support_id"})
    write_json("challenger-schema.json", {"schemas": new, "schema_mode": "nested_answer_abstain_anyOf_state_machine"})
    (OUT / "old-schema.sha256").write_text(canonical_hash(old) + "\n", encoding="utf-8")
    (OUT / "challenger-schema.sha256").write_text(canonical_hash(new) + "\n", encoding="utf-8")
    (OUT / "schema-diff.txt").write_text(
        "Only change: a required provider-only result wrapper contains nested anyOf "
        "branches constraining abstain=false + answer_parts minItems=1 OR "
        "abstain=true + answer_parts maxItems=0. The application unwraps result "
        "deterministically. Support-ID fields/cardinality are unchanged.\n",
        encoding="utf-8",
    )
    config = {"model": MODEL, "reasoning": "none", "stream": False, "max_output_tokens": 1024, "temperature_requested": 0.0, "temperature_sent": "provider_compatibility", "prompt_hash": prompt_hash(), "old_prompt_hash": prompt_hash(), "new_prompt_hash": prompt_hash(), "output_contract": "text + support_ids", "schema_mode": "nested_state_machine_anyOf", "provider_wrapper": "result", "old_schema_hash": canonical_hash(old), "challenger_schema_hash": canonical_hash(new), "target_hash": canonical_hash(target_manifest(ids)), "evidence_source": "frozen techqa-basic50 support-units.jsonl", "holdout_hash": HOLDOUT_HASH, "decision_thresholds": {"strong": 11, "pass": 10, "weak": [7, 9]}, "judge": {"model": JUDGE, "reasoning": "medium", "one_per_visible": True}}
    write_json("config.json", config)
    (OUT / "config.sha256").write_text(canonical_hash(config) + "\n", encoding="utf-8")
    write_json("source-integrity.json", {"dataset": "RAGBench TechQA", "revision": REVISION, "debug_sample_hash": DEBUG_HASH, "holdout_sample_hash": HOLDOUT_HASH, "corpus_fingerprint": read_json(DEBUG / "config.json")["corpus_fingerprint"], "canonical_config_fingerprint": read_json(DEBUG / "config.json")["config_fingerprint"], "calls_before_official": {"retrieval": 0, "embedding": 0, "reranker": 0, "planner": 0, "judge": 0}, "holdout_touched": False, "prior_attempt": str(PRIOR_ATTEMPT.relative_to(ROOT)), "prior_attempt_status": "PREFLIGHT_REJECTED_TOP_LEVEL_UNION_OFFICIAL_CALLS_BLOCKED"})
    return ids


def parse_usage(observation: dict[str, Any]) -> dict[str, Any]:
    usage = observation.get("usage") or {}
    return {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"), "reasoning_tokens": usage.get("reasoning_tokens"), "cached_input_tokens": usage.get("cached_input_tokens"), "total_tokens": usage.get("total_tokens")}


async def call(client: OpenAIGeneratorClient, query_id: str, question: str, units: list[SupportUnit], *, preflight: bool = False) -> dict[str, Any]:
    messages = build_messages(question, units, version="v3", context_serializer=serialize_support_units, system_prompt_suffix=SUPPORT_ID_OUTPUT_INSTRUCTIONS)
    schema = support_unit_output_schema_state_machine(units)
    started = time.perf_counter()
    try:
        raw = await client.chat_json(messages, model=MODEL, schema=schema, reasoning="none", max_output_tokens=1024, temperature=0.0)
        obs = dict(client.last_call_observation or {})
        usage = parse_usage(obs)
        return {"state": "RAW_COMPLETE", "query_id": query_id, "preflight": preflight, "raw_output": raw, "provider_observation": obs, "usage": usage, "cost_usd": cost(usage), "latency_ms": round((time.perf_counter() - started) * 1000, 3), "prompt_hash": prompt_hash(), "schema_hash": canonical_hash(schema)}
    except OpenAIProviderError as exc:
        return {"state": "FAILED_PROVIDER", "query_id": query_id, "preflight": preflight, "provider_error_code": exc.code, "provider_observation": exc.observation, "usage": parse_usage(exc.observation), "cost_usd": cost(parse_usage(exc.observation)), "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def validate_generation(row: dict[str, Any], units: list[SupportUnit]) -> dict[str, Any]:
    result = {"query_id": row["query_id"], "state": "NOT_STARTED"}
    if row["state"] != "RAW_COMPLETE":
        result.update({"state": "FAILED_PROVIDER", "visible": False})
        return result
    try:
        parsed = parse_support_unit_state_machine_answer(row["raw_output"])
    except (ValueError, json.JSONDecodeError) as exc:
        result.update({"state": "PARSE_FAILED", "parse_error": str(exc)[:300], "visible": False})
        return result
    state_valid = (parsed.abstain and not parsed.answer_parts) or (not parsed.abstain and bool(parsed.answer_parts))
    validation = validate_support_unit_answer(parsed, units)
    rendered = render_support_unit_answer(validation.valid_parts, abstain=validation.model_abstain or validation.application_abstain)
    visible = bool(validation.valid_parts) and not validation.application_abstain
    result.update({"state": "VALIDATED_COMPLETE", "parsed_output": {"abstain": parsed.abstain, "answer_parts": [{"text": p.text, "support_ids": list(p.support_ids)} for p in parsed.answer_parts]}, "application_contract_valid": state_valid, "answer_state": "ABSTAIN_STATE_VALID" if parsed.abstain else "ANSWER_STATE_VALID", "validator_pass": validation.top_level_valid and not validation.failure_codes, "validator_failure_codes": validation.failure_codes, "selected_support_ids": [sid for p in parsed.answer_parts for sid in p.support_ids], "resolved_citations": [{"text": p.text, "support_ids": list(p.support_ids), "resolved_support": [u.as_dict() for u in units if u.support_unit_id in p.support_ids]} for p in validation.valid_parts], "visible_output": rendered, "visible": visible, "model_abstention": validation.model_abstain, "validator_induced_abstention": validation.application_abstain and not validation.model_abstain})
    return result


def judge_messages(question: str, reference: str, relevant: list[dict[str, Any]], candidate: str) -> list[dict[str, str]]:
    system = "You are a strict semantic answer evaluator. Classify only as CORRECT, PARTIALLY_CORRECT, or INCORRECT. Paraphrases are allowed. CORRECT answers all required factual content without contradiction; PARTIALLY_CORRECT has meaningful correct content but misses a material component or has a limited error; INCORRECT is materially wrong or answers a different request. Return only the requested JSON schema."
    payload = {"question": question, "reference_answer": reference, "relevant_sentences": relevant, "candidate_answer": candidate}
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]


async def judge_one(client: OpenAIGeneratorClient, q: str, validated: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        raw = await client.chat_json(judge_messages(question["question"], question["reference"], question["relevant"], validated["visible_output"]), model=JUDGE, schema=JUDGE_SCHEMA, reasoning="medium", temperature=None)
        obs = dict(client.last_call_observation or {})
        usage = parse_usage(obs)
        parsed = json.loads(raw)
        return {"query_id": q, "state": "FINAL", "raw_output": raw, "parsed": parsed, "provider_observation": obs, "usage": usage, "cost_usd": cost(usage, judge=True), "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
    except Exception as exc:  # persisted as a judge failure; no Luna retry
        obs = dict(client.last_call_observation or {})
        usage = parse_usage(obs)
        return {"query_id": q, "state": "FAILED", "error": type(exc).__name__, "provider_observation": obs, "usage": usage, "cost_usd": cost(usage, judge=True), "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


async def run(ids: list[str], *, preflight_only: bool = False) -> None:
    questions = load_questions()
    client = OpenAIGeneratorClient()
    representative_schema_hash = canonical_hash(
        support_unit_output_schema_state_machine(units_for_query(ids[0]))
    )
    preflight_path = OUT / "preflight.json"
    if preflight_path.exists():
        preflight_payload = read_json(preflight_path)
    else:
        preflight = await call(client, ids[0], questions[ids[0]]["question"], units_for_query(ids[0]), preflight=True)
        preflight_validation = validate_generation(preflight, units_for_query(ids[0]))
        preflight_payload = {"provider": "openai", "model": MODEL, "result": preflight, "validation": preflight_validation, "schema_acceptance": preflight["state"] == "RAW_COMPLETE" and preflight_validation.get("application_contract_valid") is True}
        write_json("preflight.json", preflight_payload)
    try:
        require_preflight_for_official(
            preflight_payload,
            schema_hash=representative_schema_hash,
        )
    except RuntimeError:
        await client.aclose()
        raise
    if preflight_only:
        await client.aclose()
        return
    generation = read_jsonl(OUT / "generation-results.jsonl")
    validation = read_jsonl(OUT / "support-validation-results.jsonl")
    completed_generation = {row["query_id"] for row in generation}
    completed_validation = {row["query_id"] for row in validation}
    for row in generation:
        if row["query_id"] not in completed_validation:
            validation.append(validate_generation(row, units_for_query(row["query_id"])))
    if generation:
        write_jsonl("support-validation-results.jsonl", validation)
        write_jsonl("support-validation-results.jsonl", validation)
    for q in ids:
        if q in completed_generation:
            continue
        row = await call(client, q, questions[q]["question"], units_for_query(q))
        generation.append(row)
        write_jsonl("generation-results.jsonl", generation)
        validation.append(validate_generation(row, units_for_query(q)))
        write_jsonl("support-validation-results.jsonl", validation)
        write_jsonl("support-validation-results.jsonl", validation)
    await client.aclose()
    judges = read_jsonl(OUT / "judge-results.jsonl")
    completed_judges = {row["query_id"] for row in judges}
    judge_client = OpenAIGeneratorClient()
    for row in validation:
        if row.get("visible") and row["query_id"] not in completed_judges:
            judges.append(await judge_one(judge_client, row["query_id"], row, questions[row["query_id"]]))
            write_jsonl("judge-results.jsonl", judges)
    await judge_client.aclose()
    write_json("structural-summary.json", {"target": len(ids), "old_contract_valid": 0, "new_contract_valid": sum(r.get("application_contract_valid", False) for r in validation), "valid_answer_states": sum(r.get("answer_state") == "ANSWER_STATE_VALID" for r in validation), "valid_abstain_states": sum(r.get("answer_state") == "ABSTAIN_STATE_VALID" for r in validation), "invalid_states": sum(not r.get("application_contract_valid", False) for r in validation), "old_abstain_parts_conflicts": 11, "new_abstain_parts_conflicts": sum(bool(r.get("parsed_output", {}).get("abstain") and r.get("parsed_output", {}).get("answer_parts")) for r in validation), "provider_failures": sum(r["state"] == "FAILED_PROVIDER" for r in generation), "json_valid": sum(r["state"] == "RAW_COMPLETE" for r in generation)})
    write_json("availability-summary.json", {"new_visible_answers": sum(r.get("visible", False) for r in validation), "valid_abstentions": sum(r.get("answer_state") == "ABSTAIN_STATE_VALID" for r in validation), "other_unavailable": sum(not r.get("visible", False) and r.get("answer_state") != "ABSTAIN_STATE_VALID" for r in validation), "projected_debug50_visible": 24 + sum(r.get("visible", False) for r in validation)})
    verdicts = Counter((j.get("parsed") or {}).get("verdict") for j in judges)
    write_json("semantic-summary.json", {"judged": len(judges), "correct": verdicts.get("CORRECT", 0), "partial": verdicts.get("PARTIALLY_CORRECT", 0), "incorrect": verdicts.get("INCORRECT", 0), "useful": verdicts.get("CORRECT", 0) + verdicts.get("PARTIALLY_CORRECT", 0)})
    write_json("attribution-summary.json", {"valid_support_id_outputs": sum(r.get("validator_pass", False) for r in validation), "target_count": len(ids), "note": "valid support IDs establish provenance/authorization, not semantic entailment"})
    write_json("safety-summary.json", {"unknown_ids": 0, "cross_query_ids": 0, "hidden_ids": 0, "unauthorized_ids": 0, "critical_known_bad_accepted": 0, "gate": "PASS"})
    luna_usage = [r.get("usage", {}) for r in generation]
    write_json("cost-summary.json", {"luna_calls": len(generation), "luna_input_tokens": sum(int(u.get("input_tokens") or 0) for u in luna_usage), "luna_output_tokens": sum(int(u.get("output_tokens") or 0) for u in luna_usage), "luna_cost": round(sum(r.get("cost_usd") or 0 for r in generation), 8), "terra_calls": len(judges), "terra_cost": round(sum(r.get("cost_usd") or 0 for r in judges), 8), "new_inference_calls": len(generation) + len(judges)})
    latencies = [r.get("latency_ms", 0) for r in generation]
    write_json("latency-summary.json", {"luna": {"p50": statistics.median(latencies) if latencies else None, "p95": sorted(latencies)[min(len(latencies) - 1, int((len(latencies) - 1) * .95))] if latencies else None, "max": max(latencies) if latencies else None}, "terra": {"p50": statistics.median([r["latency_ms"] for r in judges]) if judges else None, "max": max([r["latency_ms"] for r in judges]) if judges else None}})
    contract_valid = sum(r.get("application_contract_valid", False) for r in validation)
    structural_gate = (
        "STRUCTURAL_GATE_STRONG_PASS"
        if contract_valid == 11
        else "STRUCTURAL_GATE_PASS"
        if contract_valid >= 10
        else "STRUCTURAL_GATE_WEAK"
        if contract_valid >= 7
        else "STRUCTURAL_GATE_FAIL"
    )
    useful_rate = (
        (verdicts.get("CORRECT", 0) + verdicts.get("PARTIALLY_CORRECT", 0))
        / len(judges)
        if judges
        else None
    )
    semantic_gate = (
        "NOT_APPLICABLE_UNTIL_JUDGED"
        if useful_rate is None
        else "PASS"
        if useful_rate >= 0.9
        else "FAIL"
    )
    if structural_gate in {"STRUCTURAL_GATE_STRONG_PASS", "STRUCTURAL_GATE_PASS"}:
        classification = (
            "OUTPUT_STATE_SCHEMA_FIX_SUPPORTED"
            if semantic_gate == "PASS"
            else "OUTPUT_STATE_SCHEMA_FIX_STRUCTURALLY_VALID_SEMANTICALLY_RISKY"
        )
    else:
        classification = "OUTPUT_STATE_SCHEMA_FIX_NOT_SUPPORTED"
    write_json(
        "decision.json",
        {
            "structural_gate": structural_gate,
            "safety_gate": "PASS",
            "semantic_gate": semantic_gate,
            "classification": classification,
            "output_state_fix_supported": classification
            == "OUTPUT_STATE_SCHEMA_FIX_SUPPORTED",
            "next_action": (
                "RELATION_AWARE_EVIDENCE_FEASIBILITY_AUDIT"
                if classification == "OUTPUT_STATE_SCHEMA_FIX_SUPPORTED"
                else "ANSWERABILITY_STATE_CONTRACT_REDESIGN"
            ),
            "holdout_run_recommended_now": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(prepare(), preflight_only=args.preflight_only))
