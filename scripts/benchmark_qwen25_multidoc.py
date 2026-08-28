# ruff: noqa: E501
"""Phase 7.8: qwen3.5:4b versus qwen2.5:7b-instruct capacity probe.

Only the generator model changes.  The three cached multi-document contexts,
Context Builder v1 serialization, prompt v3, validator, and refined scorer are
held fixed.  Arm A is reused from the Phase 7.5/7.7 artifacts; only Arm B
calls the local provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.context_builder import build_context_v1
from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import has_material_contradiction, score_required_facts
from app.llm.generate import stream_answer
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
P75 = ROOT / "artifacts/phase-7/context-builder-full-validation"
P77 = ROOT / "artifacts/phase-7/multidoc-completeness-prompt"
OUT = ROOT / "artifacts/phase-7/qwen25-7b-multidoc-probe"
MODEL_4B = "qwen3.5:4b"
MODEL_7B = "qwen2.5:7b-instruct"
PROMPT = "v3"
IDS = {"multi-00-1", "multi-00-3", "multi-03-0"}
ORDERED_IDS = ("multi-00-1", "multi-00-3", "multi-03-0")
EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))], 3)


def serving_state() -> dict[str, Any]:
    try:
        completed = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=False, timeout=10)
        return {"available": completed.returncode == 0, "raw": completed.stdout.strip(), "stderr": completed.stderr.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "raw": "", "stderr": type(exc).__name__}


def validate_inputs() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata = read_json(SMOKE / "cache-metadata.json")
    p75_config = read_json(P75 / "experiment-config.json")
    cache = {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}
    baseline = {row["query_id"]: row for row in read_jsonl(P75 / "b-generation-results.jsonl")}
    questions_all = {row["id"]: row for row in read_json(ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json")}
    actual = {**{key: metadata.get(key) for key in EXPECTED}, "generator": p75_config.get("model"), "prompt": p75_config.get("prompt_version"), "think": p75_config.get("think")}
    expected = {**EXPECTED, "generator": MODEL_4B, "prompt": PROMPT, "think": False}
    mismatch = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
    if mismatch:
        raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH: {mismatch}")
    if len(cache) != 36 or len(baseline) != 36 or set(cache) != set(baseline):
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: expected matching 36-query cache and 4B baseline")
    if {query_id for query_id, row in cache.items() if row["category"] == "multi_document"} != IDS:
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: canonical multi-document IDs differ")
    if not IDS <= set(questions_all):
        raise RuntimeError("dataset annotations do not cover the three multi-document queries")
    for query_id in IDS:
        builder = build_context_v1(chunks_from_cache(cache[query_id]), max_context_tokens=2600)
        stored = baseline[query_id]["context_builder"]
        if builder.input_chunk_ids != stored["input_chunk_ids"] or builder.output_chunk_ids != stored["output_chunk_ids"]:
            raise RuntimeError(f"context identity mismatch for {query_id}")
    return actual, baseline, {query_id: cache[query_id] for query_id in IDS}, {query_id: questions_all[query_id] for query_id in IDS}


def preflight(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from app.llm.prompt import build_messages

    query_id = sorted(cache)[0]
    builder = build_context_v1(chunks_from_cache(cache[query_id]), max_context_tokens=2600)
    messages = build_messages(questions[query_id]["question"], builder.chunks, version=PROMPT, context_serializer=lambda _chunks, rendered=builder.context: rendered)
    dummy = {"query_id": query_id, "model": MODEL_7B, "prompt": PROMPT, "raw_candidate": "dummy", "context_builder": builder.as_dict()}
    values = [builder.as_dict(), messages, dummy]
    encoded = [json.dumps(value, ensure_ascii=False) for value in values]
    return {"status": "PASS" if all(json.loads(value) is not None for value in encoded) else "FAIL", "checked_before_inference": True, "json_round_trip": True, "structures": ["prompt_messages", "context_builder", "generation_result", "checkpoint"]}


def status(row: dict[str, Any]) -> str:
    return row.get("fact_score", {}).get("status", "REQUIRES_MANUAL_REVIEW")


def citations(row: dict[str, Any]) -> list[list[str]]:
    return row.get("citations", {}).get("found", [])


def citation_classes(row: dict[str, Any], question: dict[str, Any]) -> list[str]:
    allowed = set(question.get("required_evidence", [])) | set(question.get("expected_source_ids", [])) | set(question.get("supporting_source_ids", []))
    invalid = {tuple(value) for value in row.get("citations", {}).get("unknown_or_unauthorized", [])}
    result = []
    for citation in citations(row):
        if tuple(citation) in invalid:
            result.append("UNKNOWN_ID")
        elif len(citation) > 1 and citation[1] in allowed:
            result.append("SUPPORTED")
        elif status(row) in {"FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE"}:
            result.append("CORRECT_FACT_WRONG_SOURCE")
        else:
            result.append("WRONG_FACT_WRONG_SOURCE")
    return result


def make_result(record: dict[str, Any], question: dict[str, Any], builder: Any, observation: GenerationObservation, events: list[dict[str, Any]], error: str | None, latency_ms: float, builder_ms: float) -> dict[str, Any]:
    raw = observation.raw_candidate_output or ""
    fact_score = score_required_facts(question.get("expected_answer"), raw, observable=observation.raw_candidate_available)
    if has_material_contradiction(record["query_id"], raw) and fact_score["status"] == "FULLY_CORRECT_COMPLETE":
        fact_score["status"] = "PARTIALLY_CORRECT"
    grounding = next((event for event in events if event.get("type") == "grounding"), {})
    found = grounding.get("citations_found", [])
    invalid = grounding.get("ungrounded_citations", [])
    return {
        "query_id": record["query_id"], "category": record["category"], "language_pair": record["language_pair"], "model": MODEL_7B, "prompt": PROMPT, "think": False,
        "generation_calls": 1, "provider_status": "ERROR" if error else "COMPLETED", "provider_error": error, "generation_latency_ms": round(latency_ms, 3), "context_builder_latency_ms": round(builder_ms, 3),
        "raw_candidate_observable": observation.raw_candidate_available, "raw_candidate_output": raw, "validator_pass": observation.validator_pass, "validator_failure_codes": list(observation.validator_failure_codes),
        "validated_output": raw if observation.validated_output_available else "", "user_visible_output": raw if observation.user_visible_output_available else "", "fact_score": fact_score,
        "citations": {"found": found, "unknown_or_unauthorized": invalid, "identity_valid": error is None and not invalid, "authorized": error is None and not invalid}, "context_builder": builder.as_dict(), "events": events,
    }


def compare(query_id: str, a: dict[str, Any], b: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    a_status, b_status = status(a), status(b)
    quality = {"REQUIRES_MANUAL_REVIEW": 0, "INCORRECT": 1, "PARTIALLY_CORRECT": 2, "CORRECT_BUT_INCOMPLETE": 3, "FULLY_CORRECT_COMPLETE": 4}
    return {
        "query_id": query_id, "required_fact_ids": a.get("fact_score", {}).get("required_fact_ids", []),
        "a": {"model": MODEL_4B, "status": a_status, "fact_coverage": a.get("fact_score", {}).get("fact_coverage"), "matched_fact_ids": a.get("fact_score", {}).get("matched_fact_ids", []), "missing_fact_ids": a.get("fact_score", {}).get("missing_fact_ids", []), "citations": citations(a), "validator_pass": a.get("validator_pass")},
        "b": {"model": MODEL_7B, "status": b_status, "fact_coverage": b.get("fact_score", {}).get("fact_coverage"), "matched_fact_ids": b.get("fact_score", {}).get("matched_fact_ids", []), "missing_fact_ids": b.get("fact_score", {}).get("missing_fact_ids", []), "citations": citations(b), "validator_pass": b.get("validator_pass")},
        "a_citation_classes": citation_classes(a, question), "b_citation_classes": citation_classes(b, question),
        "content_outcome": "IMPROVED" if quality.get(b_status, 0) > quality.get(a_status, 0) else "REGRESSED" if quality.get(b_status, 0) < quality.get(a_status, 0) else "UNCHANGED",
        "same_context_ids": a["context_builder"]["output_chunk_ids"] == b["context_builder"]["output_chunk_ids"], "same_context_order": a["context_builder"]["output_chunk_ids"] == b["context_builder"]["output_chunk_ids"], "same_context_serialization": a["context_builder"] == b["context_builder"],
        "a_output_chars": len(a.get("raw_candidate_output", a.get("answer", ""))), "b_output_chars": len(b.get("raw_candidate_output", "")), "a_latency_ms": a.get("generation_latency_ms"), "b_latency_ms": b.get("generation_latency_ms"),
    }


def load_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = read_jsonl(path)
    ids = [row.get("query_id") for row in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= IDS or any("context_builder" not in row for row in rows):
        raise RuntimeError("invalid or duplicate checkpoint")
    return rows


async def run(args: argparse.Namespace) -> int:
    actual, baseline, cache, questions = validate_inputs()
    check = preflight(cache, questions)
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "experiment-config.json", {"schema_version": "phase-7.8-qwen25-multidoc-v1", "identity": {**actual, "status": "PASS"}, "baseline_model": MODEL_4B, "challenger_model": MODEL_7B, "prompt": PROMPT, "think": False, "num_ctx": 4096, "context_builder": "context_builder_v1", "validator": "strict", "retrieval_reused": True, "retrieval_calls": 0, "reranker_calls": 0, "semantic_gate_calls": 0})
    write(OUT / "query-manifest.json", {"query_ids": sorted(IDS), "count": 3, "composition": {"multi_document": 3}, "selection_rationale": "All canonical complete multi-document records; no resampling."})
    write(OUT / "model-serving-state.json", {"before_inference": serving_state(), "required_model": MODEL_7B, "inventory_verified": False})
    write(OUT / "serialization-preflight.json", check)
    if check["status"] != "PASS":
        raise RuntimeError("STOP_BEFORE_INFERENCE: serialization preflight failed")
    if args.preflight_only:
        print(json.dumps({"status": "SERIALIZATION_PREFLIGHT_PASS", "inference_calls": 0}))
        return 0
    settings = Settings.benchmark_reference(**({"ollama_base_url": args.ollama_url} if args.ollama_url else {}))
    inventory = OllamaClient(base_url=settings.ollama_base_url, think=False)
    try:
        models = await inventory.list_models()
        if MODEL_7B not in models:
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: {MODEL_7B}; available={models}")
    finally:
        await inventory.aclose()
    checkpoint_path = OUT / "qwen25-7b-results.jsonl"
    results = load_checkpoint(checkpoint_path)
    completed = {row["query_id"] for row in results}
    for query_id in sorted(IDS):
        if query_id in completed:
            continue
        record = cache[query_id]
        started_builder = time.perf_counter()
        builder = build_context_v1(chunks_from_cache(record), max_context_tokens=2600)
        builder_ms = (time.perf_counter() - started_builder) * 1000
        if set(builder.input_chunk_ids) != set(builder.output_chunk_ids):
            raise RuntimeError(f"Context Builder changed Top-5 membership for {query_id}")
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        error = None
        started = time.perf_counter()
        client = OllamaClient(base_url=settings.ollama_base_url, think=False)
        try:
            async for event in stream_answer(record["query"], builder.chunks, client, model=MODEL_7B, prompt_version=PROMPT, validation_mode=settings.security_validation_mode, evaluation_observation=observation, context_serializer=lambda _chunks, rendered=builder.context: rendered):
                events.append(event)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            await client.aclose()
        results.append(make_result(record, questions[query_id], builder, observation, events, error, (time.perf_counter() - started) * 1000, builder_ms))
        write_jsonl_atomic(checkpoint_path, results)
        completed.add(query_id)
    if {row["query_id"] for row in results} != IDS:
        raise RuntimeError("7B run did not produce exactly three results")
    results = sorted(results, key=lambda row: row["query_id"])
    a_rows = {query_id: baseline[query_id] for query_id in IDS}
    b_rows = {row["query_id"]: row for row in results}
    comparisons = [compare(query_id, a_rows[query_id], b_rows[query_id], questions[query_id]) for query_id in sorted(IDS)]
    a_full = sum(status(a_rows[query_id]) == "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    b_full = sum(status(b_rows[query_id]) == "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    a_cov = [a_rows[query_id]["fact_score"].get("fact_coverage") for query_id in ORDERED_IDS]
    b_cov = [b_rows[query_id]["fact_score"].get("fact_coverage") for query_id in ORDERED_IDS]
    a_lat = [float(a_rows[query_id]["generation_latency_ms"]) for query_id in ORDERED_IDS]
    b_lat = [float(b_rows[query_id]["generation_latency_ms"]) for query_id in ORDERED_IDS]
    planning_ids = {"multi-00-1", "multi-00-3"}
    a_planning_failures = sum(query_id in planning_ids and status(a_rows[query_id]) != "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    b_planning_failures = sum(query_id in planning_ids and status(b_rows[query_id]) != "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    a_synthesis_failures = sum(query_id == "multi-03-0" and status(a_rows[query_id]) != "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    b_synthesis_failures = sum(query_id == "multi-03-0" and status(b_rows[query_id]) != "FULLY_CORRECT_COMPLETE" for query_id in ORDERED_IDS)
    a_classes = Counter(cls for item in comparisons for cls in item["a_citation_classes"])
    b_classes = Counter(cls for item in comparisons for cls in item["b_citation_classes"])
    decision = "QWEN25_7B_SYNTHESIS_GAIN_STRONG" if b_full >= 2 else "QWEN25_7B_SYNTHESIS_GAIN_PARTIAL" if any((item["b"]["fact_coverage"] or 0) > (item["a"]["fact_coverage"] or 0) for item in comparisons) else "QWEN25_7B_NO_MEANINGFUL_GAIN"
    summary = {"status": "COMPLETED", "decision": decision, "identity": {**actual, "status": "PASS"}, "calls": {"4b_generation": 0, "7b_generation": 3, "retrieval": 0, "reranker": 0, "embedding": 0, "semantic_evaluator": 0}, "same_context": all(item["same_context_ids"] and item["same_context_order"] and item["same_context_serialization"] for item in comparisons), "a": {"fully_correct_complete": a_full, "component_coverage": a_cov, "fact_coverage": a_cov, "planning_failures": a_planning_failures, "synthesis_failures": a_synthesis_failures, "citation_identity": sum(bool(a_rows[query_id].get("citations", {}).get("identity_valid", False)) for query_id in ORDERED_IDS), "validator_pass": sum(a_rows[query_id].get("validator_pass") is True for query_id in ORDERED_IDS), "validator_reject": sum(a_rows[query_id].get("validator_pass") is False for query_id in ORDERED_IDS), "citation_classes": dict(a_classes), "latency_ms": {"p50": percentile(a_lat, .5), "max": max(a_lat)}}, "b": {"fully_correct_complete": b_full, "component_coverage": b_cov, "fact_coverage": b_cov, "planning_failures": b_planning_failures, "synthesis_failures": b_synthesis_failures, "citation_identity": sum(bool(b_rows[query_id].get("citations", {}).get("identity_valid", False)) for query_id in ORDERED_IDS), "validator_pass": sum(b_rows[query_id].get("validator_pass") is True for query_id in ORDERED_IDS), "validator_reject": sum(b_rows[query_id].get("validator_pass") is False for query_id in ORDERED_IDS), "raw_observable": sum(bool(b_rows[query_id].get("raw_candidate_observable")) for query_id in ORDERED_IDS), "citation_classes": dict(b_classes), "latency_ms": {"p50": percentile(b_lat, .5), "max": max(b_lat)}}, "content_outcomes": dict(Counter(item["content_outcome"] for item in comparisons)), "output_length_ratio": [item["b_output_chars"] / item["a_output_chars"] if item["a_output_chars"] else None for item in comparisons], "full_development": False, "calibration": False, "frozen_test_touched": False}
    write(OUT / "model-serving-state.json", {"before_inference": read_json(OUT / "model-serving-state.json")["before_inference"], "after_inference": serving_state(), "required_model": MODEL_7B, "inventory_verified": True})
    write(OUT / "qwen35-4b-baseline.json", {"model": MODEL_4B, "prompt": PROMPT, "generation_calls": 0, "results": list(a_rows.values()), "metrics": summary["a"]})
    write_jsonl_atomic(OUT / "qwen25-7b-results.jsonl", results)
    write(OUT / "component-comparison.json", {"records": comparisons, "a_full": a_full, "b_full": b_full, "a_mean": sum(a_cov) / len(a_cov), "b_mean": sum(b_cov) / len(b_cov)})
    write(OUT / "fact-comparison.json", {"records": comparisons, "a": a_cov, "b": b_cov})
    write(OUT / "synthesis-comparison.json", {"records": comparisons, "a_planning_failures": a_planning_failures, "b_planning_failures": b_planning_failures, "a_synthesis_failures": a_synthesis_failures, "b_synthesis_failures": b_synthesis_failures})
    write(OUT / "citation-comparison.json", {"a_classes": dict(a_classes), "b_classes": dict(b_classes), "a_identity": summary["a"]["citation_identity"], "b_identity": summary["b"]["citation_identity"]})
    write(OUT / "validator-comparison.json", {"a": {"pass": summary["a"]["validator_pass"], "reject": summary["a"]["validator_reject"]}, "b": {"pass": summary["b"]["validator_pass"], "reject": summary["b"]["validator_reject"]}, "b_failure_codes": dict(Counter(code for row in b_rows.values() for code in row.get("validator_failure_codes", [])))})
    write(OUT / "latency-comparison.json", {"a_ms": a_lat, "b_ms": b_lat, "a_p50": percentile(a_lat, .5), "b_p50": percentile(b_lat, .5), "a_max": max(a_lat), "b_max": max(b_lat), "ratios": [item["b_latency_ms"] / item["a_latency_ms"] for item in comparisons]})
    write_jsonl_atomic(OUT / "per-query-comparison.jsonl", comparisons)
    write(OUT / "decision.json", {"decision": decision, "runtime_default_changed": False, "reason": "Three-query generator-only capacity comparison with identical cached contexts and prompt v3."})
    write(OUT / "summary.json", summary)
    write(OUT / "report.md", f"""# Phase 7.8 qwen3.5:4b vs qwen2.5:7b-instruct

Decision: **{decision}**

Arm A reused the Phase 7.5/7.7 Context Builder v1 result with qwen3.5:4b and
prompt v3. Arm B generated exactly the same three cached contexts with
qwen2.5:7b-instruct and prompt v3. No retrieval, reranking, embedding, or
Phase 6 call was made.

- Fully correct and complete: 4B `{a_full}/3`; 7B `{b_full}/3`.
- Fact coverage (ordered as multi-00-1, multi-00-3, multi-03-0): 4B `{a_cov}`; 7B `{b_cov}`.
- Obligation-planning failures: 4B `{a_planning_failures}/3`; 7B `{b_planning_failures}/3`.
- Evidence-synthesis failures: 4B `{a_synthesis_failures}/3`; 7B `{b_synthesis_failures}/3`.
- Validator: 4B `{summary['a']['validator_pass']} pass / {summary['a']['validator_reject']} reject`; 7B `{summary['b']['validator_pass']} pass / {summary['b']['validator_reject']} reject`.
- Raw B candidates observable: `{summary['b']['raw_observable']}/3`.
- Generation latency p50/max: 4B `{summary['a']['latency_ms']['p50']}/{summary['a']['latency_ms']['max']}` ms; 7B `{summary['b']['latency_ms']['p50']}/{summary['b']['latency_ms']['max']}` ms.
- Context IDs/order identical: `{summary['same_context']}`. Runtime default remains qwen3.5:4b.
""")
    print(json.dumps({"status": "COMPLETED", "decision": decision, "four_b_calls": 0, "seven_b_calls": 3, "retrieval_calls": 0}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--preflight-only", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
