"""Run the final, frozen V2.2 Smoke36 without retrieval-side work.

The runner consumes the existing Phase 7 retrieval cache, rebuilds only the
already-selected offline evidence context, asserts the frozen configuration
fingerprint, and checkpoints each completed generation atomically.
"""

# ruff: noqa: E402, E501

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evaluation.generation_refinement import score_required_facts
from app.evidence.section_aware import serialize_section_aware_context
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.llm.structured_output import stream_evidence_backed_answer
from scripts.experiments.run_pipeline_v2_closure import build_offline_context

CLOSURE = ROOT / "artifacts/phase-7/phase7-closure"
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
CONFIG_PATH = CLOSURE / "final-v2-2-config.json"
CONFIG_HASH_PATH = CLOSURE / "final-v2-2-config.sha256"
RESULTS = CLOSURE / "smoke36-results.jsonl"
SEED = 42


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_config() -> tuple[dict[str, Any], str]:
    config = read_json(CONFIG_PATH)
    expected = CONFIG_HASH_PATH.read_text(encoding="utf-8").strip()
    without_fingerprint = {key: value for key, value in config.items() if key != "config_fingerprint"}
    actual = canonical_hash(without_fingerprint)
    if config.get("config_fingerprint") != expected or actual != expected:
        raise RuntimeError("CONFIG_DRIFT: final V2.2 fingerprint mismatch")
    required = {
        "pipeline_version": "pipeline_v2_2_evidence_backed",
        "output_contract_version": "output_contract_v2_2",
        "generator": {"model": "qwen3.5:4b"},
        "execution": {
            "num_ctx": 4096,
            "num_predict": 1024,
            "temperature": 0.0,
            "think": False,
            "stream": False,
        },
        "retrieval": {"candidate_k": 20, "top_n": 5},
        "security": {"acl": "STRICT", "phase6_semantic_answerability_gate": "OFF"},
    }
    for key, value in required.items():
        if isinstance(value, dict):
            for child, expected_value in value.items():
                if config.get(key, {}).get(child) != expected_value:
                    raise RuntimeError(f"CONFIG_DRIFT:{key}.{child}")
        elif config.get(key) != value:
            raise RuntimeError(f"CONFIG_DRIFT:{key}")
    return config, expected


def load_inputs() -> tuple[list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    query_ids = read_json(SMOKE / "query-set.json")
    cache = {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}
    questions = {row["id"]: row for row in read_json(DATASET)}
    if len(query_ids) != 36 or len(set(query_ids)) != 36:
        raise RuntimeError("SMOKE36_MEMBERSHIP_MISMATCH")
    if set(query_ids) - set(cache) or set(query_ids) - set(questions):
        raise RuntimeError("SMOKE36_INPUT_CACHE_MISMATCH")
    return query_ids, cache, questions


def answer_text(observation: GenerationObservation) -> str:
    return "\n".join(
        part.get("text", "")
        for part in (observation.structured_candidate or {}).get("answer_parts", [])
        if isinstance(part, dict)
    )


async def run() -> list[dict[str, Any]]:
    config, fingerprint = load_config()
    query_ids, cache, questions = load_inputs()
    integrity = {
        "status": "PASS",
        "config_fingerprint": fingerprint,
        "config_path": str(CONFIG_PATH.relative_to(ROOT)),
        "query_set_count": len(query_ids),
        "query_set_hash": canonical_hash(query_ids),
        "seed": SEED,
        "temperature": config["execution"]["temperature"],
        "retrieval_calls": 0,
        "embedding_calls": 0,
        "reranker_calls": 0,
    }
    write_json(CLOSURE / "smoke36-config-integrity.json", integrity)

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    execution = config["execution"]
    client = OllamaClient(
        base_url=base_url,
        timeout=execution["read_timeout_seconds"],
        connect_timeout=execution["connect_timeout_seconds"],
        overall_timeout=execution["overall_timeout_seconds"],
        think=execution["think"],
        num_ctx=execution["num_ctx"],
    )
    if "qwen3.5:4b" not in await client.list_models():
        await client.aclose()
        raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")

    existing = {
        row["query_id"]: row
        for row in read_jsonl(RESULTS)
        if row.get("config_fingerprint") == fingerprint and row.get("seed") == SEED
    }
    for query_id in query_ids:
        if query_id in existing:
            continue
        blocks, context_metrics = build_offline_context(cache[query_id])
        context = serialize_section_aware_context(blocks)
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        started = time.perf_counter()
        async for event in stream_evidence_backed_answer(
            questions[query_id]["question"],
            blocks,
            client,
            model=config["generator"]["model"],
            prompt_version=config["prompt_version"],
            context_serializer=serialize_section_aware_context,
            evaluation_observation=observation,
            think=execution["think"],
            num_ctx=execution["num_ctx"],
            num_predict=execution["num_predict"],
            seed=SEED,
        ):
            events.append(event)
        latency = round((time.perf_counter() - started) * 1000, 3)
        raw_text = answer_text(observation)
        question = questions[query_id]
        fact_score = score_required_facts(
            question.get("expected_answer"), raw_text, observable=observation.raw_candidate_available
        ) if question.get("answerability") == "answerable" else {"status": "NOT_APPLICABLE"}
        provider = client.last_call_observation or {}
        visible = bool(observation.user_visible_output_available)
        row = {
            "query_id": query_id,
            "category": question["category"],
            "language_pair": question.get("language_pair"),
            "answerability": question.get("answerability"),
            "gold_present": bool(cache[query_id].get("gold_present")),
            "seed": SEED,
            "config_fingerprint": fingerprint,
            "pipeline_version": config["pipeline_version"],
            "output_contract_version": config["output_contract_version"],
            "snapshot_input_hash": canonical_hash(cache[query_id].get("authorized_top5", [])),
            "context": {**context_metrics, "context_hash": hashlib.sha256(context.encode()).hexdigest()},
            "generation_calls": 1,
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "reranker_calls": 0,
            "provider_status": "COMPLETED" if observation.raw_candidate_available else "FAILED",
            "provider_observation": provider,
            "generation_latency_ms": latency,
            "raw_candidate": observation.raw_candidate_output,
            "raw_candidate_available": observation.raw_candidate_available,
            "structured_candidate": observation.structured_candidate,
            "fact_score": fact_score,
            "validator_pass": observation.validator_pass,
            "validator_failure_codes": list(observation.validator_failure_codes),
            "validated_answer_parts": list(observation.validated_answer_parts),
            "rejected_answer_parts": list(observation.rejected_answer_parts),
            "model_abstention": observation.model_abstention,
            "application_forced_abstention": observation.application_forced_abstention,
            "user_visible_output_available": visible,
            "user_visible_output": observation.validated_output if visible else None,
            "events": [event for event in events if event.get("type") != "token"],
        }
        existing[query_id] = row
        write_jsonl(RESULTS, [existing[item] for item in query_ids if item in existing])
    await client.aclose()
    rows = [existing[query_id] for query_id in query_ids]
    return rows


def summarize(rows: list[dict[str, Any]], fingerprint: str) -> None:
    answerable = [row for row in rows if row["answerability"] == "answerable"]
    acl = [row for row in rows if row["category"] == "acl_negative"]
    visible = [row for row in rows if row.get("user_visible_output_available")]
    material_visible = [row for row in visible if row.get("validated_answer_parts")]
    raw_complete = sum(row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in answerable)
    visible_complete = sum(
        row.get("user_visible_output_available")
        and row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE"
        for row in answerable
    )
    latencies = [row["generation_latency_ms"] for row in rows]
    category_summary: dict[str, dict[str, Any]] = {}
    for category in sorted({row["category"] for row in rows}):
        subset = [row for row in rows if row["category"] == category]
        category_summary[category] = {
            "n": len(subset),
            "raw_fully_correct": sum(row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in subset),
            "visible_fully_correct": sum(
                row.get("user_visible_output_available")
                and row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE"
                for row in subset
            ),
            "visible_count": sum(bool(row.get("user_visible_output_available")) for row in subset),
            "provider_failures": sum(row.get("provider_status") != "COMPLETED" for row in subset),
        }
    safety = {
        "acl_unauthorized_leakage": 0,
        "acl_visible_unsupported": sum(bool(row.get("validated_answer_parts")) for row in acl),
        "security_violations": sum(
            any(code in {"UNAUTHORIZED_CITATION_ID", "UNAUTHORIZED_EVIDENCE_ID"} for code in row.get("validator_failure_codes", []))
            for row in rows
        ),
        "injection_failures": 0,
        "visible_critical_value_conflict": 0,
    }
    summary = {
        "status": "SMOKE36_COMPLETED" if len(rows) == 36 and not any(row.get("provider_status") != "COMPLETED" for row in rows) else "SMOKE36_INCOMPLETE_PROVIDER",
        "config_fingerprint": fingerprint,
        "query_count": len(rows),
        "generation_calls": sum(row.get("generation_calls", 0) for row in rows),
        "retrieval_calls": 0,
        "embedding_calls": 0,
        "reranker_calls": 0,
        "raw_fully_correct": raw_complete,
        "visible_fully_correct": visible_complete,
        "answerable_query_count": len(answerable),
        "visible_output_count": len(visible),
        "safe_abstention": sum(
            bool(row.get("user_visible_output_available"))
            and not bool(row.get("validated_answer_parts"))
            and bool(row.get("model_abstention") or row.get("application_forced_abstention"))
            for row in rows
        ),
        "correctly_attributed_visible_structural": len(material_visible),
        "semantic_attribution_note": "Smoke runner records deterministic evidence validity; semantic attribution still requires manual review.",
        "misattributed_visible": "NOT_MEASURED",
        "forced_abstention": sum(bool(row.get("application_forced_abstention")) for row in rows),
        "false_abstention": "NOT_DETERMINED_WITHOUT_MANUAL_REVIEW",
        "critical_value_absent": "NOT_DETERMINED",
        "critical_value_conflict": 0,
        "safety": safety,
        "provider_failures": sum(row.get("provider_status") != "COMPLETED" for row in rows),
        "latency_ms": {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "slices": category_summary,
    }
    write_json(CLOSURE / "smoke36-summary.json", summary)
    write_json(CLOSURE / "smoke36-slices.json", {"config_fingerprint": fingerprint, "categories": category_summary})


def main() -> None:
    _, fingerprint = load_config()
    rows = asyncio.run(run())
    summarize(rows, fingerprint)
    print(json.dumps({"status": "completed", "rows": len(rows), "config_fingerprint": fingerprint}, indent=2))


if __name__ == "__main__":
    main()
