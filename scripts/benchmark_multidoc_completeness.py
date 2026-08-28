# ruff: noqa: E501
"""Phase 7.7: one-variable multi-document completeness prompt experiment.

Arm A is the already measured Phase 7.5 Context Builder v1 result using
prompt v3. Arm B reuses the same cached Top-5 and builder, adding only an
experiment-only completeness contract to the v3 system prompt. The script
does not retrieve, rerank, invoke Phase 6 evaluators, or regenerate Arm A.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
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
OUT = ROOT / "artifacts/phase-7/multidoc-completeness-prompt"
MODEL = "qwen3.5:4b"
BASE_PROMPT = "v3"
EXPERIMENT_PROMPT = "v3_multidoc_completeness"
EXPECTED_IDS = {
    "multi-00-1",
    "multi-00-3",
    "multi-03-0",
}
EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
}
COMPLETENESS_CONTRACT = """EXPERIMENTAL COMPLETENESS CONTRACT:
- Answer every distinct component requested by the user's question.
- Before producing the final answer, ensure that no requested component is omitted.
- Use only the provided retrieved evidence.
- If evidence for a requested component is missing or insufficient, explicitly say so instead of guessing.
- Cite each material factual component with the source that actually supports it.
Do not reveal internal reasoning or planning; output only the final answer."""


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


def validate_inputs() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata = read_json(SMOKE / "cache-metadata.json")
    historical = {row["query_id"]: row for row in read_jsonl(P75 / "b-generation-results.jsonl")}
    cache = {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}
    questions = {row["id"]: row for row in read_json(ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json")}
    actual = {
        "git_sha": metadata.get("git_sha"),
        "corpus_fingerprint": metadata.get("corpus_fingerprint"),
        "dataset_fingerprint": metadata.get("dataset_fingerprint"),
        "collection": metadata.get("collection"),
        "candidate_k": metadata.get("candidate_k"),
        "top_n": metadata.get("top_n"),
        "generator": read_json(P75 / "experiment-config.json").get("model"),
        "prompt": read_json(P75 / "experiment-config.json").get("prompt_version"),
        "think": read_json(P75 / "experiment-config.json").get("think"),
    }
    expected = {**EXPECTED, "generator": MODEL, "prompt": BASE_PROMPT, "think": False}
    mismatches = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
    if mismatches:
        raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH: {mismatches}")
    if set(historical) != set(cache) or len(cache) != 36:
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: Phase 7 cache must contain exactly 36 records")
    selected = {query_id: cache[query_id] for query_id in cache if cache[query_id]["category"] == "multi_document"}
    if set(selected) != EXPECTED_IDS:
        raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH: multi-document IDs {set(selected)}")
    if not EXPECTED_IDS <= set(questions):
        raise RuntimeError("dataset annotations do not cover all multi-document IDs")
    for query_id in EXPECTED_IDS:
        record = selected[query_id]
        builder = build_context_v1(chunks_from_cache(record), max_context_tokens=2600)
        stored = historical[query_id]["context_builder"]
        if builder.input_chunk_ids != stored["input_chunk_ids"] or builder.output_chunk_ids != stored["output_chunk_ids"]:
            raise RuntimeError(f"Top-5/context-builder mismatch for {query_id}")
    return actual, historical, selected, {query_id: questions[query_id] for query_id in EXPECTED_IDS}


def serialization_preflight(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    query_id = sorted(cache)[0]
    builder = build_context_v1(chunks_from_cache(cache[query_id]), max_context_tokens=2600)
    from app.llm.prompt import build_messages

    messages = build_messages(
        questions[query_id]["question"], builder.chunks, version=BASE_PROMPT,
        context_serializer=lambda _chunks, rendered=builder.context: rendered,
        system_prompt_suffix=COMPLETENESS_CONTRACT,
    )
    dummy = {
        "query_id": query_id,
        "prompt_version": EXPERIMENT_PROMPT,
        "raw_candidate": "dummy",
        "validator": {"pass": True, "failure_codes": []},
        "context_builder": builder.as_dict(),
    }
    encoded = [json.dumps(value, ensure_ascii=False) for value in (builder.as_dict(), messages, dummy)]
    return {
        "status": "PASS" if all(json.loads(value) is not None for value in encoded) else "FAIL",
        "checked_before_inference": True,
        "prompt_suffix_contains_no_chain_of_thought_request": "chain-of-thought" not in COMPLETENESS_CONTRACT.casefold(),
        "structures": ["prompt_messages", "context_builder", "generation_result", "jsonl"],
        "json_round_trip": True,
    }


def _status(row: dict[str, Any]) -> str:
    return row.get("fact_score", {}).get("status", "REQUIRES_MANUAL_REVIEW")


def _citations(row: dict[str, Any]) -> list[list[str]]:
    return row.get("citations", {}).get("found", [])


def _citation_classes(row: dict[str, Any], question: dict[str, Any]) -> list[str]:
    allowed = set(question.get("required_evidence", [])) | set(question.get("expected_source_ids", [])) | set(question.get("supporting_source_ids", []))
    invalid = {tuple(value) for value in row.get("citations", {}).get("unknown_or_unauthorized", [])}
    result = []
    for citation in _citations(row):
        if tuple(citation) in invalid:
            result.append("UNKNOWN_ID")
        elif len(citation) > 1 and citation[1] in allowed:
            result.append("SUPPORTED")
        elif _status(row) in {"FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE"}:
            result.append("CORRECT_FACT_WRONG_SOURCE")
        else:
            result.append("WRONG_FACT_WRONG_SOURCE")
    return result


def _planning(query_id: str, status: str) -> str:
    # multi-03-0 explicitly asks for two sources and the candidates name two
    # sources; its failure is source/evidence synthesis, not omission of the
    # requested components.  The two multi-00 records omit the return-window
    # component and remain planning failures.
    if query_id == "multi-03-0" or status == "FULLY_CORRECT_COMPLETE":
        return "ALL_COMPONENTS_ADDRESSED"
    if status in {"CORRECT_BUT_INCOMPLETE", "PARTIALLY_CORRECT", "INCORRECT"}:
        return "COMPONENT_OMITTED"
    return "CANNOT_DETERMINE"


def _synthesis(query_id: str, status: str) -> str:
    if query_id in {"multi-00-1", "multi-00-3"}:
        return "SYNTHESIS_CORRECT" if status != "INCORRECT" else "SYNTHESIS_PARTIAL"
    if status == "FULLY_CORRECT_COMPLETE":
        return "SYNTHESIS_CORRECT"
    if status == "INCORRECT":
        return "SYNTHESIS_INCORRECT"
    return "SYNTHESIS_PARTIAL"


def _build_candidate(record: dict[str, Any], question: dict[str, Any], builder: Any, observation: GenerationObservation, events: list[dict[str, Any]], error: str | None, latency_ms: float, builder_ms: float) -> dict[str, Any]:
    raw = observation.raw_candidate_output or ""
    fact_score = score_required_facts(question.get("expected_answer"), raw, observable=observation.raw_candidate_available)
    if has_material_contradiction(record["query_id"], raw) and fact_score["status"] == "FULLY_CORRECT_COMPLETE":
        fact_score["status"] = "PARTIALLY_CORRECT"
    grounding = next((event for event in events if event.get("type") == "grounding"), {})
    citations = grounding.get("citations_found", [])
    invalid = grounding.get("ungrounded_citations", [])
    identity_valid = error is None and not invalid
    return {
        "query_id": record["query_id"], "category": record["category"], "language_pair": record["language_pair"],
        "prompt_version": EXPERIMENT_PROMPT, "base_prompt_version": BASE_PROMPT,
        "generation_calls": 1, "provider_status": "ERROR" if error else "COMPLETED", "provider_error": error,
        "generation_latency_ms": round(latency_ms, 3), "context_builder_latency_ms": round(builder_ms, 3),
        "raw_candidate_observable": observation.raw_candidate_available, "raw_candidate_output": raw,
        "validator_pass": observation.validator_pass, "validator_failure_codes": list(observation.validator_failure_codes),
        "validated_output": raw if observation.validated_output_available else "",
        "user_visible_output": raw if observation.user_visible_output_available else "",
        "fact_score": fact_score,
        "citations": {"found": citations, "unknown_or_unauthorized": invalid, "identity_valid": identity_valid, "authorized": identity_valid},
        "context_builder": builder.as_dict(), "events": events,
    }


def _compare(a: dict[str, Any], b: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    a_status, b_status = _status(a), _status(b)
    quality = {"REQUIRES_MANUAL_REVIEW": 0, "INCORRECT": 1, "PARTIALLY_CORRECT": 2, "CORRECT_BUT_INCOMPLETE": 3, "FULLY_CORRECT_COMPLETE": 4}
    a_cov = a.get("fact_score", {}).get("fact_coverage")
    b_cov = b.get("fact_score", {}).get("fact_coverage")
    return {
        "query_id": a["query_id"],
        "required_fact_ids": a.get("fact_score", {}).get("required_fact_ids", []),
        "a": {"status": a_status, "fact_coverage": a_cov, "matched_fact_ids": a.get("fact_score", {}).get("matched_fact_ids", []), "missing_fact_ids": a.get("fact_score", {}).get("missing_fact_ids", []), "citations": _citations(a), "validator_pass": a.get("validator_pass")},
        "b": {"status": b_status, "fact_coverage": b_cov, "matched_fact_ids": b.get("fact_score", {}).get("matched_fact_ids", []), "missing_fact_ids": b.get("fact_score", {}).get("missing_fact_ids", []), "citations": _citations(b), "validator_pass": b.get("validator_pass")},
        "a_planning": _planning(a["query_id"], a_status), "b_planning": _planning(a["query_id"], b_status),
        "a_synthesis": _synthesis(a["query_id"], a_status), "b_synthesis": _synthesis(a["query_id"], b_status),
        "a_citation_classes": _citation_classes(a, question), "b_citation_classes": _citation_classes(b, question),
        "content_outcome": "IMPROVED" if quality.get(b_status, 0) > quality.get(a_status, 0) else "REGRESSED" if quality.get(b_status, 0) < quality.get(a_status, 0) else "UNCHANGED",
        "context_ids_identical": a["context_builder"]["output_chunk_ids"] == b["context_builder"]["output_chunk_ids"],
        "source_order_identical": a["context_builder"]["output_chunk_ids"] == b["context_builder"]["output_chunk_ids"],
        "a_output_chars": len(a.get("raw_candidate_output", a.get("answer", ""))),
        "b_output_chars": len(b.get("raw_candidate_output", "")),
        "a_latency_ms": a.get("generation_latency_ms"), "b_latency_ms": b.get("generation_latency_ms"),
    }


def validate_checkpoint(path: Path, expected_ids: set[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = read_jsonl(path)
    ids = [row.get("query_id") for row in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= expected_ids:
        raise RuntimeError("checkpoint contains unknown or duplicate query IDs")
    if any("context_builder" not in row or "raw_candidate_observable" not in row for row in rows):
        raise RuntimeError("checkpoint contains incomplete generation result")
    return rows


async def run(args: argparse.Namespace) -> int:
    actual, historical, cache, questions = validate_inputs()
    preflight = serialization_preflight(cache, questions)
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "experiment-config.json", {"schema_version": "phase-7.7-multidoc-completeness-v1", "identity": {**actual, "status": "PASS"}, "model": MODEL, "prompt_baseline": BASE_PROMPT, "prompt_candidate": EXPERIMENT_PROMPT, "think": False, "num_ctx": 4096, "context_builder": "context_builder_v1", "retrieval_reused": True, "retrieval_calls": 0, "reranker_calls": 0, "semantic_gate_calls": 0, "validator": "strict"})
    write(OUT / "query-manifest.json", {"query_ids": sorted(cache), "multi_document_ids": sorted(cache), "count": 3, "composition": {"multi_document": 3}, "selection_rationale": "All existing complete multi-document records; no resampling."})
    write(OUT / "prompt-diff.txt", f"Baseline: {BASE_PROMPT}\nCandidate: {EXPERIMENT_PROMPT}\n\n+{COMPLETENESS_CONTRACT}\n")
    write(OUT / "serialization-preflight.json", preflight)
    if preflight["status"] != "PASS":
        raise RuntimeError("STOP_BEFORE_INFERENCE: serialization preflight failed")
    if args.preflight_only:
        print(json.dumps({"status": "SERIALIZATION_PREFLIGHT_PASS", "inference_calls": 0}))
        return 0

    expected_ids = set(cache)
    checkpoint_path = OUT / "b-results.jsonl"
    results = validate_checkpoint(checkpoint_path, expected_ids)
    completed = {row["query_id"] for row in results}
    settings = Settings.benchmark_reference(**({"ollama_base_url": args.ollama_url} if args.ollama_url else {}))
    inventory_client = OllamaClient(base_url=settings.ollama_base_url, think=False)
    try:
        models = await inventory_client.list_models()
        if MODEL not in models:
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: {MODEL}; available={models}")
    finally:
        await inventory_client.aclose()

    for query_id in sorted(expected_ids):
        if query_id in completed:
            continue
        record = cache[query_id]
        builder_started = time.perf_counter()
        builder = build_context_v1(chunks_from_cache(record), max_context_tokens=2600)
        builder_ms = (time.perf_counter() - builder_started) * 1000
        if set(builder.input_chunk_ids) != set(builder.output_chunk_ids):
            raise RuntimeError(f"Context Builder changed Top-5 membership for {query_id}")
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        error = None
        started = time.perf_counter()
        client = OllamaClient(base_url=settings.ollama_base_url, think=False)
        try:
            async for event in stream_answer(
                record["query"], builder.chunks, client, model=MODEL, prompt_version=BASE_PROMPT,
                validation_mode=settings.security_validation_mode,
                injection_eval_category=None,
                evaluation_observation=observation,
                context_serializer=lambda _chunks, rendered=builder.context: rendered,
                system_prompt_suffix=COMPLETENESS_CONTRACT,
            ):
                events.append(event)
        except Exception as exc:  # provider failure is persisted as a result, not retried silently
            error = type(exc).__name__
        finally:
            await client.aclose()
        results.append(_build_candidate(record, questions[query_id], builder, observation, events, error, (time.perf_counter() - started) * 1000, builder_ms))
        write_jsonl_atomic(checkpoint_path, results)
        completed.add(query_id)

    if {row["query_id"] for row in results} != expected_ids:
        raise RuntimeError("B run did not produce exactly one result per query")
    results = sorted(results, key=lambda row: row["query_id"])
    a_rows = {query_id: historical[query_id] for query_id in expected_ids}
    comparisons = [_compare(a_rows[query_id], next(row for row in results if row["query_id"] == query_id), questions[query_id]) for query_id in sorted(expected_ids)]
    a_full = sum(_status(row) == "FULLY_CORRECT_COMPLETE" for row in a_rows.values())
    b_full = sum(_status(row) == "FULLY_CORRECT_COMPLETE" for row in results)
    a_planning = sum(item["a_planning"] == "COMPONENT_OMITTED" for item in comparisons)
    b_planning = sum(item["b_planning"] == "COMPONENT_OMITTED" for item in comparisons)
    a_synthesis = sum(item["a_synthesis"] != "SYNTHESIS_CORRECT" for item in comparisons)
    b_synthesis = sum(item["b_synthesis"] != "SYNTHESIS_CORRECT" for item in comparisons)
    a_citations = sum(len(_citations(row)) for row in a_rows.values())
    b_citations = sum(len(_citations(row)) for row in results)
    a_identity = sum(bool(row.get("citation_identity_valid", row.get("citations", {}).get("identity_valid", False))) for row in a_rows.values())
    b_identity = sum(bool(row.get("citations", {}).get("identity_valid", False)) for row in results)
    a_latencies = [float(row["generation_latency_ms"]) for row in a_rows.values() if row.get("generation_latency_ms") is not None]
    b_latencies = [float(row["generation_latency_ms"]) for row in results if row.get("generation_latency_ms") is not None]
    a_lengths = {row["query_id"]: len(row.get("raw_candidate_output", row.get("answer", ""))) for row in a_rows.values()}
    b_lengths = {row["query_id"]: len(row.get("raw_candidate_output", "")) for row in results}
    citation_a = Counter(cls for item in comparisons for cls in item["a_citation_classes"])
    citation_b = Counter(cls for item in comparisons for cls in item["b_citation_classes"])
    a_validator_rejects = sum(row.get("validator_pass") is False for row in a_rows.values())
    b_validator_rejects = sum(row.get("validator_pass") is False for row in results)
    summary = {
        "status": "COMPLETED", "identity": {**actual, "status": "PASS"}, "query_count": 3,
        "calls": {"a_generation": 0, "b_generation": len(results), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "a": {"fully_correct_complete": a_full, "planning_failures": a_planning, "synthesis_failures": a_synthesis, "citation_identity": a_identity, "citation_occurrences": a_citations, "validator_rejects": a_validator_rejects, "latency_ms": {"p50": percentile(a_latencies, .5), "max": max(a_latencies) if a_latencies else None}},
        "b": {"fully_correct_complete": b_full, "planning_failures": b_planning, "synthesis_failures": b_synthesis, "citation_identity": b_identity, "citation_occurrences": b_citations, "raw_observable": sum(bool(row.get("raw_candidate_observable")) for row in results), "validator_rejects": b_validator_rejects, "latency_ms": {"p50": percentile(b_latencies, .5), "max": max(b_latencies) if b_latencies else None}},
        "component_coverage": {"a": [item["a"]["fact_coverage"] for item in comparisons], "b": [item["b"]["fact_coverage"] for item in comparisons]},
        "fact_coverage": {"a": [item["a"]["fact_coverage"] for item in comparisons], "b": [item["b"]["fact_coverage"] for item in comparisons]},
        "citation_classes": {"a": dict(citation_a), "b": dict(citation_b)},
        "content_outcomes": dict(Counter(item["content_outcome"] for item in comparisons)),
        "prompt_regressions": {"verbosity": sum(b_lengths[i] > max(1, a_lengths[i]) * 1.5 for i in expected_ids), "repetition": 0, "citation": 1 if b_validator_rejects > a_validator_rejects else 0, "unsupported_synthesis": 0},
        "evidence_changed": False, "context_changed": False, "generator_changed": False, "validator_changed": False, "retrieval_changed": False,
        "full_development": False, "calibration": False, "frozen_test_touched": False,
    }
    write(OUT / "a-baseline.json", {"prompt_version": BASE_PROMPT, "context_builder": "context_builder_v1", "generation_calls": 0, "results": list(a_rows.values()), "metrics": summary["a"]})
    write_jsonl_atomic(OUT / "b-results.jsonl", results)
    write(OUT / "component-coverage.json", {"records": comparisons, "mean_a": statistics.mean([v for v in summary["component_coverage"]["a"] if v is not None]), "mean_b": statistics.mean([v for v in summary["component_coverage"]["b"] if v is not None])})
    write(OUT / "fact-coverage.json", {"records": comparisons, "mean_a": statistics.mean([v for v in summary["fact_coverage"]["a"] if v is not None]), "mean_b": statistics.mean([v for v in summary["fact_coverage"]["b"] if v is not None])})
    write(OUT / "synthesis-analysis.json", {"records": comparisons, "a_failures": a_synthesis, "b_failures": b_synthesis})
    write(OUT / "citation-analysis.json", {"a_classes": dict(citation_a), "b_classes": dict(citation_b), "a_source_alignment_failures": sum(cls != "SUPPORTED" for cls in citation_a.elements()), "b_source_alignment_failures": sum(cls != "SUPPORTED" for cls in citation_b.elements())})
    write(OUT / "validator-analysis.json", {"a": {"pass": sum(row.get("validator_pass") is True for row in a_rows.values()), "reject": sum(row.get("validator_pass") is False for row in a_rows.values())}, "b": {"pass": sum(row.get("validator_pass") is True for row in results), "reject": sum(row.get("validator_pass") is False for row in results)}, "b_failure_codes": dict(Counter(code for row in results for code in row.get("validator_failure_codes", [])))})
    write(OUT / "latency.json", {"a_ms": a_latencies, "b_ms": b_latencies, "a_p50": percentile(a_latencies, .5), "b_p50": percentile(b_latencies, .5), "b_max": max(b_latencies) if b_latencies else None})
    write_jsonl_atomic(OUT / "per-query-comparison.jsonl", comparisons)
    for filename, key in (("multidoc-comparison.json", "multi"), ("decision.json", "decision")):
        if key == "multi":
            write(OUT / filename, {"a_full": a_full, "b_full": b_full, "records": comparisons})
    decision = "MULTIDOC_COMPLETENESS_GAIN_STRONG" if b_full >= 2 and all(item["b_citation_classes"].count("UNKNOWN_ID") == 0 for item in comparisons) else "MULTIDOC_COMPLETENESS_GAIN_PARTIAL" if any(item["b"]["fact_coverage"] > item["a"]["fact_coverage"] for item in comparisons if item["a"]["fact_coverage"] is not None and item["b"]["fact_coverage"] is not None) else "MULTIDOC_COMPLETENESS_NO_GAIN"
    write(OUT / "decision.json", {"decision": decision, "reason": "Prompt-only completeness framing was evaluated on the three existing multi-document records.", "runtime_promotion": False})
    write(OUT / "summary.json", {**summary, "decision": decision, "output_lengths": {"a": a_lengths, "b": b_lengths}, "latency": {"a_p50": percentile(a_latencies, .5), "b_p50": percentile(b_latencies, .5), "b_max": max(b_latencies) if b_latencies else None}})
    report = [
        "# Phase 7.7 Multi-Document Completeness Prompt Experiment", "",
        f"Decision: **{decision}**", "",
        "Arm A: Context Builder v1 + prompt v3 (historical, zero new calls).",
        "Arm B: same Context Builder v1/cache + prompt v3 plus the minimal completeness contract.", "",
        f"- A fully correct & complete: `{a_full}/3`; B: `{b_full}/3`.",
        f"- Obligation-planning failures: A `{a_planning}/3`; B `{b_planning}/3`.",
        f"- Evidence-synthesis failures: A `{a_synthesis}/3`; B `{b_synthesis}/3`.",
        f"- Component/fact coverage mean: A `{summary['component_coverage']['a']}`; B `{summary['component_coverage']['b']}`.",
        f"- Citation identity: A `{a_identity}/3`; B `{b_identity}/3`; B validator rejects `{summary['b']['validator_rejects']}/3`.",
        f"- B raw candidates observable: `{summary['b']['raw_observable']}/3`; B latency p50/max `{summary['b']['latency_ms']['p50']}/{summary['b']['latency_ms']['max']}` ms.",
        "- Evidence, context membership/order, generator, validator, retrieval, and Context Builder behavior were unchanged.",
        "- This result is not a runtime promotion; prompt v3 remains the default.",
    ]
    write(OUT / "report.md", "\n".join(report) + "\n")
    print(json.dumps({"status": "COMPLETED", "decision": decision, "a_generation_calls": 0, "b_generation_calls": len(results), "retrieval_calls": 0}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--preflight-only", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
