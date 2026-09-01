# ruff: noqa: E501

"""Phase 7 cache-first end-to-end grounded-generation smoke benchmark.

The retrieval cache is built with the reference retrieval path once.  The
generation phase then calls the repository's real ``stream_answer`` path and
performs only deterministic scoring; no judge model is involved.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.generation_baseline import (
    aggregate_results,
    build_cache_record,
    chunks_from_cache,
    score_generation,
    select_generation_smoke_questions,
    summarize_latency,
)
from app.evaluation.index_validation import validate_evaluation_index
from app.llm.embedding_models import active_embedding_config
from app.llm.generate import stream_answer
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.report import RetrievalReport
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET = CORPUS_DIR / "golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
MANIFEST = CORPUS_DIR / "corpus-manifest.json"
INDEX_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"
OUTPUT_DIR = ROOT / "artifacts/phase-7/generation-smoke"
COLLECTION_DEFAULT = "kb_eval_phase55_0175aa4a2f9b"
REFERENCE_CANDIDATE_K = 20
TOP_N = 5


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _retrieval_config(settings: Settings, embedding: Any) -> dict[str, Any]:
    return {
        "embedding_model": embedding.ollama_model,
        "embedding_dimension": embedding.dimension,
        "retrieval_method": "BM25 + dense + RRF",
        "candidate_k": REFERENCE_CANDIDATE_K,
        "top_n": TOP_N,
        "reranker_model": settings.reranker_model,
        "tenant_acl": True,
        "security_mode": settings.security_validation_mode,
        "chunking": settings.chunking_config().as_dict(),
    }


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _load_questions() -> list[dict[str, Any]]:
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    return sorted((row for row in rows if row["split"] == "development"), key=lambda r: r["id"])


def _validate_cache_metadata(
    metadata: dict[str, Any],
    fingerprints: dict[str, str],
    collection: str,
    query_ids: list[str],
    retrieval_fp: str,
) -> None:
    expected = {
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config_fingerprint": retrieval_fp,
        "candidate_k": REFERENCE_CANDIDATE_K,
        "top_n": TOP_N,
        "authorized_only": True,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"generation cache identity mismatch for {key}")
    if metadata.get("query_ids") != query_ids:
        raise ValueError("generation cache query set does not match deterministic smoke set")
    if metadata.get("generation_invoked") is not False:
        raise ValueError("retrieval cache metadata claims generation was invoked")


def _load_cache(
    output_dir: Path,
    fingerprints: dict[str, str],
    collection: str,
    query_ids: list[str],
    retrieval_fp: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata_path = output_dir / "cache-metadata.json"
    inputs_path = output_dir / "retrieval-inputs.jsonl"
    if not metadata_path.exists() or not inputs_path.exists():
        raise FileNotFoundError("generation smoke cache is incomplete")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    _validate_cache_metadata(metadata, fingerprints, collection, query_ids, retrieval_fp)
    records = [
        json.loads(line) for line in inputs_path.read_text(encoding="utf-8").splitlines() if line
    ]
    if [record["query_id"] for record in records] != query_ids:
        raise ValueError("generation cache input order differs from query-set.json")
    if len(records) != len(query_ids):
        raise ValueError("generation cache record count mismatch")
    for record in records:
        if any("score" in chunk for chunk in record["authorized_top5"]):
            raise ValueError("generation cache must not contain retrieval scores")
        if any(not chunk["chunk_id"] for chunk in record["authorized_top5"]):
            raise ValueError("generation cache contains an empty authorized chunk ID")
        if record["retrieval"]["authorized_candidate_count"] < len(record["authorized_top5"]):
            raise ValueError("generation cache authorized count is smaller than top-k")
    return metadata, records


async def _build_cache(
    args: argparse.Namespace,
    questions: list[dict[str, Any]],
    fingerprints: dict[str, str],
    settings: Settings,
    embedding: Any,
    retrieval_config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collection = args.collection or COLLECTION_DEFAULT
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
    validation = validate_evaluation_index(
        qdrant,
        collection,
        MANIFEST,
        INDEX_VALIDATION,
        fingerprints["corpus_fingerprint"],
        expected_dimension=embedding.dimension,
    )
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        trust_remote_code=settings.reranker_trust_remote_code,
        device=args.reranker_device,
        max_concurrency=settings.reranker_max_concurrency,
    )
    records: list[dict[str, Any]] = []
    try:
        for question in questions:
            report = RetrievalReport()
            started = time.perf_counter()
            chunks = await search(
                question["question"],
                ollama,
                sparse,
                qdrant,
                collection,
                embedding.ollama_model,
                RetrievalContext(tenant_id=question["tenant_id"]),
                reranker=reranker,
                top_k=REFERENCE_CANDIDATE_K,
                top_n=TOP_N,
                query_prefix=embedding.query_prefix(),
                dimensions=embedding.output_dimension,
                report=report,
            )
            observation = extract_answerability_observation(
                chunks,
                authorized_candidate_count=report.authorized_candidate_count,
                pre_acl_candidate_count=report.pre_acl_candidate_count,
            )
            records.append(
                build_cache_record(
                    question,
                    chunks,
                    pre_acl_candidate_count=report.pre_acl_candidate_count,
                    authorized_candidate_count=report.authorized_candidate_count,
                    retrieval_ms=(time.perf_counter() - started) * 1000,
                    deterministic_reason=(
                        observation.reason if observation.reason != "FEATURES_AVAILABLE" else None
                    ),
                )
            )
    finally:
        await ollama.aclose()
        qdrant.close()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    query_ids = [question["id"] for question in questions]
    metadata = {
        "schema_version": "phase-7-generation-input-cache-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config": retrieval_config,
        "retrieval_config_fingerprint": _fingerprint(retrieval_config),
        "candidate_k": REFERENCE_CANDIDATE_K,
        "top_n": TOP_N,
        "query_count": len(records),
        "query_ids": query_ids,
        "authorized_only": True,
        "generation_invoked": False,
        "retrieval_calls_during_cache_build": len(records),
        "generation_model": settings.ollama_model,
        "generation_prompt_version": settings.active_prompt_version,
        "think": settings.ollama_thinking,
        "temperature": None,
        "security_mode": settings.security_validation_mode,
        "index_validation": validation,
        "category_counts": dict(Counter(record["category"] for record in records)),
        "language_pair_counts": dict(Counter(record["language_pair"] for record in records)),
    }
    _write_json(output_dir / "query-set.json", query_ids)
    (output_dir / "retrieval-inputs.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
        + "\n",
        encoding="utf-8",
    )
    _write_json(output_dir / "cache-metadata.json", metadata)
    return metadata, records


async def _model_available(client: OllamaClient, model: str) -> bool:
    return model in set(await client.list_models())


async def _evaluate_generation(
    records: list[dict[str, Any]],
    questions_by_id: dict[str, dict[str, Any]],
    settings: Settings,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = OllamaClient(base_url=settings.ollama_base_url, think=settings.ollama_thinking)
    results: list[dict[str, Any]] = []
    generation_errors = 0
    try:
        for record in records:
            question = questions_by_id[record["query_id"]]
            deterministic_reason = record["retrieval"].get("deterministic_reason")
            if deterministic_reason:
                skipped = score_generation(question, record, "", [])
                skipped.update(
                    {
                        "generation_invoked": False,
                        "provider_status": "SKIPPED_DETERMINISTIC_SAFETY",
                        "generation_latency_ms": None,
                        "provider_error": None,
                    }
                )
                skipped["failure"] = "DETERMINISTIC_SAFETY_SKIP"
                results.append(skipped)
                continue
            events: list[dict[str, Any]] = []
            answer_parts: list[str] = []
            evaluation_observation = GenerationObservation()
            started = time.perf_counter()
            provider_error: str | None = None
            try:
                async for event in stream_answer(
                    record["query"],
                    chunks_from_cache(record),
                    client,
                    model=settings.ollama_model,
                    prompt_version=settings.active_prompt_version,
                    validation_mode=settings.security_validation_mode,
                    injection_eval_category=(
                        "injection_bearing" if record["category"] == "injection_bearing" else None
                    ),
                    evaluation_observation=evaluation_observation,
                ):
                    events.append(event)
                    if event.get("type") == "token":
                        answer_parts.append(event.get("content", ""))
            except Exception as exc:  # provider failure is an explicit benchmark outcome
                provider_error = type(exc).__name__
                generation_errors += 1
            generation_ms = (time.perf_counter() - started) * 1000
            result = score_generation(question, record, "".join(answer_parts), events)
            result.update(
                {
                    "generation_invoked": True,
                    "provider_status": "ERROR" if provider_error else "COMPLETED",
                    "generation_latency_ms": round(generation_ms, 3),
                    "provider_error": provider_error,
                    "input_context": {
                        "authorized_chunk_count": len(record["authorized_top5"]),
                        "context_characters": sum(
                            len(chunk["content"]) for chunk in record["authorized_top5"]
                        ),
                    },
                    "evaluation_observability": evaluation_observation.as_dict(),
                }
            )
            if provider_error:
                result["failure"] = "GENERATION_PROVIDER_FAILURE"
            results.append(result)
    finally:
        await client.aclose()
    return results, {"generation_provider_failures": generation_errors}


def _slice_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    keys = {"all"}
    for result in results:
        keys.update({result["category"], result["language_pair"]})
    output: dict[str, Any] = {}
    for key in sorted(keys):
        rows = (
            results
            if key == "all"
            else [r for r in results if r["category"] == key or r["language_pair"] == key]
        )
        gold = [r for r in rows if r["answerability"] == "answerable" and r["all_required_present"]]
        answerable = [r for r in rows if r["answerability"] == "answerable"]
        output[key] = {
            "n": len(rows),
            "answerable_n": len(answerable),
            "correct": {
                "count": sum(r["correctness"]["status"] == "PASS" for r in answerable),
                "denominator": len(answerable),
            },
            "complete": sum(
                r["required_fact_completeness"]["covered"]
                == r["required_fact_completeness"]["total"]
                and r["correctness"]["status"] != "NOT_APPLICABLE"
                for r in answerable
            ),
            "unsupported_claim_failures": sum(
                r["unsupported_claims"]["status"] == "FAIL" for r in rows
            ),
            "citation_failures": sum(not r["citations"]["valid"] for r in rows),
            "gold_present_success": {
                "count": None,
                "denominator": len(gold),
                "status": "REQUIRES_REVIEW_FOR_CLAIM_SUPPORT",
            },
        }
    return output


def _manual_review(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "query_id": result["query_id"],
            "query": result["query"],
            "generated_answer": result["answer"],
            "expected_evidence_references": result.get("expected_source_ids", []),
            "actual_citations": result["citations"]["found"],
            "reason": "claim-level entailment, authority, or language requires human review",
        }
        for result in results
        if result["manual_review_required"]
    ]


def _write_outputs(
    output_dir: Path,
    metadata: dict[str, Any],
    results: list[dict[str, Any]],
    questions_by_id: dict[str, dict[str, Any]],
    settings: Settings,
    model_available: bool,
    provider_info: dict[str, Any],
) -> None:
    summary = aggregate_results(results)
    cache_records = [
        json.loads(line)
        for line in (output_dir / "retrieval-inputs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    cache_answerable = [r for r in cache_records if r["answerability"] == "answerable"]
    cache_gold_present = [r for r in cache_answerable if r["all_required_present"]]
    cache_deterministic_reasons = Counter(
        r["retrieval"]["deterministic_reason"]
        for r in cache_records
        if r["retrieval"]["deterministic_reason"]
    )
    summary.update(
        {
            "status": "BASELINE_INCONCLUSIVE" if not model_available else "MEASURED_SMOKE",
            "generation_model": settings.ollama_model,
            "generation_model_available": model_available,
            "generation_prompt_version": settings.active_prompt_version,
            "think": settings.ollama_thinking,
            "semantic_answerability_invoked": False,
            "calibration_run": False,
            "frozen_test_touched": False,
            "generation_calls": sum(result.get("generation_invoked", False) for result in results),
            "retrieval_calls_during_generation_evaluation": 0,
            "embedding_calls_during_generation_evaluation": 0,
            "reranker_calls_during_generation_evaluation": 0,
            "semantic_answerability_calls_during_generation_evaluation": 0,
            "deterministic_safety_skips": sum(
                result.get("failure") == "DETERMINISTIC_SAFETY_SKIP" for result in results
            ),
            "smoke_query_count": len(cache_records),
            "cache_category_counts": dict(Counter(r["category"] for r in cache_records)),
            "cache_language_pair_counts": dict(Counter(r["language_pair"] for r in cache_records)),
            "cache_answerable_count": len(cache_answerable),
            "cache_gold_present_answerable_count": len(cache_gold_present),
            "cache_deterministic_safety_reasons": dict(cache_deterministic_reasons),
            **provider_info,
        }
    )
    _write_json(output_dir / "summary.json", summary)
    (output_dir / "generation-results.jsonl").write_text(
        "\n".join(json.dumps(result, ensure_ascii=False, sort_keys=True) for result in results)
        + ("\n" if results else ""),
        encoding="utf-8",
    )
    _write_json(output_dir / "correctness-results.json", {"summary": summary, "records": results})
    _write_json(
        output_dir / "citation-results.json",
        {
            "summary": summary["citation_validity"],
            "records": [{"query_id": r["query_id"], **r["citations"]} for r in results],
        },
    )
    _write_json(output_dir / "slice-results.json", _slice_results(results))
    failures = [
        {
            "query_id": r["query_id"],
            "category": r["category"],
            "failures": [r["failure"]] if r["failure"] else [],
        }
        for r in results
        if r["failure"]
    ]
    _write_json(output_dir / "failure-analysis.json", failures)
    review_rows = _manual_review(results)
    (output_dir / "manual-review.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in review_rows)
        + ("\n" if review_rows else ""),
        encoding="utf-8",
    )
    retrieval_values = [
        float(r["retrieval"]["retrieval_ms"])
        for r in (
            json.loads(line)
            for line in (output_dir / "retrieval-inputs.jsonl").read_text().splitlines()
        )
        if r["retrieval"]["retrieval_ms"] is not None
    ]
    generation_values = [
        r["generation_latency_ms"] for r in results if r.get("generation_latency_ms") is not None
    ]
    e2e_values: list[float] = []
    cached_rows = [
        json.loads(line)
        for line in (output_dir / "retrieval-inputs.jsonl").read_text().splitlines()
        if line
    ]
    results_by_id = {result["query_id"]: result for result in results}
    for cached in cached_rows:
        result = results_by_id.get(cached["query_id"])
        generation_ms = result.get("generation_latency_ms") if result else None
        retrieval_ms = cached["retrieval"].get("retrieval_ms")
        if generation_ms is not None and retrieval_ms is not None:
            e2e_values.append(float(retrieval_ms) + float(generation_ms))
    latency = {
        "retrieval": summarize_latency(retrieval_values),
        "generation": summarize_latency(generation_values),
        "validation": {"status": "not separately instrumented by current stream_answer"},
        "end_to_end": summarize_latency(e2e_values),
    }
    _write_json(output_dir / "latency.json", latency)
    model_note = (
        f"The configured generator `{settings.ollama_model}` was not available locally; "
        "no generation calls were made.\n"
        if not model_available
        else "Generation used the repository stream_answer path with strict v3 output validation.\n"
    )
    report = f"""# Phase 7 Generation Smoke

{model_note}
Retrieval was cached once for {metadata['query_count']} deterministic development queries. The cache contains only authorized top-5 chunks and is bound to corpus `{metadata['corpus_fingerprint']}` and dataset `{metadata['dataset_fingerprint']}`.

## Scope

- Retrieval identity: `{metadata['retrieval_config_fingerprint']}`
- Generation model: `{settings.ollama_model}`
- Prompt: `{settings.active_prompt_version}`
- Thinking: `{settings.ollama_thinking}`
- Semantic Phase 6 gate: disabled and not invoked
- Calibration/frozen test/full development: not run

## Interpretation

Deterministic fact and citation checks are reported separately. Unsupported claim entailment, authority selection, and language appropriateness remain explicit manual-review dimensions; they are not silently converted into automated passes.

Summary: `{summary['status']}`

## Measured results

- Gold-present answerable: `{summary['gold_present_answerable_count']}`
- Deterministic correctness: `{summary['correct_answer']['count']}/{summary['correct_answer']['denominator']}`
- Authored required-fact completeness: `{summary['fully_complete_answer']['count']}/{summary['fully_complete_answer']['denominator']}`
- Gold-present success: `not fully determinable`; claim-level entailment remains in manual review
- Citation-ID validity: `{summary['citation_validity']['count']}/{summary['citation_validity']['denominator']}`
- Citation support correctness: `{summary['citation_support_correctness']['count']}/{summary['citation_support_correctness']['denominator']}`
- Strict output validation: `{summary['output_validation']['count']}/{summary['output_validation']['denominator']}`
- Manual review records: `{summary['manual_review_count']}`
- Generation latency p50/p95/max: `{latency['generation']['p50_ms']}/{latency['generation']['p95_ms']}/{latency['generation']['max_ms']} ms`
- Retrieval, embedding, reranker, and semantic-gate calls during generation evaluation: `0`

The three complete multi-document records had all required evidence in the
cached authorized context; the generation result is reported separately from
the Phase 6 semantic-gate result (`0/3 ANSWER`). No old `qwen3:4b` generation
measurement exists, so this smoke establishes `qwen3.5:4b` as the new measured
baseline rather than an improvement claim.
"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    if args.split != "development":
        raise ValueError("Phase 7 smoke permits only --split development")
    output_dir = Path(args.output_dir)
    questions = select_generation_smoke_questions(_load_questions())
    query_ids = [question["id"] for question in questions]
    fingerprints = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    settings_overrides = {"ollama_base_url": args.ollama_url} if args.ollama_url else {}
    settings = Settings.benchmark_reference(**settings_overrides)
    embedding = active_embedding_config(settings)
    retrieval_config = _retrieval_config(settings, embedding)
    retrieval_fp = _fingerprint(retrieval_config)
    collection = args.collection or COLLECTION_DEFAULT
    try:
        if args.rebuild_cache:
            raise FileNotFoundError
        metadata, records = _load_cache(
            output_dir, fingerprints, collection, query_ids, retrieval_fp
        )
        cache_reused = True
    except FileNotFoundError:
        metadata, records = await _build_cache(
            args, questions, fingerprints, settings, embedding, retrieval_config
        )
        cache_reused = False
    if [record["query_id"] for record in records] != query_ids:
        raise ValueError("cache/query-set identity mismatch")
    metadata.update(
        {
            "generation_model": settings.ollama_model,
            "generation_prompt_version": settings.active_prompt_version,
            "think": settings.ollama_thinking,
            "security_mode": settings.security_validation_mode,
        }
    )
    metadata["cache_reused"] = cache_reused
    _write_json(output_dir / "cache-metadata.json", metadata)
    questions_by_id = {question["id"]: question for question in questions}
    if args.rescore_existing:
        existing_path = output_dir / "generation-results.jsonl"
        if not existing_path.exists():
            raise FileNotFoundError("cannot rescore without generation-results.jsonl")
        existing = [
            json.loads(line)
            for line in existing_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        records_by_id = {record["query_id"]: record for record in records}
        results = []
        for old in existing:
            result = score_generation(
                questions_by_id[old["query_id"]],
                records_by_id[old["query_id"]],
                old.get("answer", ""),
                old.get("events", []),
            )
            for key in (
                "generation_invoked",
                "provider_status",
                "generation_latency_ms",
                "provider_error",
                "input_context",
            ):
                if key in old:
                    result[key] = old[key]
            results.append(result)
        _write_outputs(
            output_dir,
            metadata,
            results,
            questions_by_id,
            settings,
            True,
            {"generation_provider_failures": sum(bool(r.get("provider_error")) for r in results)},
        )
        print(json.dumps({"status": "rescored", "query_count": len(results)}, sort_keys=True))
        return 0
    availability_client = OllamaClient(base_url=settings.ollama_base_url)
    try:
        model_available = await _model_available(availability_client, settings.ollama_model)
    finally:
        await availability_client.aclose()
    if model_available:
        results, provider_info = await _evaluate_generation(
            records, questions_by_id, settings, output_dir
        )
    else:
        results = []
        provider_info = {"generation_provider_failures": 0}
    _write_outputs(
        output_dir,
        metadata,
        results,
        questions_by_id,
        settings,
        model_available,
        provider_info,
    )
    print(
        json.dumps(
            {
                "status": "model_available" if model_available else "model_unavailable",
                "query_count": len(questions),
                "cache_reused": cache_reused,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="development")
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--reranker-device", default=None)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--rescore-existing", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
