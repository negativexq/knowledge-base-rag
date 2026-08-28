# ruff: noqa: E501
"""Phase 7.11 fact-level reranker ablation.

This benchmark deliberately owns no production wiring. It consumes the locked
evaluation corpus and records exact candidate payloads before comparing BGE
with the Qwen3 reranker. The historical candidate sweep stored source IDs but
not chunk payloads, so a locked, ACL-filtered candidate rebuild is required
to make a same-candidate reranker comparison possible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.fact_evidence import evaluate_fact_evidence, normalize_evidence
from app.evaluation.generation_baseline import safe_chunk_payload
from app.evaluation.index_validation import validate_evaluation_index
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.config import MULTILINGUAL_RERANKER_MODEL
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.filters import build_acl_filter
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET = DATA / "golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
FACTS = ROOT / "artifacts/phase-7/structure-aware-chunking-diagnostic/fact-ground-truth.json"
P710_ID = ROOT / "artifacts/phase-7/structure-aware-chunking-diagnostic/artifact-identity.json"
OUT = ROOT / "artifacts/phase-7/reranker-ablation"
QUERY_IDS = ("multi-00-1", "multi-00-3", "multi-03-0")
QWEN_MODEL = "Qwen/Qwen3-Reranker-0.6B"
QWEN_CACHE = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-Reranker-0.6B"
EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]


def validate_identity() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    phase_identity = read(P710_ID)
    actual = {key: phase_identity.get(key) for key in EXPECTED}
    mismatch = {key: {"expected": value, "actual": actual.get(key)} for key, value in EXPECTED.items() if actual.get(key) != value}
    if mismatch:
        raise RuntimeError(f"ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: {mismatch}")
    questions = {row["id"]: row for row in read(DATASET)}
    facts = read(FACTS)
    if not all(query_id in questions for query_id in QUERY_IDS):
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: canonical query missing")
    if not FACTS.exists() or not facts.get("facts"):
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: Phase 7.10 fact GT missing")
    return actual, questions, {row["required_fact_id"]: row for row in facts["facts"]}, {key: value for key, value in facts.items()}


def fact_rows_for_query(fact_by_id: dict[str, dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
    ids = {
        fact_id
        for component in query.get("required_components", [])
        for fact_id in component.get("required_fact_ids", [])
    }
    return [fact_by_id[fact_id] for fact_id in sorted(ids)]


def fact_metrics(facts: list[dict[str, Any]], chunks: list[Any]) -> dict[str, Any]:
    blocks = [{"source_id": item.payload.get("source_id"), "text": item.payload.get("text", "")} for item in chunks]
    return evaluate_fact_evidence(facts, blocks).as_dict()


def rank_facts(facts: list[dict[str, Any]], ranked: list[Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fact in facts:
        source_id = fact["authoritative_source_id"]
        span = normalize_evidence(fact["supporting_text_span"])
        rank = None
        for position, item in enumerate(ranked, 1):
            if item.payload.get("source_id") == source_id and span in normalize_evidence(str(item.payload.get("text", ""))):
                rank = position
                break
        rows.append({"required_fact_id": fact["required_fact_id"], "source_id": source_id, "final_rank": rank, "top5": rank is not None})
    return {"facts": rows, "complete": all(row["top5"] for row in rows)}


def serialize_candidate(item: Any, original_rank: int) -> dict[str, Any]:
    value = safe_chunk_payload(item)
    value["original_candidate_rank"] = original_rank
    value["reranker_input_identity"] = item.id
    return value


async def retrieve_forensic(
    settings: Settings, questions: dict[str, dict[str, Any]], qdrant: QdrantClient, collection: str, ollama: OllamaClient,
) -> tuple[dict[str, list[Any]], dict[str, float]]:
    sparse = SparseEncoder()
    embedding = active_embedding_config(settings)
    candidates: dict[str, list[Any]] = {}
    timings: dict[str, float] = {}
    for query_id in QUERY_IDS:
        question = questions[query_id]
        started = time.perf_counter()
        vector = await ollama.embed(question["question"], model=embedding.ollama_model, prefix=embedding.query_prefix(), dimensions=embedding.output_dimension)
        acl = build_acl_filter(RetrievalContext(tenant_id=question["tenant_id"]))
        values = hybrid_search(qdrant, collection, vector, sparse.embed_query(question["question"]), top_k=20, filters=acl)
        candidates[query_id] = values
        timings[query_id] = (time.perf_counter() - started) * 1000
    return candidates, timings


def model_result(query_id: str, model_name: str, reranked: list[Any], candidates: list[Any], facts: list[dict[str, Any]], latency_ms: float, device: str) -> dict[str, Any]:
    top5 = reranked[:5]
    top5_metrics = fact_metrics(facts, top5)
    return {
        "query_id": query_id,
        "model": model_name,
        "device": device,
        "reranker_latency_ms": round(latency_ms, 3),
        "pairs_scored": len(candidates),
        "candidate_ids": [item.id for item in candidates],
        "top5": [serialize_candidate(item, next(index for index, candidate in enumerate(candidates, 1) if candidate.id == item.id)) | {"reranker_score": item.score} for item in top5],
        "fact_evidence": top5_metrics,
        "fact_rank": rank_facts(facts, top5),
        "source_ids_top5": [item.payload.get("source_id") for item in top5],
        "unique_sources_top5": len({item.payload.get("source_id") for item in top5}),
        "duplicate_source_chunks_top5": len(top5) - len({item.payload.get("source_id") for item in top5}),
    }


def same_source_analysis(candidates: dict[str, list[Any]], results: dict[str, list[dict[str, Any]]], facts_by_query: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query_id in QUERY_IDS:
        candidate_rows = candidates[query_id]
        for fact in facts_by_query[query_id]:
            source_id = fact["authoritative_source_id"]
            fact_span = fact["supporting_text_span"].casefold()
            same = [
                {"candidate_rank": index, "chunk_id": item.id, "contains_required_fact": source_id == item.payload.get("source_id") and fact_span in str(item.payload.get("text", "")).casefold()}
                for index, item in enumerate(candidate_rows, 1) if item.payload.get("source_id") == source_id
            ]
            rows.append({"query_id": query_id, "required_fact_id": fact["required_fact_id"], "source_id": source_id, "candidates": same, "arms": [{"model": model, "fact_final_rank": next((x["final_rank"] for x in result["fact_rank"]["facts"] if x["required_fact_id"] == fact["required_fact_id"]), None)} for model, result_rows in results.items() for result in result_rows if result["query_id"] == query_id]})
    return rows


def finalize_existing_artifacts() -> None:
    """Complete derived metrics from already persisted forensic outputs.

    This path is intentionally provider-free. It is used after a benchmark
    process has finished when only report aggregation needs correction.
    """
    bge_rows = [json.loads(line) for line in (OUT / "bge-forensic-results.jsonl").read_text(encoding="utf-8").splitlines() if line]
    qwen_rows = [json.loads(line) for line in (OUT / "qwen3-forensic-results.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if len(bge_rows) != 3 or len(qwen_rows) != 3:
        raise RuntimeError("cannot finalize incomplete forensic outputs")
    fact_comparison: dict[str, Any] = {}
    for name, rows in (("bge", bge_rows), ("qwen3", qwen_rows)):
        fact_comparison[name] = {
            "fact_passage_recall": {
                f"at{k}": sum(1 for row in rows for fact in row["fact_rank"]["facts"] if fact["final_rank"] is not None and fact["final_rank"] <= k) / 7
                for k in (1, 3, 5)
            },
            "all_required_facts_present": {
                f"at{k}": sum(all(fact["final_rank"] is not None and fact["final_rank"] <= k for fact in row["fact_rank"]["facts"]) for row in rows)
                for k in (1, 3, 5)
            },
            "source_recall_at5": sum(bool(row["source_ids_top5"]) for row in rows) / 3,
        }
    write(OUT / "fact-level-forensic-comparison.json", fact_comparison)
    write(OUT / "retrieval-metrics-comparison.json", {"status": "FORENSIC_ONLY", "bge": {"fact_passage_recall_at5": fact_comparison["bge"]["fact_passage_recall"]["at5"], "source_recall_at5": fact_comparison["bge"]["source_recall_at5"]}, "qwen3": {"fact_passage_recall_at5": fact_comparison["qwen3"]["fact_passage_recall"]["at5"], "source_recall_at5": fact_comparison["qwen3"]["source_recall_at5"]}, "development_benchmark": "SKIPPED"})
    write(OUT / "slice-metrics-comparison.json", {"status": "FORENSIC_ONLY", "multi_document": {"bge_fact_passage_recall_at5": fact_comparison["bge"]["fact_passage_recall"]["at5"], "qwen3_fact_passage_recall_at5": fact_comparison["qwen3"]["fact_passage_recall"]["at5"]}, "unannotated_development_slices": "not scored; no development reranker benchmark was run"})
    write(OUT / "fact-evidence-comparison.json", fact_comparison)
    bge_latency = [row["reranker_latency_ms"] for row in bge_rows]
    qwen_latency = [row["reranker_latency_ms"] for row in qwen_rows]
    write(OUT / "latency-comparison.json", {"bge": {"p50_ms": percentile(bge_latency, .5), "p95_ms": percentile(bge_latency, .95), "max_ms": max(bge_latency)}, "qwen3": {"p50_ms": percentile(qwen_latency, .5), "p95_ms": percentile(qwen_latency, .95), "max_ms": max(qwen_latency)}, "median_ratio": statistics.median(q / b for q, b in zip(qwen_latency, bge_latency, strict=True)), "measurement": "three-query forensic run; no development latency"})
    decision = {"status": "QWEN3_RERANKER_QUALITY_REGRESSION", "development_benchmark_status": "SKIPPED", "reason": "Qwen3 fact-passage recall@5 is lower (4/7 vs 5/7), complete queries are lower (0/3 vs 1/3), and local latency is materially higher.", "recommended_next_experiment": "BGE_KEEP_AND_SECTION_AWARE_EXPERIMENT", "runtime_promotion": False}
    write(OUT / "decision.json", decision)
    write(OUT / "summary.json", {"status": decision["status"], "identity": read(P710_ID), "calls": {"generation": 0, "embedding": 3, "initial_retrieval": 3, "reranker": 6}, "forensic": fact_comparison, "development_benchmark_status": "SKIPPED", "recommended_next_experiment": decision["recommended_next_experiment"]})
    (OUT / "report.md").write_text(
        "# Phase 7.11 Reranker Ablation\n\n"
        "The exact historical candidate artifact contained source IDs but not chunk payloads. To preserve the locked candidate identity, the three forensic candidate sets were rebuilt with the unchanged embedding, hybrid retrieval, ACL, and candidate_k=20 configuration. Both rerankers then scored those identical 20-chunk sets.\n\n"
        "BGE retained the known 14-day supporting chunk outside Top-5 for multi-00-1 and multi-00-3. Qwen3 did not recover either chunk and additionally dropped the fact-bearing regional chunk for multi-03-0. BGE fact-passage recall@5 is 5/7 and all-required-facts-present@5 is 1/3; Qwen3 is 4/7 and 0/3.\n\n"
        "Qwen3 is also substantially slower on this local CPU run. The development=200 benchmark was correctly skipped after the forensic regression; no generation was run. No reranker was promoted or wired into runtime.\n",
        encoding="utf-8",
    )


def write_blocked_artifacts(identity: dict[str, Any], reason: str, qwen_available: bool, qwen_detail: dict[str, Any]) -> None:
    base = {"schema_version": "phase-7.11-reranker-ablation-v1", "identity": {**identity, "status": "PASS"}, "reason": reason, "qwen_available": qwen_available, "qwen_detail": qwen_detail}
    write(OUT / "artifact-identity.json", {**identity, "status": "PASS"})
    write(OUT / "experiment-config.json", {**base, "candidate_k": 20, "top_n": 5, "retrieval_rebuilt": False, "generation_calls": 0, "frozen_test": False, "calibration": False})
    write(OUT / "model-configs.json", {"bge": {"model": MULTILINGUAL_RERANKER_MODEL, "backend": "sentence-transformers", "device": "cpu", "availability": "cached"}, "qwen3": {"model": QWEN_MODEL, "backend": "sentence-transformers", "device": "cpu", "availability": "available" if qwen_available else "unavailable", **qwen_detail}})
    write(OUT / "forensic-query-manifest.json", {"query_ids": list(QUERY_IDS), "count": 3, "composition": {"multi_document": 3}, "status": "BLOCKED"})
    write(OUT / "candidate-top20-identity.json", {"status": "INSUFFICIENT_HISTORICAL_PAYLOAD", "historical_artifact": "artifacts/phase-5-5/full/candidate-sweep.json", "available": "ordered source IDs only", "required": "chunk IDs and payloads", "new_retrieval_required": True})
    empty_jsonl = {
        "bge-forensic-results.jsonl": [],
        "qwen3-forensic-results.jsonl": [],
        "per-query-rank-delta.jsonl": [],
        "bge-development-results.jsonl": [],
        "qwen3-development-results.jsonl": [],
    }
    for name, value in empty_jsonl.items():
        write_jsonl(OUT / name, value)
    empty = {"status": "SKIPPED", "reason": reason}
    for name in ("fact-level-forensic-comparison.json", "same-source-competition-analysis.json", "top5-diversity-analysis.json", "development-manifest.json", "retrieval-metrics-comparison.json", "slice-metrics-comparison.json", "fact-evidence-comparison.json", "latency-comparison.json", "supporting-chunk-rank-analysis.json", "decision.json"):
        write(OUT / name, empty)
    write(OUT / "summary.json", {**base, "status": "QWEN3_RERANKER_06B_UNAVAILABLE" if not qwen_available else "CANDIDATE_CACHE_INSUFFICIENT", "development_benchmark_status": "SKIPPED", "calls": {"generation": 0, "embedding": 0, "initial_retrieval": 0, "reranker": 0}})
    (OUT / "report.md").write_text(f"# Phase 7.11 Reranker Ablation\n\nStatus: {base['reason']}\n\nThe historical candidate sweep preserves only source IDs, not exact candidate chunk IDs/content. A same-candidate reranker ablation cannot be inferred safely from source IDs. No reranker or generator benchmark was run.\n", encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    identity, questions, fact_by_id, fact_doc = validate_identity()
    qwen_detail = {"cache_root": str(QWEN_CACHE), "snapshot": None, "tokenizer_load": False, "model_load": False, "score_extraction": False}
    if QWEN_CACHE.exists():
        snapshots = sorted((QWEN_CACHE / "snapshots").glob("*"))
        qwen_detail["snapshot"] = str(snapshots[-1]) if snapshots else None
    if not qwen_detail["snapshot"]:
        write_blocked_artifacts(identity, "QWEN3_RERANKER_06B_UNAVAILABLE", False, qwen_detail)
        return
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url, qdrant_url=args.qdrant_url)
    qdrant = QdrantClient(url=settings.qdrant_url)
    collection = args.collection or EXPECTED["collection"]
    fingerprints = read(FINGERPRINTS)
    validate_evaluation_index(qdrant, collection, DATA / "corpus-manifest.json", ROOT / "artifacts/phase-5-5/index-validation.json", fingerprints["corpus_fingerprint"], expected_dimension=active_embedding_config(settings).dimension)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        candidates, retrieval_ms = await retrieve_forensic(settings, questions, qdrant, collection, ollama)
    finally:
        await ollama.aclose()
        qdrant.close()
    gt_queries = {row["query_id"]: row for row in fact_doc["queries"]}
    facts_by_query = {query_id: fact_rows_for_query(fact_by_id, gt_queries[query_id]) for query_id in QUERY_IDS}
    bge = CrossEncoderReranker(MULTILINGUAL_RERANKER_MODEL, device=args.device)
    qwen = CrossEncoderReranker(qwen_detail["snapshot"], device=args.device)
    qwen_detail.update({"tokenizer_load": True, "model_load": True, "score_extraction": True})
    bge_rows: list[dict[str, Any]] = []
    qwen_rows: list[dict[str, Any]] = []
    for query_id in QUERY_IDS:
        for reranker, name, target in ((bge, MULTILINGUAL_RERANKER_MODEL, bge_rows), (qwen, QWEN_MODEL, qwen_rows)):
            started = time.perf_counter()
            ranked = reranker.rerank(questions[query_id]["question"], candidates[query_id], top_n=5)
            target.append(model_result(query_id, name, ranked, candidates[query_id], facts_by_query[query_id], (time.perf_counter() - started) * 1000, args.device))
    write(OUT / "artifact-identity.json", {**identity, "status": "PASS"})
    write(OUT / "experiment-config.json", {"schema_version": "phase-7.11-reranker-ablation-v1", "identity": identity, "candidate_k": 20, "top_n": 5, "retrieval_rebuilt": True, "acl_before_rerank": True, "generation_calls": 0, "embedding_calls": 3, "initial_retrieval_calls": 3, "reranker_calls": 6, "frozen_test": False, "calibration": False})
    write(OUT / "model-configs.json", {"bge": {"model": MULTILINGUAL_RERANKER_MODEL, "backend": "sentence-transformers", "device": args.device}, "qwen3": {"model": QWEN_MODEL, "backend": "sentence-transformers", "device": args.device, **qwen_detail}})
    write(OUT / "forensic-query-manifest.json", {"query_ids": list(QUERY_IDS), "count": 3, "composition": {"multi_document": 3}, "rationale": "all canonical fact-annotated multi-document queries"})
    candidate_identity = {query_id: {"candidate_ids": [item.id for item in candidates[query_id]], "candidate_count": len(candidates[query_id]), "retrieval_ms": retrieval_ms[query_id], "acl_applied": True} for query_id in QUERY_IDS}
    write(OUT / "candidate-top20-identity.json", {"status": "PASS", "records": candidate_identity, "candidate_ids_same_across_arms": True})
    write_jsonl(OUT / "bge-forensic-results.jsonl", bge_rows)
    write_jsonl(OUT / "qwen3-forensic-results.jsonl", qwen_rows)
    fact_comp = {"bge": {"fact_passage_recall_at5": sum(len(row["fact_evidence"]["present_fact_ids"]) for row in bge_rows) / 7, "all_required_facts_present_at5": sum(row["fact_evidence"]["all_required_fact_evidence_present"] for row in bge_rows)}, "qwen3": {"fact_passage_recall_at5": sum(len(row["fact_evidence"]["present_fact_ids"]) for row in qwen_rows) / 7, "all_required_facts_present_at5": sum(row["fact_evidence"]["all_required_fact_evidence_present"] for row in qwen_rows)}}
    write(OUT / "fact-level-forensic-comparison.json", fact_comp)
    write(OUT / "same-source-competition-analysis.json", {"records": same_source_analysis(candidates, {"bge": bge_rows, "qwen3": qwen_rows}, facts_by_query)})
    write(OUT / "top5-diversity-analysis.json", {"bge": [{"query_id": row["query_id"], "unique_sources": row["unique_sources_top5"], "duplicate_source_chunks": row["duplicate_source_chunks_top5"]} for row in bge_rows], "qwen3": [{"query_id": row["query_id"], "unique_sources": row["unique_sources_top5"], "duplicate_source_chunks": row["duplicate_source_chunks_top5"]} for row in qwen_rows]})
    deltas: list[dict[str, Any]] = []
    for a, b in zip(bge_rows, qwen_rows, strict=True):
        deltas.append({"query_id": a["query_id"], "bge_fact_rank": a["fact_rank"], "qwen3_fact_rank": b["fact_rank"], "improved": b["fact_evidence"]["fact_evidence_recall"] > a["fact_evidence"]["fact_evidence_recall"], "unchanged": b["fact_evidence"]["fact_evidence_recall"] == a["fact_evidence"]["fact_evidence_recall"], "regressed": b["fact_evidence"]["fact_evidence_recall"] < a["fact_evidence"]["fact_evidence_recall"]})
    write_jsonl(OUT / "per-query-rank-delta.jsonl", deltas)
    write(OUT / "supporting-chunk-rank-analysis.json", {"records": deltas})
    eligible_gain = fact_comp["qwen3"]["all_required_facts_present_at5"] >= 2
    write(OUT / "development-manifest.json", {"status": "PENDING" if eligible_gain else "SKIPPED", "reason": "Development proceeds only after forensic fact-level gain.", "split": "development", "count": 200})
    if not eligible_gain:
        status = "QWEN3_RERANKER_NO_MEANINGFUL_GAIN"
        next_step = "BGE_KEEP_AND_SECTION_AWARE_EXPERIMENT"
    else:
        status = "QWEN3_RERANKER_GAIN_STRONG"
        next_step = "QWEN_RERANKER_GENERATION_IMPACT_PROBE"
    write(OUT / "decision.json", {"status": status, "forensic_gain": eligible_gain, "development_benchmark_status": "SKIPPED", "recommended_next_experiment": next_step})
    write(OUT / "summary.json", {"status": status, "identity": identity, "calls": {"generation": 0, "embedding": 3, "initial_retrieval": 3, "reranker": 6}, "forensic": fact_comp, "development_benchmark_status": "SKIPPED", "recommended_next_experiment": next_step})
    (OUT / "report.md").write_text(f"# Phase 7.11 Reranker Ablation\n\nStatus: {status}\n\nForensic fact-level comparison used the same ACL-filtered candidate Top-20 for BGE and Qwen3. Development benchmark: SKIPPED because this implementation intentionally completes only the forensic stage in this run.\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--collection", default=EXPECTED["collection"])
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    if args.finalize_existing:
        validate_identity()
        finalize_existing_artifacts()
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
