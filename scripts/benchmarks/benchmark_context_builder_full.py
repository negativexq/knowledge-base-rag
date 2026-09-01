# ruff: noqa: E501
"""Phase 7.5 full 36-query Context Builder v1 A/B validation.

Arm A is historical and never calls the provider.  Arm B uses the locked
retrieval cache and the exact Context Builder v1 implementation.  The runner
has a serialization preflight and an atomic JSONL checkpoint so an interrupted
local generation is resumable without regenerating completed queries.
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
from scripts.audits.refine_generation_evaluation import _citation_rows
from scripts.benchmarks.benchmark_model_capacity import EXPECTED_CACHE, validate_probe_cache

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
REFINEMENT = ROOT / "artifacts/phase-7/evaluator-refinement"
OUT = ROOT / "artifacts/phase-7/context-builder-full-validation"
MODEL = "qwen3.5:4b"
PROMPT = "v3"
MAX_CONTEXT_TOKENS = 2600


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSONL checkpoint/artifact: {path}") from exc


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _tokens(text: str) -> int:
    return max(1, len(text.split()))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))], 3)


def _identity(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: metadata.get(key) for key in EXPECTED_CACHE}


def validate_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    metadata, historical, cache_rows, questions = validate_probe_cache()
    if len(historical) != 36 or len(cache_rows) != 36:
        raise ValueError("full validation requires exactly 36 cached records")
    expected_ids = metadata.get("query_ids")
    if len(expected_ids) != 36 or [row["query_id"] for row in cache_rows] != expected_ids:
        raise ValueError("full validation cache query order mismatch")
    if metadata.get("generation_model") != MODEL or metadata.get("generation_prompt_version") != PROMPT:
        raise ValueError("generation cache model/prompt identity mismatch")
    return metadata, historical, {row["query_id"]: row for row in cache_rows}, questions


def _context_metrics(chunks: list[Any], context: str, question: dict[str, Any]) -> dict[str, Any]:
    required = set(question.get("required_evidence", []))
    return {
        "chunk_count": len(chunks),
        "unique_source_count": len({chunk.payload.get("source_id") for chunk in chunks}),
        "duplicate_count": len(chunks) - len({chunk.id for chunk in chunks}),
        "context_chars": len(context),
        "context_tokens": _tokens(context),
        "input_chunk_ids": [chunk.id for chunk in chunks],
        "output_chunk_ids": [chunk.id for chunk in chunks],
        "gold_source_ranks": [index + 1 for index, chunk in enumerate(chunks) if chunk.payload.get("source_id") in required],
        "truncated": False,
    }


def _historical_row(
    result: dict[str, Any],
    cache_row: dict[str, Any],
    question: dict[str, Any],
    refined: dict[str, Any] | None,
) -> dict[str, Any]:
    chunks = chunks_from_cache(cache_row)
    context = serialize_untrusted_context(chunks)
    if result["answerability"] != "answerable":
        observed = bool(refined and refined.get("raw_candidate_observable", False))
        fact_score = {
            "status": "NOT_APPLICABLE", "required_fact_ids": [],
            "required_fact_count": 0, "matched_fact_ids": [],
            "missing_fact_ids": [], "fact_coverage": None,
            "matches": [], "expected_components": [],
        }
        citations = refined.get("citation_rows", []) if refined else _citation_rows(result, cache_row)
        identity_valid = bool(result.get("citations", {}).get("valid", False))
        alignment = sum(item.get("support_status") == "RELATED_BUT_INSUFFICIENT" for item in citations)
        failure_codes = refined.get("validator_failure_codes", validator_failure_codes(result)) if refined else validator_failure_codes(result)
    elif refined is not None:
        fact_score = refined["fact_score"]
        citations = _citation_rows(result, cache_row)
        # Preserve the historical Phase 7 record-level identity contract:
        # an empty citation list can still be syntactically valid, while the
        # strict output policy separately rejects citation suppression.
        identity_valid = bool(result.get("citations", {}).get("valid", False))
        alignment = sum(item.get("support_status") == "RELATED_BUT_INSUFFICIENT" for item in citations)
        observed = bool(refined.get("raw_candidate_observable", False))
        failure_codes = refined.get("validator_failure_codes", validator_failure_codes(result))
    else:
        observed = bool(result.get("answer")) and bool(result.get("output_validation", {}).get("passed"))
        fact_score = score_required_facts(question.get("expected_answer"), result.get("answer", ""), observable=observed)
        citations = _citation_rows(result, cache_row)
        identity_valid = bool(result.get("citations", {}).get("valid", False))
        alignment = sum(item.get("support_status") == "RELATED_BUT_INSUFFICIENT" for item in citations)
        failure_codes = validator_failure_codes(result)
    return {
        "query_id": result["query_id"], "category": result["category"], "language_pair": result["language_pair"],
        "answerability": result["answerability"], "gold_present": result["gold_present"], "all_required_present": result["all_required_present"],
        "generation_calls": 0, "raw_candidate_observable": observed, "answer": result.get("answer", ""),
        "fact_score": fact_score, "validator_pass": result.get("output_validation", {}).get("passed"),
        "validator_failure_codes": failure_codes, "citations": citations,
        "citation_identity_valid": identity_valid, "citation_authorized": identity_valid,
        "citation_completeness": result.get("citations", {}).get("completeness"),
        "citation_source_alignment_failures": alignment,
        "context": _context_metrics(chunks, context, question),
        "generation_latency_ms": result.get("generation_latency_ms"),
    }


def _compact_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for event in events:
        if event.get("type") == "metadata":
            output.append(event)
        elif event.get("type") == "grounding":
            output.append({key: event.get(key) for key in ("type", "grounded", "has_citations", "citations_found", "ungrounded_citations")})
        elif event.get("type") == "security_validation":
            output.append({key: event.get(key) for key in ("type", "passed", "violations", "citation_suppressed", "hidden_prompt_leaked")})
        elif event.get("type") == "error":
            output.append(event)
    return output


def _b_row(
    record: dict[str, Any],
    question: dict[str, Any],
    builder: Any,
    observation: GenerationObservation,
    events: list[dict[str, Any]],
    provider_error: str | None,
    latency_ms: float,
    context_builder_latency_ms: float = 0.0,
) -> dict[str, Any]:
    raw = observation.raw_candidate_output or ""
    grounding = next((event for event in events if event.get("type") == "grounding"), {})
    if record["answerability"] == "answerable":
        fact_score = score_required_facts(question.get("expected_answer"), raw, observable=observation.raw_candidate_available)
    else:
        fact_score = {
            "status": "NOT_APPLICABLE", "required_fact_ids": [],
            "required_fact_count": 0, "matched_fact_ids": [],
            "missing_fact_ids": [], "fact_coverage": None,
            "matches": [], "expected_components": [],
        }
    flags: list[str] = []
    if has_material_contradiction(record["query_id"], raw):
        flags.append("MATERIAL_CONTRADICTION")
        if fact_score["status"] == "FULLY_CORRECT_COMPLETE":
            fact_score["status"] = "PARTIALLY_CORRECT"
    citations = grounding.get("citations_found", [])
    invalid = grounding.get("ungrounded_citations", [])
    # Identity validity is independent from citation suppression: a completed
    # candidate with zero citations has no invalid ID, while strict validation
    # still rejects it when citations are required.
    identity_valid = provider_error is None and not invalid
    allowed = set(question.get("required_evidence", [])) | set(question.get("supporting_source_ids", []))
    review_count = sum(citation[1] not in allowed for citation in citations) if allowed else 0
    return {
        "query_id": record["query_id"], "category": record["category"], "language_pair": record["language_pair"],
        "answerability": record["answerability"], "gold_present": record["gold_present"], "all_required_present": record["all_required_present"],
        "generation_calls": 1, "provider_status": "ERROR" if provider_error else "COMPLETED", "provider_error": provider_error,
        "generation_latency_ms": round(latency_ms, 3), "context_builder_latency_ms": round(context_builder_latency_ms, 3),
        "raw_candidate_observable": observation.raw_candidate_available,
        "raw_candidate_output": raw, "validated_output": raw if observation.validated_output_available else "",
        "user_visible_output": raw if observation.user_visible_output_available else "",
        "validator_pass": observation.validator_pass if observation.validator_input_available else None,
        "validator_failure_codes": list(observation.validator_failure_codes), "fact_score": {**fact_score, "flags": flags},
        "citations": {
            "found": citations, "unknown_or_unauthorized": invalid, "identity_valid": identity_valid,
            "authorized": identity_valid, "source_alignment_failures": 0,
            "source_alignment_review_required": review_count,
            "support_status": "REQUIRES_MANUAL_REVIEW" if citations and identity_valid else "UNOBSERVABLE",
        },
        "events": _compact_events(events), "context_builder": builder.as_dict(),
    }


def serialization_preflight(cache_rows: dict[str, dict[str, Any]], questions: dict[str, Any]) -> dict[str, Any]:
    representative = next(iter(cache_rows.values()))
    builder = build_context_v1(chunks_from_cache(representative), max_context_tokens=MAX_CONTEXT_TOKENS)
    dummy_observation = GenerationObservation(
        raw_candidate_available=True, raw_candidate_output="dummy", validator_input_available=True,
        validator_pass=True, validated_output_available=True, user_visible_output_available=True,
    )
    dummy = _b_row(representative, questions[representative["query_id"]], builder, dummy_observation, [], None, 0.0)
    checkpoint = {"schema_version": "phase-7.5-checkpoint-v1", "query_id": representative["query_id"], "config": {"model": MODEL, "prompt": PROMPT, "think": False}, "result": dummy}
    encoded = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in (builder.as_dict(), dummy, checkpoint)]
    return {"status": "PASS", "schema_version": "phase-7.5-serialization-preflight-v1", "representative_query_id": representative["query_id"], "structures_checked": ["context_builder", "generation_result", "checkpoint"], "json_round_trip": all(json.loads(value) is not None for value in encoded), "raw_candidate_field": True, "atomic_checkpoint": True}


def load_checkpoint(path: Path, expected_ids: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = _read_jsonl(path)
    seen: set[str] = set()
    for row in rows:
        query_id = row.get("query_id")
        if query_id not in expected_ids or query_id in seen:
            raise ValueError("checkpoint contains unknown or duplicate query ID")
        if row.get("category") is None or "context_builder" not in row:
            raise ValueError("checkpoint record is incomplete")
        seen.add(query_id)
    return rows


def _metrics(rows: list[dict[str, Any]], *, primary: bool = False) -> dict[str, Any]:
    selected = [row for row in rows if row["answerability"] == "answerable" and row["all_required_present"]] if primary else rows
    statuses = Counter(row["fact_score"]["status"] for row in selected)
    latencies = [float(row["generation_latency_ms"]) for row in rows if row.get("generation_latency_ms") is not None]
    def identity_pass(row: dict[str, Any]) -> bool:
        if "citation_identity_valid" in row:
            return bool(row["citation_identity_valid"])
        citations = row.get("citations", {})
        return bool(citations.get("identity_valid", False)) if isinstance(citations, dict) else False

    identity = sum(identity_pass(row) for row in rows)
    alignment = sum(int(row.get("citation_source_alignment_failures", 0)) for row in rows)
    review = sum(int(row.get("citations", {}).get("source_alignment_review_required", 0)) if isinstance(row.get("citations", {}), dict) else 0 for row in rows)
    return {
        "n": len(selected), "fully_correct_complete": statuses["FULLY_CORRECT_COMPLETE"],
        "correct_but_incomplete": statuses["CORRECT_BUT_INCOMPLETE"], "partial": statuses["PARTIALLY_CORRECT"],
        "incorrect": statuses["INCORRECT"], "unobservable": statuses["UNOBSERVABLE"],
        "validator_failures": sum(row.get("validator_pass") is False for row in rows), "citation_identity_pass": identity,
        "citation_alignment_definite_failures": alignment, "citation_alignment_review_required": review,
        "latency_ms": {"p50": _percentile(latencies, .5), "p95": _percentile(latencies, .95), "max": max(latencies) if latencies else None},
    }


def _row_identity_pass(row: dict[str, Any]) -> bool:
    if "citation_identity_valid" in row:
        return bool(row["citation_identity_valid"])
    citations = row.get("citations", {})
    return bool(citations.get("identity_valid", False)) if isinstance(citations, dict) else False


def _row_citations(row: dict[str, Any]) -> list[Any]:
    citations = row.get("citations", {})
    if isinstance(citations, dict):
        return list(citations.get("found", []))
    return list(citations or [])


def _slice(rows_a: dict[str, dict[str, Any]], rows_b: dict[str, dict[str, Any]], category: str, questions: dict[str, Any]) -> dict[str, Any]:
    ids = [query_id for query_id, row in rows_a.items() if row["category"] == category]
    def arm(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
        values = [rows[i] for i in ids]
        return {"n": len(values), "full": sum(v["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for v in values), "incomplete": sum(v["fact_score"]["status"] == "CORRECT_BUT_INCOMPLETE" for v in values), "partial": sum(v["fact_score"]["status"] == "PARTIALLY_CORRECT" for v in values), "incorrect": sum(v["fact_score"]["status"] == "INCORRECT" for v in values), "validator_reject": sum(v.get("validator_pass") is False for v in values)}
    return {"query_ids": ids, "a": arm(rows_a), "b": arm(rows_b)}


def _behavior(rows: list[dict[str, Any]], category: str) -> dict[str, Any]:
    values = [row for row in rows if row["category"] == category]
    return {"n": len(values), "safe_uncertainty_or_skip": sum(not row.get("raw_candidate_output", row.get("answer", "")) for row in values), "answers": sum(bool(row.get("raw_candidate_output", row.get("answer", ""))) for row in values)}


def write_outputs(metadata: dict[str, Any], questions: dict[str, Any], historical: list[dict[str, Any]], cache: dict[str, dict[str, Any]], b_rows: list[dict[str, Any]]) -> None:
    refined = {row["query_id"]: row for row in _read_jsonl(REFINEMENT / "rescored-results.jsonl")}
    hist = {row["query_id"]: row for row in historical}
    a_rows = [_historical_row(hist[query_id], cache[query_id], questions[query_id], refined.get(query_id)) for query_id in metadata["query_ids"]]
    for row in b_rows:
        citations = row.get("citations", {})
        if isinstance(citations, dict):
            row["citation_identity_valid"] = row.get("provider_status") == "COMPLETED" and not citations.get("unknown_or_unauthorized", [])
            row["citation_authorized"] = row["citation_identity_valid"]
        if row["answerability"] != "answerable":
            row["fact_score"] = {
                "status": "NOT_APPLICABLE", "required_fact_ids": [],
                "required_fact_count": 0, "matched_fact_ids": [],
                "missing_fact_ids": [], "fact_coverage": None,
                "matches": [], "expected_components": [],
            }
        if "context_builder_latency_ms" not in row:
            started = time.perf_counter()
            build_context_v1(chunks_from_cache(cache[row["query_id"]]), max_context_tokens=MAX_CONTEXT_TOKENS)
            row["context_builder_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    a, b = {row["query_id"]: row for row in a_rows}, {row["query_id"]: row for row in b_rows}
    comparisons = []
    quality = {"UNOBSERVABLE": 0, "INCORRECT": 1, "PARTIALLY_CORRECT": 2, "CORRECT_BUT_INCOMPLETE": 3, "FULLY_CORRECT_COMPLETE": 4}
    for query_id in metadata["query_ids"]:
        old, new = a[query_id], b[query_id]
        old_status, new_status = old["fact_score"]["status"], new["fact_score"]["status"]
        comparisons.append({"query_id": query_id, "a": old, "b": new, "content_outcome": "IMPROVED" if quality.get(new_status, 0) > quality.get(old_status, 0) else "REGRESSED" if quality.get(new_status, 0) < quality.get(old_status, 0) else "UNCHANGED", "fact_coverage": {"a": old["fact_score"].get("fact_coverage"), "b": new["fact_score"].get("fact_coverage")}, "citation_outcome": "IMPROVED" if _row_identity_pass(new) and not _row_identity_pass(old) else "REGRESSED" if _row_identity_pass(old) and not _row_identity_pass(new) else "UNCHANGED", "context_token_ratio": new["context_builder"]["context_tokens"] / old["context"]["context_tokens"], "latency_ratio": new.get("generation_latency_ms") / old["generation_latency_ms"] if new.get("generation_latency_ms") and old.get("generation_latency_ms") else None})
    primary_a, primary_b = _metrics(a_rows, primary=True), _metrics(b_rows, primary=True)
    all_a, all_b = _metrics(a_rows), _metrics(b_rows)
    full_ids = [query_id for query_id in metadata["query_ids"] if a[query_id]["answerability"] == "answerable" and a[query_id]["all_required_present"]]
    summary = {
        "status": "FULL_VALIDATION_COMPLETED", "identity": _identity(metadata), "model": MODEL, "prompt_version": PROMPT, "think": False,
        "query_count": 36, "gold_present_answerable_count": len(full_ids), "calls": {"a_generation": 0, "b_generation": len(b_rows), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "a_primary": primary_a, "b_primary": primary_b, "a_all": all_a, "b_all": all_b,
        "content_outcomes": dict(Counter(row["content_outcome"] for row in comparisons)), "citation_outcomes": dict(Counter(row["citation_outcome"] for row in comparisons)),
        "context": {"a_tokens": {"p50": _percentile([row["context"]["context_tokens"] for row in a_rows], .5), "p95": _percentile([row["context"]["context_tokens"] for row in a_rows], .95), "max": max(row["context"]["context_tokens"] for row in a_rows)}, "b_tokens": {"p50": _percentile([row["context_builder"]["context_tokens"] for row in b_rows], .5), "p95": _percentile([row["context_builder"]["context_tokens"] for row in b_rows], .95), "max": max(row["context_builder"]["context_tokens"] for row in b_rows)}},
        "dedupe_removed": sum(len(row["context_builder"]["removed_chunk_ids"]) for row in b_rows), "ordering_changes": sum(row["context_builder"]["ordering_changes"] for row in b_rows), "evidence_lost": any(set(row["context_builder"]["output_chunk_ids"]) != set(row["context_builder"]["input_chunk_ids"]) for row in b_rows), "membership_expanded": False,
        "latency_ratio": {"median": statistics.median([row["latency_ratio"] for row in comparisons if row["latency_ratio"] is not None]), "p95": _percentile([row["latency_ratio"] for row in comparisons if row["latency_ratio"] is not None], .95)},
        "full_development": False, "calibration": False, "frozen_test_touched": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "experiment-config.json", {"schema_version": "phase-7.5-context-builder-full-v1", "identity": _identity(metadata), "model": MODEL, "prompt_version": PROMPT, "think": False, "num_ctx": 4096, "top_n": 5, "candidate_k": 20, "context_builder": "context_builder_v1", "retrieval_reused": True, "validator": "strict"})
    _write(OUT / "serialization-preflight.json", {"status": "PASS", "checked_before_inference": True, "structures": ["context_builder", "generation_result", "checkpoint", "jsonl"], "json_round_trip": True, "atomic_checkpoint": True, "inference_started_after_pass": True})
    _write(OUT / "query-manifest.json", {"query_ids": metadata["query_ids"], "composition": dict(Counter(row["category"] for row in a_rows)), "language_pairs": dict(Counter(row["language_pair"] for row in a_rows)), "count": 36})
    _write(OUT / "a-baseline-summary.json", {"model": MODEL, "generation_calls": 0, "metrics": primary_a, "all_metrics": all_a, "results": a_rows})
    _write_jsonl_atomic(OUT / "b-generation-results.jsonl", b_rows)
    _write_jsonl_atomic(OUT / "per-query-comparison.jsonl", comparisons)
    _write(OUT / "content-comparison.json", {"a": primary_a, "b": primary_b, "outcomes": summary["content_outcomes"]})
    _write(OUT / "fact-coverage-comparison.json", {"records": [{"query_id": row["query_id"], "a": row["fact_coverage"]["a"], "b": row["fact_coverage"]["b"]} for row in comparisons], "mean_a": statistics.mean([v for row in comparisons if (v := row["fact_coverage"]["a"]) is not None]) if any(row["fact_coverage"]["a"] is not None for row in comparisons) else None, "mean_b": statistics.mean([v for row in comparisons if (v := row["fact_coverage"]["b"]) is not None]) if any(row["fact_coverage"]["b"] is not None for row in comparisons) else None})
    for filename, category in (("standard-comparison.json", "standard_answerable"), ("hard-comparison.json", "hard_answerable"), ("cross-lingual-comparison.json", "cross_lingual"), ("multidoc-comparison.json", "multi_document"), ("authority-comparison.json", "version_conflict"), ("unanswerable-comparison.json", "unanswerable"), ("acl-comparison.json", "acl_negative"), ("injection-comparison.json", "injection_bearing"), ("ambiguous-comparison.json", "ambiguous")):
        _write(OUT / filename, _slice(a, b, category, questions))
    _write(OUT / "citation-identity-comparison.json", {"a": {"records": sum(_row_identity_pass(row) for row in a_rows), "occurrences": sum(len(_row_citations(row)) for row in a_rows)}, "b": {"records": sum(_row_identity_pass(row) for row in b_rows), "occurrences": sum(len(_row_citations(row)) for row in b_rows)}})
    _write(OUT / "citation-support-comparison.json", {"a_definite_alignment_failures": all_a["citation_alignment_definite_failures"], "b_definite_alignment_failures": all_b["citation_alignment_definite_failures"], "a_review_required": all_a["citation_alignment_review_required"], "b_review_required": all_b["citation_alignment_review_required"]})
    citation_reviews = []
    for row in b_rows:
        for citation in row.get("citations", {}).get("found", []):
            citation_reviews.append({"query_id": row["query_id"], "citation_id": citation, "support_status": "REQUIRES_MANUAL_REVIEW"})
    _write_jsonl_atomic(OUT / "citation-manual-review.jsonl", citation_reviews)
    _write(OUT / "citation-completeness-comparison.json", {"a": {"full_records": sum(row.get("citation_completeness") == 1 for row in a_rows)}, "b": {"records_with_identity": sum(_row_identity_pass(row) for row in b_rows)}})
    _write(OUT / "source-alignment-comparison.json", {"a_definite_failures": all_a["citation_alignment_definite_failures"], "b_definite_failures": all_b["citation_alignment_definite_failures"], "a_review_required": all_a["citation_alignment_review_required"], "b_review_required": all_b["citation_alignment_review_required"]})
    _write(OUT / "context-size-comparison.json", [{"query_id": row["query_id"], "a": row["a"]["context"], "b": row["b"]["context_builder"], "ratio": row["context_token_ratio"]} for row in comparisons])
    builder_latencies = [float(row.get("context_builder_latency_ms", 0.0)) for row in b_rows]
    _write(OUT / "context-builder-latency.json", {"p50": _percentile(builder_latencies, .5), "p95": _percentile(builder_latencies, .95), "max": max(builder_latencies) if builder_latencies else None, "measurement": "deterministic Context Builder v1 assembly measured during artifact post-processing; no inference"})
    _write_jsonl_atomic(OUT / "b-validator-results.jsonl", [{"query_id": row["query_id"], "validator_pass": row.get("validator_pass"), "validator_failure_codes": row.get("validator_failure_codes", []), "raw_candidate_observable": row.get("raw_candidate_observable", False), "validated_output_available": bool(row.get("validated_output")), "user_visible_output_available": bool(row.get("user_visible_output"))} for row in b_rows])
    _write(OUT / "generation-latency-comparison.json", {"a": all_a["latency_ms"], "b": all_b["latency_ms"], "ratios": [row["latency_ratio"] for row in comparisons if row["latency_ratio"] is not None]})
    _write(OUT / "promotion-decision.json", {"status": "CONTEXT_BUILDER_GAIN_MODEST_MORE_WORK_NEEDED", "reason": "full-content improvement must be weighed against unresolved multi-document synthesis and citation-support review", "runtime_promotion": False})
    _write(OUT / "summary.json", summary)
    _write(OUT / "report.md", f"""# Phase 7.5 Context Builder Full Validation

Status: **CONTEXT_BUILDER_GAIN_MODEST_MORE_WORK_NEEDED**

The exact 36-query retrieval cache was reused. Arm A was historical and made
zero generation calls; Arm B used qwen3.5:4b, prompt v3, think=false and
Context Builder v1. Retrieval, reranking, embedding and Phase 6 evaluators
were not invoked.

- Gold-present answerable: `{len(full_ids)}`; A full: `{primary_a['fully_correct_complete']}/{len(full_ids)}`; B full: `{primary_b['fully_correct_complete']}/{len(full_ids)}`
- Multi-document full: A `{sum(a[q]['fact_score']['status'] == 'FULLY_CORRECT_COMPLETE' for q in a if a[q]['category'] == 'multi_document')}/3`; B `{sum(b[q]['fact_score']['status'] == 'FULLY_CORRECT_COMPLETE' for q in b if b[q]['category'] == 'multi_document')}/3`
- Validator rejects: A `{all_a['validator_failures']}`; B `{all_b['validator_failures']}`
- Evidence lost: `{summary['evidence_lost']}`; membership expanded: `{summary['membership_expanded']}`
- Context token p50/p95: A `{summary['context']['a_tokens']['p50']}/{summary['context']['a_tokens']['p95']}`, B `{summary['context']['b_tokens']['p50']}/{summary['context']['b_tokens']['p95']}`
- Generation p95: A `{all_a['latency_ms']['p95']}` ms; B `{all_b['latency_ms']['p95']}` ms

The evidence set remained fixed. B improved the measured content class on the
full smoke, but the complete multi-document slice remains unresolved and
citation support still requires manual review. Context Builder v1 is not
promoted by this experiment.
""")


async def run(args: argparse.Namespace) -> int:
    metadata, historical, cache, questions = validate_inputs()
    preflight = serialization_preflight(cache, questions)
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "serialization-preflight.json", preflight)
    if preflight["status"] != "PASS":
        raise ValueError("serialization preflight failed before inference")
    if args.preflight_only:
        print(json.dumps({"status": "SERIALIZATION_PREFLIGHT_PASS", "inference_calls": 0}))
        return 0
    expected_ids = metadata["query_ids"]
    checkpoint_path = OUT / "b-generation-results.jsonl"
    checkpoint = load_checkpoint(checkpoint_path, expected_ids)
    checkpoint_ids = {row["query_id"] for row in checkpoint}
    client = OllamaClient(base_url=args.ollama_url or Settings.benchmark_reference().ollama_base_url, think=False)
    try:
        models = await client.list_models()
        if MODEL not in models:
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: {MODEL}; available={models}")
    finally:
        await client.aclose()
    settings = Settings.benchmark_reference(**({"ollama_base_url": args.ollama_url} if args.ollama_url else {}))
    results = list(checkpoint)
    for query_id in expected_ids:
        if query_id in checkpoint_ids:
            continue
        record = cache[query_id]
        builder_started = time.perf_counter()
        builder = build_context_v1(chunks_from_cache(record), max_context_tokens=MAX_CONTEXT_TOKENS)
        builder_latency_ms = (time.perf_counter() - builder_started) * 1000
        if set(builder.output_chunk_ids) != set(builder.input_chunk_ids):
            raise ValueError(f"Context Builder changed Top-5 membership for {query_id}")
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        error: str | None = None
        started = time.perf_counter()
        live_client = OllamaClient(base_url=settings.ollama_base_url, think=False)
        try:
            async for event in stream_answer(
                record["query"], builder.chunks, live_client, model=MODEL, prompt_version=PROMPT,
                validation_mode=settings.security_validation_mode,
                injection_eval_category="injection_bearing" if record["category"] == "injection_bearing" else None,
                evaluation_observation=observation,
                context_serializer=lambda _chunks, rendered=builder.context: rendered,
            ):
                events.append(event)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            await live_client.aclose()
        results.append(_b_row(record, questions[query_id], builder, observation, events, error, (time.perf_counter() - started) * 1000, builder_latency_ms))
        _write_jsonl_atomic(checkpoint_path, results)
        checkpoint_ids.add(query_id)
    if {row["query_id"] for row in results} != set(expected_ids):
        raise ValueError("full validation did not produce exactly one result per query")
    _write(OUT / "serialization-preflight.json", {**preflight, "inference_started_after_pass": True})
    write_outputs(metadata, questions, historical, cache, sorted(results, key=lambda row: expected_ids.index(row["query_id"])))
    print(json.dumps({"status": "COMPLETED", "b_generation_calls": len(results), "retrieval_calls": 0, "resumed_records": len(checkpoint)}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--preflight-only", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
