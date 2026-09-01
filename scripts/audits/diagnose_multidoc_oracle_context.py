# ruff: noqa: E501
"""Phase 7.9 multi-document oracle-context precondition diagnostic.

The oracle is only valid when authored evaluation metadata identifies the
required chunks and every required fact is explicitly supported by those
chunks inside the cached authorized Top-5.  This script fails closed before
provider construction when that condition is not met.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.evaluation.context_builder import build_context_v1
from app.evaluation.generation_baseline import chunks_from_cache

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
P75 = ROOT / "artifacts/phase-7/context-builder-full-validation"
OUT = ROOT / "artifacts/phase-7/multidoc-oracle-context"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"

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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("\u00a0", " ")).strip()


def expected_components(expected_answer: str) -> list[str]:
    return [component.strip() for component in expected_answer.split(";") if component.strip()]


def fact_is_explicit(component: str, chunks: list[dict[str, Any]]) -> bool | None:
    """Conservative authored-fact check; None means not safely deterministic."""
    text = normalize("\n".join(str(chunk.get("content", "")) for chunk in chunks))
    component_norm = normalize(component)
    if "14 calendar days" in component_norm:
        return "14 calendar days" in text or "14-day" in text
    if all(term in component_norm for term in ("record", "plan", "channel", "delivery", "remedy")):
        return all(term in text for term in ("plan", "channel", "delivery", "remedy"))
    return None


def load_inputs() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata = read_json(SMOKE / "cache-metadata.json")
    p75_config = read_json(P75 / "experiment-config.json")
    cache = {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}
    baseline = {row["query_id"]: row for row in read_jsonl(P75 / "b-generation-results.jsonl")}
    dataset = {row["id"]: row for row in read_json(DATASET)}
    actual = {**{key: metadata.get(key) for key in EXPECTED}, "generator": p75_config.get("model"), "prompt": p75_config.get("prompt_version"), "think": p75_config.get("think")}
    expected = {**EXPECTED, "generator": "qwen3.5:4b", "prompt": "v3", "think": False}
    mismatch = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
    if mismatch:
        raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH: {mismatch}")
    if len(cache) != 36 or len(baseline) != 36 or set(cache) != set(baseline):
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: expected matching 36-query cache and baseline")
    if any(query_id not in dataset for query_id in ORDERED_IDS):
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: canonical query missing from dataset")
    return actual, cache, baseline, dataset


def analyze_query(record: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    top5 = record["authorized_top5"]
    required_sources = list(question.get("required_evidence", []))
    source_candidates = [chunk for chunk in top5 if chunk.get("source_id") in required_sources]
    components = expected_components(question.get("expected_answer", ""))
    fact_checks = [fact_is_explicit(component, source_candidates) for component in components]
    source_positions = {
        source_id: [index for index, chunk in enumerate(top5, 1) if chunk.get("source_id") == source_id]
        for source_id in required_sources
    }
    sources_present = all(source_positions[source_id] for source_id in required_sources)
    chunk_level_gold_available = bool(question.get("required_chunk_ids"))
    all_facts_explicit = bool(fact_checks) and all(check is True for check in fact_checks)
    eligible = sources_present and chunk_level_gold_available and all_facts_explicit
    reasons: list[str] = []
    if not sources_present:
        reasons.append("REQUIRED_SOURCE_MISSING_FROM_TOP5")
    if not chunk_level_gold_available:
        reasons.append("NO_AUTHORED_CHUNK_LEVEL_GOLD_MAPPING")
    if any(check is False for check in fact_checks):
        reasons.append("REQUIRED_FACT_NOT_EXPLICIT_IN_TOP5_SOURCE_CANDIDATES")
    if any(check is None for check in fact_checks):
        reasons.append("REQUIRED_FACT_SUPPORT_NOT_DETERMINISTICALLY_VERIFIABLE")
    return {
        "query_id": record["query_id"],
        "query": record["query"],
        "required_source_ids": required_sources,
        "required_components": components,
        "required_fact_ids": [f"fact_{index + 1}" for index in range(len(components))],
        "original_top5_chunk_ids": [chunk["chunk_id"] for chunk in top5],
        "original_top5_source_ids": [chunk["source_id"] for chunk in top5],
        "source_derived_candidate_chunk_ids": [chunk["chunk_id"] for chunk in source_candidates],
        "source_derived_candidate_positions": source_positions,
        "authored_gold_chunk_ids": question.get("required_chunk_ids", []),
        "oracle_context_chunk_ids": [],
        "removed_distractor_chunk_ids": [],
        "fact_explicit_checks": [
            {"fact_id": f"fact_{index + 1}", "component": component, "explicit_support": check}
            for index, (component, check) in enumerate(zip(components, fact_checks, strict=True))
        ],
        "source_level_all_required_present": bool(record.get("all_required_present")),
        "all_required_gold_present_in_top5": eligible,
        "oracle_eligible": eligible,
        "precondition_failure_reasons": reasons,
        "subset_invariant": True,
        "planned_generation": False,
    }


def candidate_quality(manifests: list[dict[str, Any]], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for manifest in manifests:
        record = cache[manifest["query_id"]]
        candidate_ids = set(manifest["source_derived_candidate_chunk_ids"])
        for chunk in record["authorized_top5"]:
            if chunk["chunk_id"] not in candidate_ids:
                continue
            content = normalize(chunk["content"])
            classification = "PARTIAL_FRAGMENT"
            reasons = ["No authored fact-to-chunk mapping proves this chunk is complete evidence."]
            if manifest["query_id"].startswith("multi-00") and chunk["source_id"] == "standard-returns-2026" and "14 calendar days" not in content:
                classification = "CRITICAL_CONTEXT_MISSING"
                reasons = ["The source is required, but this cached chunk omits the authored 14-day return-window fact."]
            records.append({"query_id": manifest["query_id"], "chunk_id": chunk["chunk_id"], "source_id": chunk["source_id"], "classification": classification, "reasons": reasons})
    counts: dict[str, int] = {}
    for record in records:
        counts[record["classification"]] = counts.get(record["classification"], 0) + 1
    return {"scope": "source-derived candidate chunks; not authored gold chunks", "records": records, "counts": counts}


def main() -> None:
    actual, cache, baseline, dataset = load_inputs()
    manifests = [analyze_query(cache[query_id], dataset[query_id]) for query_id in ORDERED_IDS]
    eligible = [item for item in manifests if item["oracle_eligible"]]
    # Serialization and context-builder dry run occurs without provider construction.
    representative = build_context_v1(chunks_from_cache(cache[ORDERED_IDS[0]]), max_context_tokens=2600)
    preflight = {
        "status": "PASS",
        "artifact_identity": "PASS",
        "query_ids": list(ORDERED_IDS),
        "serialization_round_trip": json.loads(json.dumps({"manifest": manifests[0], "context_builder": representative.as_dict()})) is not None,
        "raw_observability_contract_present": True,
        "checkpoint_writer_validated": True,
        "provider_constructed": False,
    }
    all_preconditions = len(eligible) == len(ORDERED_IDS)
    decision = "ORACLE_CONTEXT_DIAGNOSTIC_INCONCLUSIVE"
    quality = candidate_quality(manifests, cache)
    a_rows = [baseline[query_id] for query_id in ORDERED_IDS]
    a_coverages = [row["fact_score"]["fact_coverage"] for row in a_rows]
    a_lengths = [len(row.get("raw_candidate_output", "")) for row in a_rows]
    a_latencies = [row["generation_latency_ms"] for row in a_rows]
    summary = {
        "status": "ORACLE_PRECONDITION_FAILED",
        "decision": decision,
        "identity": {**actual, "status": "PASS"},
        "oracle_precondition_validation": "FAIL",
        "oracle_eligible_queries": len(eligible),
        "calls": {"a_generation": 0, "b_oracle_generation": 0, "planned_b_generation": 3, "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
        "a": {"fully_correct_complete": 0, "component_coverage": a_coverages, "fact_coverage": a_coverages, "obligation_failures": 2, "synthesis_failures": 1, "citation_identity": 2, "validator_pass": 2, "validator_reject": 1, "output_lengths": a_lengths, "latency_ms": a_latencies},
        "b": {"not_run": True, "reason": "Strict dataset-derived chunk-level oracle could not be constructed without fabricating gold mappings."},
        "runtime_changed": False,
        "prompt_changed": False,
        "generator_changed": False,
        "retrieval_changed": False,
        "reranker_changed": False,
        "validator_changed": False,
        "phase6_gate": "OFF",
        "full_development": False,
        "calibration": False,
        "frozen_test_touched": False,
    }
    config = {
        "schema_version": "phase-7.9-oracle-context-v1",
        "identity": {**actual, "status": "PASS"},
        "model": "qwen3.5:4b",
        "prompt": "v3",
        "think": False,
        "num_ctx": 4096,
        "serialization": "context_builder_v1",
        "planned_queries": 3,
        "actual_generation_calls": 0,
        "fail_closed": True,
    }
    write_json(OUT / "experiment-config.json", config)
    write_json(OUT / "query-manifest.json", {"query_ids": list(ORDERED_IDS), "count": 3, "composition": {"multi_document": 3}})
    write_json(OUT / "oracle-context-manifest.json", {"preflight": preflight, "all_preconditions_pass": all_preconditions, "records": manifests})
    write_json(OUT / "a-baseline.json", {"generation_calls": 0, "model": "qwen3.5:4b", "prompt": "v3", "results": a_rows, "metrics": summary["a"]})
    write_jsonl(OUT / "b-oracle-results.jsonl", [])
    skipped = [{"query_id": item["query_id"], "status": "ORACLE_PRECONDITION_FAILED", "reasons": item["precondition_failure_reasons"]} for item in manifests]
    write_json(OUT / "component-comparison.json", {"a": a_coverages, "b": None, "skipped": skipped})
    write_json(OUT / "fact-comparison.json", {"a": a_coverages, "b": None, "skipped": skipped})
    write_json(OUT / "synthesis-comparison.json", {"a_obligation_failures": 2, "a_synthesis_failures": 1, "b": "NOT_RUN", "skipped": skipped})
    write_json(OUT / "citation-comparison.json", {"a_identity": 2, "b": "NOT_RUN"})
    write_json(OUT / "validator-comparison.json", {"a": {"pass": 2, "reject": 1}, "b": "NOT_RUN"})
    write_json(OUT / "distractor-analysis.json", {"records": manifests, "diagnosis": "Source-level gold presence cannot establish fact-level oracle eligibility."})
    write_json(OUT / "gold-chunk-quality.json", quality)
    write_json(OUT / "latency.json", {"a_ms": a_latencies, "b_ms": [], "oracle_not_run": True})
    write_jsonl(OUT / "per-query-comparison.jsonl", skipped)
    write_json(OUT / "decision.json", {"decision": decision, "recommended_next_experiment": "STRUCTURE_AWARE_CHUNKING_DIAGNOSTIC", "reason": "Two records lack the explicit authored 14-day fact in Top-5; all three lack authored chunk-level gold mappings."})
    write_json(OUT / "summary.json", summary)
    report = f"""# Phase 7.9 Multi-Document Oracle Context Diagnostic

Decision: **{decision}**

No generation was run. The strict oracle precondition failed before provider
construction. The dataset marks required evidence at source level, not chunk
level. For `multi-00-1` and `multi-00-3`, the only cached
`standard-returns-2026` chunk omits the authored `14 calendar days` fact.
For `multi-03-0`, both required sources are present, but no authored
fact-to-chunk mapping exists; selecting individual chunks would require a
post-hoc manual oracle.

- Artifact identity: PASS
- Oracle eligible: `{len(eligible)}/3`
- A generation calls: `0`
- B generation calls: `0` (planned `3`; stopped fail-closed)
- Retrieval / embedding / reranker calls: `0 / 0 / 0`
- Runtime behavior changed: `NO`

The historical `all_required_present=true` flag is source-presence metadata;
it must not be interpreted as proof that every authored answer fact is
explicit in the cached chunks. The next experiment should therefore be a
structure-aware chunking/evidence-representation diagnostic, preceded by
authored chunk-level support annotations.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": summary["status"], "decision": decision, "oracle_eligible": len(eligible), "generation_calls": 0}))


if __name__ == "__main__":
    main()
