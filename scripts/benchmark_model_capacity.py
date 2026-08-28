# ruff: noqa: E501
"""Cache-only Phase 7.3 qwen3.5 capacity probe.

The 4B side is read from the existing Phase 7 smoke.  Only the explicitly
selected 9B records are sent through the real generation path.  Retrieval and
all semantic evaluators are intentionally absent from this module.
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

from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import validator_failure_codes
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.shared.config import Settings
from scripts.refine_generation_evaluation import (
    _citation_rows,
    _score,
    validate_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
OUT = ROOT / "artifacts/phase-7/model-capacity-probe"
MODEL = "qwen3.5:9b"
PROMPT = "v3"
EXPECTED_CACHE = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
    "retrieval_config_fingerprint": "4210b5315b906c5b9b01db126dc1ff7a3aca69a78a8a943c93cbd2e7e276849f",
}

SELECTION = (
    ("multi-00-1", "multi_document", "complete multi-document synthesis"),
    ("multi-00-3", "multi_document", "complete multi-document synthesis with next-step request"),
    ("multi-03-0", "multi_document", "complete Turkish multi-document evidence; validator stress"),
    ("hard-policy-language", "hard_answerable", "gold-present cross-language/context reasoning failure"),
    ("hard-order-channel", "hard_answerable", "gold-present citation-suppression failure"),
    ("hard-annual-cancel", "hard_answerable", "multi-constraint control; not only matcher failure"),
    ("cross-00-1", "cross_lingual", "TR to EN substantive contradictory-answer case"),
    ("cross-06-0", "cross_lingual", "EN to TR citation/translation failure"),
    ("version-01-0", "version_conflict", "mixed authority/current-rule case"),
    ("version-01-1", "version_conflict", "current version control case"),
    ("native-00-2", "standard_answerable", "known successful standard regression control"),
    ("injection-03-0", "injection_bearing", "retrieved-instruction control case"),
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def validate_probe_cache() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    metadata, generation, cache, questions = validate_artifacts()
    for key, expected in EXPECTED_CACHE.items():
        actual = metadata.get(key)
        if actual != expected:
            raise ValueError(f"capacity probe cache mismatch for {key}: {actual!r}")
    selected_ids = [item[0] for item in SELECTION]
    cache_ids = {row["query_id"] for row in cache}
    if not set(selected_ids) <= cache_ids:
        raise ValueError("capacity selection contains an ID outside the Phase 7 cache")
    if len(selected_ids) != 12 or len(set(selected_ids)) != 12:
        raise ValueError("capacity probe must contain exactly 12 unique IDs")
    return metadata, generation, cache, questions


def build_selection_artifact(metadata: dict[str, Any], generation: list[dict[str, Any]], questions: dict[str, Any]) -> dict[str, Any]:
    records = []
    for query_id, slice_name, rationale in SELECTION:
        question = questions[query_id]
        records.append({
            "query_id": query_id,
            "category": question["category"],
            "language_pair": question["language_pair"],
            "gold_present": next(row["gold_present"] for row in generation if row["query_id"] == query_id),
            "all_required_present": next(row["all_required_present"] for row in generation if row["query_id"] == query_id),
            "probe_slice": slice_name,
            "rationale": rationale,
        })
    return {
        "schema_version": "phase-7.3-model-capacity-selection-v1",
        "probe_count": len(records),
        "query_ids": [row["query_id"] for row in records],
        "composition": dict(Counter(row["probe_slice"] for row in records)),
        "identity": {key: metadata.get(key) for key in EXPECTED_CACHE},
        "fixed_inputs": {"prompt_version": PROMPT, "think": False, "candidate_k": 20, "top_n": 5, "retrieval_reused": True},
        "models": {"baseline": "qwen3.5:4b", "probe": MODEL},
        "records": records,
    }


def _compact_result(result: dict[str, Any], cache_row: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    fact_score = _score(result, question)
    citations = _citation_rows(result, cache_row)
    cited_sources = {item["citation_id"][1] for item in citations if item.get("citation_id")}
    required_sources = set(question.get("required_evidence", []))
    support_reference = (
        "DETERMINISTICALLY_SUPPORTED"
        if result.get("citations", {}).get("support_correct") is True
        else "REQUIRES_CLAIM_REVIEW"
        if citations and all(item["support_status"] == "SUPPORTED" for item in citations)
        else None
    )
    return {
        "query_id": result["query_id"],
        "category": result["category"],
        "language_pair": result["language_pair"],
        "answerability": result["answerability"],
        "gold_present": result["gold_present"],
        "all_required_present": result["all_required_present"],
        "generation_invoked": result.get("generation_invoked", True),
        "provider_status": result.get("provider_status"),
        "provider_error": result.get("provider_error"),
        "generation_latency_ms": result.get("generation_latency_ms"),
        "answer": result.get("answer", ""),
        "fact_score": fact_score,
        "validator_pass": result.get("output_validation", {}).get("passed"),
        "validator_failure_codes": validator_failure_codes(result),
        "raw_candidate_observable": bool(result.get("answer")) and bool(result.get("output_validation", {}).get("passed")),
        "citations": citations,
        "citation_identity_valid": all(item["identity_valid"] for item in citations) if citations else False,
        "citation_authorized": all(item["authorized"] for item in citations) if citations else False,
        "citation_support_reference": support_reference,
        "citation_completeness": len(required_sources & cited_sources) / len(required_sources) if required_sources else None,
        "answer_sha256": __import__("hashlib").sha256(result.get("answer", "").encode("utf-8")).hexdigest() if result.get("answer") else None,
        "answer_characters": len(result.get("answer", "")),
    }


def _four_b_rows(generation: list[dict[str, Any]], cache: dict[str, dict[str, Any]], questions: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {query_id for query_id, _, _ in SELECTION}
    return [_compact_result(row, cache[row["query_id"]], questions[row["query_id"]]) for row in generation if row["query_id"] in selected]


async def _model_available(client: OllamaClient) -> bool:
    return MODEL in set(await client.list_models())


async def _run_nine_b(records: list[dict[str, Any]], questions: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    client = OllamaClient(base_url=settings.ollama_base_url, think=False)
    results: list[dict[str, Any]] = []
    try:
        for record in records:
            events: list[dict[str, Any]] = []
            answer_parts: list[str] = []
            error: str | None = None
            started = time.perf_counter()
            try:
                async for event in stream_answer(
                    record["query"],
                    chunks_from_cache(record),
                    client,
                    model=MODEL,
                    prompt_version=PROMPT,
                    validation_mode=settings.security_validation_mode,
                    injection_eval_category="injection_bearing" if record["category"] == "injection_bearing" else None,
                ):
                    events.append(event)
                    if event.get("type") == "token":
                        answer_parts.append(event.get("content", ""))
            except Exception as exc:  # record provider failure, then continue the fixed probe
                error = type(exc).__name__
            latency = round((time.perf_counter() - started) * 1000, 3)
            answer = "".join(answer_parts)
            security = next((event for event in events if event.get("type") == "security_validation"), {})
            grounding = next((event for event in events if event.get("type") == "grounding"), {})
            result = {
                "query_id": record["query_id"], "category": record["category"], "language_pair": record["language_pair"],
                "answerability": record["answerability"], "gold_present": record["gold_present"], "all_required_present": record["all_required_present"],
                "answer": answer, "events": events, "generation_invoked": True,
                "provider_status": "ERROR" if error else "COMPLETED", "provider_error": error,
                "generation_latency_ms": latency,
                "output_validation": {"passed": security.get("passed"), "violations": security.get("violations", [])},
                "citations": {"found": grounding.get("citations_found", []), "unknown_or_unauthorized": grounding.get("ungrounded_citations", [])},
            }
            if error:
                result["failure"] = "GENERATION_PROVIDER_FAILURE"
            results.append(result)
    finally:
        await client.aclose()
    return results


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(row["fact_score"]["status"] for row in rows)
    latencies = [float(row["generation_latency_ms"]) for row in rows if row.get("generation_latency_ms") is not None]
    citation_rows = [item for row in rows for item in row["citations"]]
    return {
        "n": len(rows), "fully_correct_complete": statuses["FULLY_CORRECT_COMPLETE"], "correct_but_incomplete": statuses["CORRECT_BUT_INCOMPLETE"],
        "partial": statuses["PARTIALLY_CORRECT"], "incorrect": statuses["INCORRECT"], "unobservable": statuses["UNOBSERVABLE"],
        "citation_identity_pass": sum(row["citation_identity_valid"] for row in rows),
        "citation_support_reference_pass": sum(row["citation_support_reference"] == "DETERMINISTICALLY_SUPPORTED" for row in rows),
        "citation_completeness_pass": sum(row["citation_completeness"] == 1 for row in rows),
        "validator_failures": sum(row["validator_pass"] is False for row in rows),
        "unsupported_or_contradicted": sum("MATERIAL_CONTRADICTION" in row["fact_score"].get("flags", []) for row in rows),
        "latency_ms": {"p50": statistics.median(latencies) if latencies else None, "p95": sorted(latencies)[round(.95 * (len(latencies) - 1))] if latencies else None, "max": max(latencies) if latencies else None},
        "citation_status_counts": dict(Counter(item["support_status"] for item in citation_rows)),
    }


def build_outputs(metadata: dict[str, Any], four_b: list[dict[str, Any]], nine_b_raw: list[dict[str, Any]], cache: dict[str, dict[str, Any]], questions: dict[str, Any], selection: dict[str, Any]) -> None:
    nine_b = []
    for result in nine_b_raw:
        compact = _compact_result(result, cache[result["query_id"]], questions[result["query_id"]])
        nine_b.append(compact)
    by4 = {row["query_id"]: row for row in four_b}
    by9 = {row["query_id"]: row for row in nine_b}
    quality_order = {"FULLY_CORRECT_COMPLETE": 5, "CORRECT_BUT_INCOMPLETE": 4, "PARTIALLY_CORRECT": 3, "INCORRECT": 2, "UNOBSERVABLE": 1}
    comparisons = []
    for query_id, _, _ in SELECTION:
        old, new = by4[query_id], by9[query_id]
        old_rank, new_rank = quality_order[old["fact_score"]["status"]], quality_order[new["fact_score"]["status"]]
        comparisons.append({"query_id": query_id, "four_b": old, "nine_b": new, "outcome": "IMPROVED" if new_rank > old_rank else "REGRESSED" if new_rank < old_rank else "UNCHANGED", "latency_ratio": (new["generation_latency_ms"] / old["generation_latency_ms"]) if old.get("generation_latency_ms") and new.get("generation_latency_ms") else None})
    four_metrics, nine_metrics = _metrics(four_b), _metrics(nine_b)
    multidoc = [row for row in comparisons if row["query_id"].startswith("multi-")]
    injection = [row for row in comparisons if row["query_id"] == "injection-03-0"]
    ratios = [row["latency_ratio"] for row in comparisons if row["latency_ratio"] is not None]
    summary = {
        "identity": {key: metadata.get(key) for key in EXPECTED_CACHE}, "models": {"four_b": "qwen3.5:4b", "nine_b": MODEL},
        "calls": {"four_b_generation": 0, "nine_b_generation": len(nine_b), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "four_b": four_metrics, "nine_b": nine_metrics,
        "delta": {key: nine_metrics.get(key, 0) - four_metrics.get(key, 0) for key in ("fully_correct_complete", "correct_but_incomplete", "partial", "incorrect", "unobservable", "validator_failures")},
        "outcomes": dict(Counter(row["outcome"] for row in comparisons)),
        "multi_document": {"four_b_full": sum(row["four_b"]["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in multidoc), "nine_b_full": sum(row["nine_b"]["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in multidoc), "records": multidoc},
        "injection_control": {"four_b": injection[0]["four_b"]["validator_pass"] if injection else None, "nine_b": injection[0]["nine_b"]["validator_pass"] if injection else None, "expected_control_failures": 0},
        "latency_ratio": {"median": statistics.median(ratios) if ratios else None, "max": max(ratios) if ratios else None},
        "full_development": False, "calibration": False, "frozen_test_touched": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "query-selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "qwen35-4b-results.json").write_text(json.dumps({"model": "qwen3.5:4b", "results": four_b, "metrics": four_metrics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "qwen35-9b-results.json").write_text(json.dumps({"model": MODEL, "results": nine_b, "metrics": nine_metrics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "per-query-comparison.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in comparisons) + "\n", encoding="utf-8")
    (OUT / "multidoc-comparison.json").write_text(json.dumps(summary["multi_document"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, value in (("hard-comparison.json", [row for row in comparisons if row["four_b"]["category"] == "hard_answerable"]), ("cross-lingual-comparison.json", [row for row in comparisons if row["four_b"]["category"] == "cross_lingual"]), ("authority-comparison.json", [row for row in comparisons if row["four_b"]["category"] == "version_conflict"]), ("citation-comparison.json", {"four_b": four_metrics, "nine_b": nine_metrics}), ("latency-comparison.json", {"four_b": four_metrics["latency_ms"], "nine_b": nine_metrics["latency_ms"], "ratios": ratios})):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decision = _decision(summary)
    (OUT / "report.md").write_text(_report(summary, decision, selection), encoding="utf-8")


def _decision(summary: dict[str, Any]) -> str:
    four, nine = summary["four_b"], summary["nine_b"]
    if nine["validator_failures"] > four["validator_failures"] or nine["unsupported_or_contradicted"] > four["unsupported_or_contradicted"]:
        return "9B_REGRESSION"
    if summary["multi_document"]["nine_b_full"] > summary["multi_document"]["four_b_full"] and nine["latency_ms"]["p95"] and four["latency_ms"]["p95"] and nine["latency_ms"]["p95"] > 2 * four["latency_ms"]["p95"]:
        return "9B_QUALITY_GAIN_TOO_EXPENSIVE"
    if summary["outcomes"].get("IMPROVED", 0) >= 3:
        return "9B_CAPACITY_GAIN_STRONG"
    if summary["outcomes"].get("IMPROVED", 0) > 0:
        return "9B_CAPACITY_GAIN_MODEST"
    return "9B_NO_MEANINGFUL_GAIN"


def _report(summary: dict[str, Any], decision: str, selection: dict[str, Any]) -> str:
    return f"""# Phase 7.3 qwen3.5:4b vs qwen3.5:9b Capacity Probe

Cache-only comparison on the fixed 12-query selection. The 4B output was reused; 9B was run exactly {summary['calls']['nine_b_generation']} times. Retrieval and semantic evaluators were not invoked.

## Identity and controls

- Corpus: `{summary['identity']['corpus_fingerprint']}`; dataset: `{summary['identity']['dataset_fingerprint']}`
- Collection: `{summary['identity']['collection']}`; candidate_k `{summary['identity']['candidate_k']}`; top_n `{summary['identity']['top_n']}`
- Prompt `{PROMPT}`, think `false`; retrieval calls `0`; semantic evaluator calls `0`
- Selection composition: `{selection['composition']}`

## Results

- 4B fully correct/complete: `{summary['four_b']['fully_correct_complete']}/12`
- 9B fully correct/complete: `{summary['nine_b']['fully_correct_complete']}/12`
- Multi-document full: 4B `{summary['multi_document']['four_b_full']}/3`, 9B `{summary['multi_document']['nine_b_full']}/3`
- Validator failures: 4B `{summary['four_b']['validator_failures']}`, 9B `{summary['nine_b']['validator_failures']}`
- Generation p95: 4B `{summary['four_b']['latency_ms']['p95']}` ms; 9B `{summary['nine_b']['latency_ms']['p95']}` ms
- Median latency ratio: `{summary['latency_ratio']['median']}`

## Decision

**{decision}**. This is a small capacity probe, not a production model decision. Runtime defaults, retrieval, prompt, validator, ACL, and Phase 6 gate state remain unchanged.
"""


def finalize_inconclusive() -> int:
    """Persist an honest interrupted-probe record without invoking anything."""
    metadata, generation, cache_rows, questions = validate_probe_cache()
    cache = {row["query_id"]: row for row in cache_rows}
    selection = build_selection_artifact(metadata, generation, questions)
    four_b = _four_b_rows(generation, cache, questions)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "query-selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "qwen35-4b-results.json").write_text(json.dumps({"model": "qwen3.5:4b", "reused": True, "results": four_b, "metrics": _metrics(four_b)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "qwen35-9b-results.json").write_text(json.dumps({"model": MODEL, "status": "INTERRUPTED_BEFORE_FIRST_COMPLETED_CALL", "completed_calls": 0}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, value in (("per-query-comparison.jsonl", ""), ("multidoc-comparison.json", {"status": "INCONCLUSIVE", "records": []}), ("hard-comparison.json", {"status": "INCONCLUSIVE", "records": []}), ("cross-lingual-comparison.json", {"status": "INCONCLUSIVE", "records": []}), ("authority-comparison.json", {"status": "INCONCLUSIVE", "records": []}), ("citation-comparison.json", {"status": "INCONCLUSIVE"}), ("latency-comparison.json", {"status": "INCONCLUSIVE"})):
        path = OUT / name
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": "CAPACITY_PROBE_INCONCLUSIVE", "identity": {key: metadata.get(key) for key in EXPECTED_CACHE},
        "models": {"four_b": "qwen3.5:4b", "nine_b": MODEL},
        "calls": {"four_b_generation": 0, "nine_b_generation": 0, "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "selection": selection, "four_b_metrics": _metrics(four_b), "nine_b_metrics": None,
        "interrupted": True, "full_development": False, "calibration": False, "frozen_test_touched": False,
        "reason": "9B endpoint/model was available, but the first generation call did not complete before the operator stopped the probe.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "report.md").write_text(f"""# Phase 7.3 qwen3.5 capacity probe

Status: **CAPACITY_PROBE_INCONCLUSIVE**.

The locked Phase 7 cache was validated and the deterministic 12-query selection was written. Existing qwen3.5:4b outputs were reused; no 4B generation was rerun. The exact qwen3.5:9b model was locally available, but its first generation call did not complete before the operator stopped the probe. Therefore no 9B quality or latency claim is made.

- Cache: `{metadata['corpus_fingerprint']}` / `{metadata['dataset_fingerprint']}`
- Retrieval calls: `0`; embedding/reranker/semantic evaluator calls: `0`
- 4B generation calls: `0`; 9B completed generation calls: `0`
- Prompt: `{PROMPT}`; think: `false`; retrieval cache reused: `true`
- Selection: `{selection['composition']}`
- Full 36/development 200/calibration/frozen test: not run

The probe remains safe to resume with the same selection and cache after a bounded-generation/latency decision. Runtime defaults remain unchanged.
""", encoding="utf-8")
    print(json.dumps({"status": "CAPACITY_PROBE_INCONCLUSIVE", "nine_b_completed_calls": 0, "new_inference_calls": 0}))
    return 0


async def run() -> int:
    metadata, generation, cache_rows, questions = validate_probe_cache()
    questions_by_id = questions
    cache = {row["query_id"]: row for row in cache_rows}
    selection = build_selection_artifact(metadata, generation, questions_by_id)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "query-selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    availability = OllamaClient(base_url=Settings.benchmark_reference().ollama_base_url)
    try:
        if not await _model_available(availability):
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: {MODEL}")
    finally:
        await availability.aclose()
    settings = Settings.benchmark_reference()
    selected_records = [cache[query_id] for query_id, _, _ in SELECTION]
    nine_b = await _run_nine_b(selected_records, questions_by_id, settings)
    four_b = _four_b_rows(generation, cache, questions_by_id)
    build_outputs(metadata, four_b, nine_b, cache, questions_by_id, selection)
    print(json.dumps({"status": "COMPLETED", "model": MODEL, "query_count": len(nine_b), "retrieval_calls": 0}))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize-inconclusive", action="store_true")
    args = parser.parse_args()
    raise SystemExit(finalize_inconclusive() if args.finalize_inconclusive else asyncio.run(run()))


if __name__ == "__main__":
    main()
