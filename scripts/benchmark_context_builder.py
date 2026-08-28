# ruff: noqa: E501
"""Phase 7.4 cache-only Context Builder v1 A/B probe.

Arm A is read from the historical qwen3.5:4b Phase 7 output.  Arm B sends
only the fixed 12-record selection through the real generation path after a
deterministic context presentation step.  This module intentionally imports
no retrieval, embedding, reranker, or semantic-evaluator client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.context_builder import build_context_v1
from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import (
    has_material_contradiction,
    score_required_facts,
    validator_failure_codes,
)
from app.llm.generate import stream_answer
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.llm.trust_boundary import serialize_untrusted_context
from app.shared.config import Settings
from scripts.benchmark_model_capacity import EXPECTED_CACHE, SELECTION, validate_probe_cache

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/phase-7/context-builder-probe"
MODEL = "qwen3.5:4b"
PROMPT = "v3"
MAX_CONTEXT_TOKENS = 2600


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _tokens(value: str) -> int:
    return max(1, len(value.split()))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))], 3)


def _cache() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    metadata, historical, cache_rows, questions = validate_probe_cache()
    selected_ids = [item[0] for item in SELECTION]
    if len(selected_ids) != 12 or len(set(selected_ids)) != 12:
        raise ValueError("Context Builder probe must contain exactly 12 unique IDs")
    cache = {row["query_id"]: row for row in cache_rows}
    if not set(selected_ids) <= set(cache):
        raise ValueError("Context Builder selection is outside the locked retrieval cache")
    if metadata.get("generation_model") != MODEL:
        raise ValueError("historical cache generation metadata unexpectedly changed")
    return metadata, historical, cache, questions


def selection_artifact(metadata: dict[str, Any], historical: list[dict[str, Any]], questions: dict[str, Any]) -> dict[str, Any]:
    historical_by_id = {row["query_id"]: row for row in historical}
    records = []
    for query_id, category, rationale in SELECTION:
        row = historical_by_id[query_id]
        records.append({
            "query_id": query_id,
            "category": category,
            "language_pair": questions[query_id]["language_pair"],
            "gold_present": row["gold_present"],
            "all_required_present": row["all_required_present"],
            "rationale": rationale,
        })
    return {
        "schema_version": "phase-7.4-context-builder-selection-v1",
        "probe_count": 12,
        "query_ids": [item["query_id"] for item in records],
        "composition": dict(Counter(item["category"] for item in records)),
        "identity": {key: metadata.get(key) for key in EXPECTED_CACHE},
        "fixed": {
            "model": MODEL,
            "prompt_version": PROMPT,
            "think": False,
            "candidate_k": 20,
            "top_n": 5,
            "retrieval_reused": True,
            "validator": "strict",
        },
        "records": records,
    }


def _old_refined() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(ROOT / "artifacts/phase-7/evaluator-refinement/rescored-results.jsonl")
    return {row["query_id"]: row for row in rows}


def _baseline_row(
    historical: dict[str, Any],
    cache_row: dict[str, Any],
    question: dict[str, Any],
    refined: dict[str, Any],
) -> dict[str, Any]:
    chunks = chunks_from_cache(cache_row)
    context = serialize_untrusted_context(chunks)
    citations = refined.get("citation_rows", [])
    source_alignment = sum(item.get("support_status") == "RELATED_BUT_INSUFFICIENT" for item in citations)
    return {
        "query_id": historical["query_id"],
        "category": historical["category"],
        "language_pair": historical["language_pair"],
        "answerability": historical["answerability"],
        "gold_present": historical["gold_present"],
        "all_required_present": historical["all_required_present"],
        "generation_calls": 0,
        "raw_candidate_observable": refined.get("raw_candidate_observable", False),
        "answer": historical.get("answer", ""),
        "fact_score": refined["fact_score"],
        "validator_pass": historical.get("output_validation", {}).get("passed"),
        "validator_failure_codes": refined.get("validator_failure_codes", validator_failure_codes(historical)),
        "citations": citations,
        "citation_identity_valid": refined.get("citation_identity_valid", False),
        "citation_authorized": refined.get("citation_authorized", False),
        "citation_completeness": refined.get("citation_completeness"),
        "citation_source_alignment_failures": source_alignment,
        "context": {
            "chunk_count": len(chunks),
            "unique_source_count": len({chunk.payload.get("source_id") for chunk in chunks}),
            "duplicate_count": len(chunks) - len({chunk.id for chunk in chunks}),
            "context_chars": len(context),
            "context_tokens": _tokens(context),
            "input_chunk_ids": [chunk.id for chunk in chunks],
            "output_chunk_ids": [chunk.id for chunk in chunks],
            "gold_source_ranks": [index + 1 for index, chunk in enumerate(chunks) if chunk.payload.get("source_id") in question.get("required_evidence", [])],
            "truncated": False,
        },
        "generation_latency_ms": historical.get("generation_latency_ms"),
    }


def _compact_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for event in events:
        if event.get("type") == "metadata":
            compact.append(event)
        elif event.get("type") == "grounding":
            compact.append({key: event.get(key) for key in ("type", "grounded", "has_citations", "citations_found", "ungrounded_citations")})
        elif event.get("type") == "security_validation":
            compact.append({key: event.get(key) for key in ("type", "passed", "violations", "citation_suppressed", "hidden_prompt_leaked")})
        elif event.get("type") == "error":
            compact.append(event)
    return compact


def _candidate_row(
    record: dict[str, Any],
    question: dict[str, Any],
    builder: Any,
    observation: GenerationObservation,
    events: list[dict[str, Any]],
    provider_error: str | None,
    latency_ms: float,
) -> dict[str, Any]:
    raw = observation.raw_candidate_output or ""
    grounding = next((event for event in events if event.get("type") == "grounding"), {})
    validator_pass = observation.validator_pass if observation.validator_input_available else None
    fact_score = score_required_facts(
        question.get("expected_answer"), raw, observable=observation.raw_candidate_available
    )
    flags = []
    if has_material_contradiction(record["query_id"], raw):
        flags.append("MATERIAL_CONTRADICTION")
        if fact_score["status"] == "FULLY_CORRECT_COMPLETE":
            fact_score["status"] = "PARTIALLY_CORRECT"
    citation_ids = grounding.get("citations_found", [])
    invalid_ids = grounding.get("ungrounded_citations", [])
    identity_valid = bool(citation_ids) and not invalid_ids
    expected_sources = set(question.get("expected_source_ids", []))
    cited_sources = {citation[1] for citation in citation_ids}
    allowed_sources = expected_sources | set(question.get("supporting_source_ids", []))
    alignment_review = sum(source not in allowed_sources for source in cited_sources) if allowed_sources else 0
    return {
        "query_id": record["query_id"],
        "category": record["category"],
        "language_pair": record["language_pair"],
        "answerability": record["answerability"],
        "gold_present": record["gold_present"],
        "all_required_present": record["all_required_present"],
        "generation_calls": 1,
        "provider_status": "ERROR" if provider_error else "COMPLETED",
        "provider_error": provider_error,
        "generation_latency_ms": round(latency_ms, 3),
        "raw_candidate_observable": observation.raw_candidate_available,
        "raw_candidate_output": raw,
        "validated_output": raw if observation.validated_output_available else "",
        "user_visible_output": raw if observation.user_visible_output_available else "",
        "validator_pass": validator_pass,
        "validator_failure_codes": list(observation.validator_failure_codes),
        "fact_score": {**fact_score, "flags": flags},
        "citations": {
            "found": citation_ids,
            "unknown_or_unauthorized": invalid_ids,
            "identity_valid": identity_valid,
            "authorized": identity_valid,
            "source_alignment_failures": 0,
            "source_alignment_review_required": alignment_review,
            "support_status": "REQUIRES_MANUAL_REVIEW" if citation_ids and identity_valid else "UNOBSERVABLE",
        },
        "events": _compact_events(events),
        "context_builder": builder.as_dict(),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(row["fact_score"]["status"] for row in rows)
    latencies = [float(row["generation_latency_ms"]) for row in rows if row.get("generation_latency_ms") is not None]
    def identity_pass(row: dict[str, Any]) -> bool:
        if "citation_identity_valid" in row:
            return bool(row["citation_identity_valid"])
        citations = row.get("citations", {})
        if isinstance(citations, dict):
            return bool(citations.get("identity_valid", False))
        return bool(citations) and all(item.get("identity_valid", False) for item in citations)

    return {
        "n": len(rows),
        "fully_correct_complete": statuses["FULLY_CORRECT_COMPLETE"],
        "correct_but_incomplete": statuses["CORRECT_BUT_INCOMPLETE"],
        "partial": statuses["PARTIALLY_CORRECT"],
        "incorrect": statuses["INCORRECT"],
        "unobservable": statuses["UNOBSERVABLE"],
        "validator_failures": sum(row.get("validator_pass") is False for row in rows),
        "citation_identity_pass": sum(identity_pass(row) for row in rows),
        "citation_alignment_failures": sum(
            row.get("citation_source_alignment_failures", 0)
            if "citation_source_alignment_failures" in row
            else (
                row.get("citations", {}).get("source_alignment_failures", 0)
                if isinstance(row.get("citations", {}), dict)
                else 0
            )
            for row in rows
        ),
        "citation_alignment_review_required": sum(
            row.get("citations", {}).get("source_alignment_review_required", 0)
            if isinstance(row.get("citations", {}), dict)
            else 0
            for row in rows
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
    }


def _write_outputs(
    metadata: dict[str, Any],
    selection: dict[str, Any],
    a_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
    questions: dict[str, Any],
) -> None:
    by_a = {row["query_id"]: row for row in a_rows}
    by_b = {row["query_id"]: row for row in b_rows}
    comparisons = []
    order = {"UNOBSERVABLE": 0, "INCORRECT": 1, "PARTIALLY_CORRECT": 2, "CORRECT_BUT_INCOMPLETE": 3, "FULLY_CORRECT_COMPLETE": 4}
    for query_id, _, _ in SELECTION:
        a, b = by_a[query_id], by_b[query_id]
        a_status, b_status = a["fact_score"]["status"], b["fact_score"]["status"]
        comparisons.append({
            "query_id": query_id,
            "a": a,
            "b": b,
            "outcome": "IMPROVED" if order[b_status] > order[a_status] else "REGRESSED" if order[b_status] < order[a_status] else "UNCHANGED",
            "fact_coverage": {"a": a["fact_score"].get("fact_coverage"), "b": b["fact_score"].get("fact_coverage")},
            "context_token_ratio": (b["context_builder"]["context_tokens"] / a["context"]["context_tokens"]) if a["context"]["context_tokens"] else None,
            "latency_ratio": (b["generation_latency_ms"] / a["generation_latency_ms"]) if a.get("generation_latency_ms") and b.get("generation_latency_ms") else None,
        })

    a_metrics, b_metrics = _metrics(a_rows), _metrics(b_rows)
    multidoc = [row for row in comparisons if row["a"]["category"] == "multi_document"]
    hard = [row for row in comparisons if row["a"]["category"] == "hard_answerable"]
    cross = [row for row in comparisons if row["a"]["category"] == "cross_lingual"]
    authority = [row for row in comparisons if row["a"]["category"] == "version_conflict"]
    injected = [row for row in comparisons if row["a"]["category"] == "injection_bearing"]
    ratios = [row["latency_ratio"] for row in comparisons if row["latency_ratio"] is not None]
    summary = {
        "status": "PROBE_COMPLETED",
        "identity": {key: metadata.get(key) for key in EXPECTED_CACHE},
        "models": {"a": MODEL, "b": MODEL},
        "arms": {"a": "raw reranked authorized Top-5 + current formatter", "b": "Context Builder v1 + same Top-5"},
        "calls": {"a_generation": 0, "b_generation": len(b_rows), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "a": a_metrics,
        "b": b_metrics,
        "delta": {key: b_metrics[key] - a_metrics[key] for key in ("fully_correct_complete", "correct_but_incomplete", "partial", "incorrect", "unobservable", "validator_failures")},
        "outcomes": dict(Counter(row["outcome"] for row in comparisons)),
        "multi_document": {"a_full": sum(row["a"]["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in multidoc), "b_full": sum(row["b"]["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in multidoc), "records": multidoc},
        "dedupe": {"removed_chunks": sum(len(row["b"]["context_builder"]["removed_chunk_ids"]) for row in comparisons), "ordering_changes": sum(row["b"]["context_builder"]["ordering_changes"] for row in comparisons)},
        "evidence_lost": any(set(row["b"]["context_builder"]["output_chunk_ids"]) != set(row["b"]["context_builder"]["input_chunk_ids"]) for row in comparisons),
        "top5_membership_expanded": False,
        "latency_ratio": {"median": statistics.median(ratios) if ratios else None, "max": max(ratios) if ratios else None},
        "full_development": False, "calibration": False, "frozen_test_touched": False,
        "slices": {"hard": hard, "cross_lingual": cross, "authority": authority, "injection": injected},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "query-selection.json", selection)
    _write(OUT / "context-builder-config.json", {
        "version": "context_builder_v1", "model": MODEL, "prompt_version": PROMPT, "think": False,
        "max_context_tokens": MAX_CONTEXT_TOKENS, "dedupe": "exact normalized content + same citation identity only",
        "ordering": "stable original reranker order", "neighbor_expansion": False,
        "top5_membership_changed": False,
    })
    _write(OUT / "a-baseline-results.json", {"model": MODEL, "generation_reused": True, "metrics": a_metrics, "results": a_rows})
    _write(OUT / "b-context-builder-results.json", {"model": MODEL, "generation_calls": len(b_rows), "metrics": b_metrics, "results": b_rows})
    _write(OUT / "per-query-comparison.jsonl", "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in comparisons) + "\n")
    _write(OUT / "dedupe-analysis.json", {"removed_chunks": summary["dedupe"]["removed_chunks"], "records": [{"query_id": row["query_id"], "builder": row["b"]["context_builder"]} for row in comparisons]})
    _write(OUT / "context-order-analysis.json", [{"query_id": row["query_id"], "a": row["a"]["context"], "b": row["b"]["context_builder"]} for row in comparisons])
    _write(OUT / "multidoc-comparison.json", multidoc)
    _write(OUT / "hard-comparison.json", hard)
    _write(OUT / "cross-lingual-comparison.json", cross)
    _write(OUT / "authority-comparison.json", authority)
    _write(OUT / "citation-alignment-comparison.json", {"a": a_metrics, "b": b_metrics, "records": comparisons})
    _write(OUT / "validator-comparison.json", {"a": a_metrics, "b": b_metrics, "records": comparisons})
    _write(OUT / "context-size-comparison.json", [{"query_id": row["query_id"], "a": row["a"]["context"], "b": row["b"]["context_builder"], "ratio": row["context_token_ratio"]} for row in comparisons])
    _write(OUT / "latency-comparison.json", {"a": a_metrics["latency_ms"], "b": b_metrics["latency_ms"], "ratios": ratios})
    _write(OUT / "summary.json", summary)
    improved = summary["outcomes"].get("IMPROVED", 0)
    decision = "CONTEXT_BUILDER_GAIN_STRONG" if summary["multi_document"]["b_full"] > summary["multi_document"]["a_full"] and improved else "CONTEXT_BUILDER_GAIN_MODEST" if improved else "CONTEXT_BUILDER_NO_MEANINGFUL_GAIN"
    report = f"""# Phase 7.4 Context Builder v1 Probe

Decision: **{decision}**

This is a controlled 12-query probe. Arm A reused the historical qwen3.5:4b
outputs and Arm B ran the same model, prompt `{PROMPT}`, think=false, and
strict validation after deterministic Context Builder v1 presentation. The
authorized Top-5 set was reused unchanged; no retrieval or semantic gate ran.

- A full correct/complete: `{a_metrics['fully_correct_complete']}/12`
- B full correct/complete: `{b_metrics['fully_correct_complete']}/12`
- Multi-document full: A `{summary['multi_document']['a_full']}/3`, B `{summary['multi_document']['b_full']}/3`
- Validator failures: A `{a_metrics['validator_failures']}`, B `{b_metrics['validator_failures']}`
- Citation-alignment proxy failures: A `{a_metrics['citation_alignment_failures']}`, B `{b_metrics['citation_alignment_failures']}`
- Context tokens p50: A `{_percentile([row['a']['context']['context_tokens'] for row in comparisons], .5)}`, B `{_percentile([row['b']['context_builder']['context_tokens'] for row in comparisons], .5)}`
- Generation p95: A `{a_metrics['latency_ms']['p95']}` ms, B `{b_metrics['latency_ms']['p95']}` ms
- Evidence lost: `{summary['evidence_lost']}`; Top-5 expanded: `False`

The probe does not promote B to the runtime default and does not claim a
production-quality result from twelve records.
"""
    _write(OUT / "report.md", report)


async def _run_b(records: list[dict[str, Any]], questions: dict[str, Any], settings: Settings, cache: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    client = OllamaClient(base_url=settings.ollama_base_url, think=False)
    output: list[dict[str, Any]] = []
    partial_path = OUT / "b-context-builder-results.partial.jsonl"
    partial_path.unlink(missing_ok=True)
    try:
        for record in records:
            chunks = chunks_from_cache(record)
            builder = build_context_v1(chunks, max_context_tokens=MAX_CONTEXT_TOKENS)
            if set(builder.output_chunk_ids) != set(builder.input_chunk_ids):
                raise ValueError(f"Context Builder changed unique Top-5 membership for {record['query_id']}")
            observation = GenerationObservation()
            events: list[dict[str, Any]] = []
            started = time.perf_counter()
            provider_error: str | None = None
            try:
                async for event in stream_answer(
                    record["query"], builder.chunks, client, model=MODEL, prompt_version=PROMPT,
                    validation_mode=settings.security_validation_mode,
                    injection_eval_category="injection_bearing" if record["category"] == "injection_bearing" else None,
                    evaluation_observation=observation,
                    context_serializer=lambda _chunks, rendered=builder.context: rendered,
                ):
                    events.append(event)
            except Exception as exc:
                provider_error = type(exc).__name__
            output.append(_candidate_row(record, questions[record["query_id"]], builder, observation, events, provider_error, (time.perf_counter() - started) * 1000))
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            partial_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in output) + "\n",
                encoding="utf-8",
            )
    finally:
        await client.aclose()
    return output


async def run(args: argparse.Namespace) -> int:
    metadata, historical, cache, questions = _cache()
    selection = selection_artifact(metadata, historical, questions)
    _write(OUT / "query-selection.json", selection)
    _write(OUT / "context-builder-config.json", {"version": "context_builder_v1", "model": MODEL, "prompt_version": PROMPT, "think": False, "max_context_tokens": MAX_CONTEXT_TOKENS, "retrieval_reused": True})
    availability = OllamaClient(base_url=args.ollama_url or Settings.benchmark_reference().ollama_base_url)
    try:
        models = await availability.list_models()
        if MODEL not in models:
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: {MODEL}; available={models}")
    finally:
        await availability.aclose()
    settings = Settings.benchmark_reference(**({"ollama_base_url": args.ollama_url} if args.ollama_url else {}))
    selected = [cache[query_id] for query_id, _, _ in SELECTION]
    b_rows = await _run_b(selected, questions, settings, cache)
    refined = _old_refined()
    historical_by_id = {row["query_id"]: row for row in historical}
    a_rows = [_baseline_row(historical_by_id[query_id], cache[query_id], questions[query_id], refined[query_id]) for query_id, _, _ in SELECTION]
    _write_outputs(metadata, selection, a_rows, b_rows, cache, questions)
    print(json.dumps({"status": "COMPLETED", "b_generation_calls": len(b_rows), "retrieval_calls": 0}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-url", default=None)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
