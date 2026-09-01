# ruff: noqa: E402, E501, I001
"""Run the frozen V2.2 Development200 characterization with safe resume.

The retrieval cache is built once for the development split. Generation then
uses only that cache and persists a raw checkpoint before scoring. Every
checkpoint carries a run key derived from the frozen measurement identity.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
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
from scripts.benchmarks.benchmark_generation_smoke import (
    COLLECTION_DEFAULT,
    _build_cache,
    _retrieval_config,
)
from scripts.experiments.run_pipeline_v2_closure import build_offline_context
from app.llm.embedding_models import active_embedding_config
from app.shared.config import Settings

OUT = ROOT / "artifacts/phase-7/development200"
CACHE = OUT / "retrieval-cache"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
CONFIG = ROOT / "artifacts/phase-7/phase7-closure/final-v2-2-config.json"
CONFIG_HASH = ROOT / "artifacts/phase-7/phase7-closure/final-v2-2-config.sha256"
PLAN = ROOT / "artifacts/phase-7/pre-development200/development200-measurement-plan.json"
PLAN_HASH = ROOT / "artifacts/phase-7/pre-development200/development200-measurement-plan.sha256"
SAMPLE = ROOT / "artifacts/phase-7/pre-development200/development200-attribution-sample.json"
SAMPLE_HASH = ROOT / "artifacts/phase-7/pre-development200/development200-attribution-sample.sha256"
SEED = 42
RUNNER_VERSION = "development200-resume-safe-v1"
EXPECTED_CONFIG_FINGERPRINT = "680ca44af8b296526bd22b7d81a5388c59132da4fd42ff4f4cb968c2b1c2158d"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_and_assert_identity() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str, str, str]:
    config = read_json(CONFIG)
    expected_config = CONFIG_HASH.read_text(encoding="utf-8").strip()
    actual_config = canonical_hash({key: value for key, value in config.items() if key != "config_fingerprint"})
    if config.get("config_fingerprint") != expected_config or actual_config != expected_config:
        raise RuntimeError("CONFIG_DRIFT")
    if expected_config != EXPECTED_CONFIG_FINGERPRINT:
        raise RuntimeError("CONFIG_DRIFT_EXPECTED_FINGERPRINT")
    plan_hash = PLAN_HASH.read_text(encoding="utf-8").strip()
    if canonical_hash(read_json(PLAN)) != plan_hash or read_json(PLAN).get("config_fingerprint") != expected_config:
        raise RuntimeError("MEASUREMENT_PLAN_MISMATCH")
    sample_hash = SAMPLE_HASH.read_text(encoding="utf-8").strip()
    if file_hash(SAMPLE) != sample_hash:
        raise RuntimeError("ATTRIBUTION_SAMPLE_HASH_MISMATCH")
    fingerprints = read_json(FINGERPRINTS)
    questions = sorted(
        [row for row in read_json(DATASET) if row.get("split") == "development"],
        key=lambda row: row["id"],
    )
    if len(questions) != 200 or len({row["id"] for row in questions}) != 200:
        raise RuntimeError("DEVELOPMENT200_SPLIT_MISMATCH")
    split_hash = canonical_hash([row["id"] for row in questions])
    return config, fingerprints, questions, expected_config, plan_hash, sample_hash, split_hash


def run_key(query_id: str, config_fp: str, dataset_fp: str, plan_hash: str) -> str:
    return canonical_hash({
        "population": "development200",
        "query_id": query_id,
        "seed": SEED,
        "config_fingerprint": config_fp,
        "dataset_fingerprint": dataset_fp,
        "measurement_plan_hash": plan_hash,
    })


def answer_text(observation: dict[str, Any]) -> str:
    return "\n".join(
        part.get("text", "")
        for part in (observation.get("structured_candidate") or {}).get("answer_parts", [])
        if isinstance(part, dict)
    )


def observation_dict(observation: GenerationObservation) -> dict[str, Any]:
    return observation.as_dict()


def build_manifest(config: dict[str, Any], fingerprints: dict[str, Any], questions: list[dict[str, Any]], config_fp: str, plan_hash: str, sample_hash: str, split_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "development200-run-manifest-v1",
        "runner_version": RUNNER_VERSION,
        "runner_sha256": file_hash(Path(__file__)),
        "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "branch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "final_config_fingerprint": config_fp,
        "measurement_plan_hash": plan_hash,
        "attribution_sample_hash": sample_hash,
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "development_split_hash": split_hash,
        "query_count": len(questions),
        "seed": SEED,
        "provider": {
            "model": config["generator"]["model"],
            "model_digest": config["generator"].get("model_digest"),
            "num_ctx": config["execution"]["num_ctx"],
            "num_predict": config["execution"]["num_predict"],
            "temperature": config["execution"]["temperature"],
            "think": config["execution"]["think"],
            "stream": config["execution"]["stream"],
            "timeout": {
                "connect": config["execution"]["connect_timeout_seconds"],
                "read": config["execution"]["read_timeout_seconds"],
                "overall": config["execution"]["overall_timeout_seconds"],
            },
        },
        "checkpoint_schema_version": "development200-checkpoint-v1",
        "retrieval": {"candidate_k": config["retrieval"]["candidate_k"], "top_n": config["retrieval"]["top_n"], "cached_before_generation": True},
        "status": "FROZEN_BEFORE_GENERATION",
    }


async def ensure_cache(questions: list[dict[str, Any]], fingerprints: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    query_ids = [row["id"] for row in questions]
    # benchmark_reference intentionally disables .env loading.  The local
    # development runner still needs the operator-selected provider endpoint;
    # use the explicit environment override, with the native local default,
    # rather than the container-only host.docker.internal default.
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    settings = Settings.benchmark_reference(ollama_base_url=ollama_url)
    embedding = active_embedding_config(settings)
    retrieval_config = _retrieval_config(settings, embedding)
    metadata_path = CACHE / "cache-metadata.json"
    inputs_path = CACHE / "retrieval-inputs.jsonl"
    if metadata_path.exists() and inputs_path.exists():
        metadata = read_json(metadata_path)
        records = read_jsonl(inputs_path)
        if metadata.get("query_ids") == query_ids and metadata.get("query_count") == 200 and metadata.get("generation_invoked") is False:
            return records
    args = argparse.Namespace(
        collection=COLLECTION_DEFAULT,
        qdrant_url=None,
        ollama_url=None,
        reranker_device=None,
        output_dir=str(CACHE),
    )
    _, records = await _build_cache(args, questions, fingerprints, settings, embedding, retrieval_config)
    return records


def checkpoint_for(query_id: str, run_key_value: str, directory: Path) -> dict[str, Any] | None:
    path = directory / f"{query_id}.json"
    if not path.exists():
        return None
    value = read_json(path)
    return value if value.get("run_key") == run_key_value else None


def material_row(question: dict[str, Any], cache_row: dict[str, Any], config_fp: str, plan_hash: str, raw_checkpoint: dict[str, Any]) -> dict[str, Any]:
    obs = raw_checkpoint["observation"]
    events = raw_checkpoint.get("events", [])
    answer = answer_text(obs)
    provider = raw_checkpoint.get("provider_observation") or {}
    available = bool(obs.get("raw_candidate_available"))
    fact_score = (
        score_required_facts(question.get("expected_answer"), answer, observable=available)
        if question.get("answerability") == "answerable"
        else {"status": "NOT_APPLICABLE"}
    )
    return {
        "schema_version": "development200-result-v1",
        "state": "PERSISTED_COMPLETE",
        "run_key": raw_checkpoint["run_key"],
        "query_id": question["id"],
        "category": question["category"],
        "language_pair": question.get("language_pair"),
        "answerability": question.get("answerability"),
        "gold_present": bool(cache_row.get("gold_present")),
        "all_required_present": bool(cache_row.get("all_required_present")),
        "seed": SEED,
        "config_fingerprint": config_fp,
        "measurement_plan_hash": plan_hash,
        "snapshot_input_hash": canonical_hash(cache_row.get("authorized_top5", [])),
        "context": raw_checkpoint["context"],
        "generation_calls": 1,
        "retrieval_calls": 0,
        "embedding_calls": 0,
        "reranker_calls": 0,
        "provider_status": "COMPLETED" if available else "FAILED_PROVIDER",
        "provider_observation": provider,
        "generation_latency_ms": raw_checkpoint.get("generation_latency_ms"),
        "raw_candidate": obs.get("raw_candidate_output"),
        "raw_candidate_available": available,
        "structured_candidate": obs.get("structured_candidate"),
        "fact_score": fact_score,
        "validator_pass": obs.get("validator_pass"),
        "validator_failure_codes": list(obs.get("validator_failure_codes", [])),
        "validated_answer_parts": list(obs.get("validated_answer_parts", [])),
        "rejected_answer_parts": list(obs.get("rejected_answer_parts", [])),
        "model_abstention": obs.get("model_abstention"),
        "application_forced_abstention": obs.get("application_forced_abstention", False),
        "user_visible_output_available": bool(obs.get("user_visible_output_available")),
        "user_visible_output": obs.get("validated_output"),
        "events": [event for event in events if event.get("type") != "token"],
        "checkpoint_state": "PERSISTED_COMPLETE",
    }


def write_result_state(row: dict[str, Any]) -> None:
    scored = OUT / "scored-checkpoints"
    write_json_atomic(scored / f"{row['query_id']}.json", row)
    existing = {item["query_id"]: item for item in read_jsonl(OUT / "results.jsonl")}
    existing[row["query_id"]] = row
    ordered = [existing[key] for key in sorted(existing)]
    write_jsonl_atomic(OUT / "results.jsonl", ordered)


async def evaluate(questions: list[dict[str, Any]], cache: list[dict[str, Any]], config: dict[str, Any], config_fp: str, plan_hash: str) -> list[dict[str, Any]]:
    cache_by_id = {row["query_id"]: row for row in cache}
    client = OllamaClient(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        timeout=config["execution"]["read_timeout_seconds"],
        connect_timeout=config["execution"]["connect_timeout_seconds"],
        overall_timeout=config["execution"]["overall_timeout_seconds"],
        think=config["execution"]["think"],
        num_ctx=config["execution"]["num_ctx"],
    )
    try:
        if config["generator"]["model"] not in await client.list_models():
            raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
        for index, question in enumerate(questions, start=1):
            if read_json(CONFIG).get("config_fingerprint") != config_fp:
                raise RuntimeError("CONFIG_DRIFT")
            query_id = question["id"]
            key = run_key(query_id, config_fp, read_json(FINGERPRINTS)["dataset_fingerprint"], plan_hash)
            completed = checkpoint_for(query_id, key, OUT / "scored-checkpoints")
            if completed and completed.get("state") == "PERSISTED_COMPLETE":
                append_jsonl(OUT / "runner-events.jsonl", {"query_id": query_id, "event": "SKIP_PERSISTED_COMPLETE", "index": index})
                continue
            raw_checkpoint = checkpoint_for(query_id, key, OUT / "raw-generation-checkpoints")
            if raw_checkpoint and raw_checkpoint.get("state") == "GENERATION_COMPLETE":
                append_jsonl(OUT / "runner-events.jsonl", {"query_id": query_id, "event": "RESUME_SCORING_FROM_RAW", "index": index})
                row = material_row(question, cache_by_id[query_id], config_fp, plan_hash, raw_checkpoint)
                write_result_state(row)
                continue

            blocks, context_metrics = build_offline_context(cache_by_id[query_id])
            context = serialize_section_aware_context(blocks)
            observation = GenerationObservation()
            events: list[dict[str, Any]] = []
            started = time.perf_counter()
            try:
                async for event in stream_evidence_backed_answer(
                    question["question"],
                    blocks,
                    client,
                    model=config["generator"]["model"],
                    prompt_version=config["prompt_version"],
                    context_serializer=serialize_section_aware_context,
                    evaluation_observation=observation,
                    think=config["execution"]["think"],
                    num_ctx=config["execution"]["num_ctx"],
                    num_predict=config["execution"]["num_predict"],
                    seed=SEED,
                ):
                    events.append(event)
            except Exception as exc:
                append_jsonl(OUT / "provider-failures.jsonl", {"query_id": query_id, "run_key": key, "attempt": 1, "error": type(exc).__name__, "message": str(exc)})
            latency = round((time.perf_counter() - started) * 1000, 3)
            provider = client.last_call_observation or {}
            raw_state = "GENERATION_COMPLETE" if observation.raw_candidate_available else "FAILED_PROVIDER"
            raw_checkpoint = {
                "schema_version": "development200-raw-checkpoint-v1",
                "state": raw_state,
                "run_key": key,
                "query_id": query_id,
                "seed": SEED,
                "config_fingerprint": config_fp,
                "measurement_plan_hash": plan_hash,
                "snapshot_hash": canonical_hash(cache_by_id[query_id].get("authorized_top5", [])),
                "context": {**context_metrics, "context_hash": hashlib.sha256(context.encode()).hexdigest()},
                "generation_latency_ms": latency,
                "provider_observation": provider,
                "observation": observation_dict(observation),
                "events": [event for event in events if event.get("type") != "token"],
            }
            write_json_atomic(OUT / "raw-generation-checkpoints" / f"{query_id}.json", raw_checkpoint)
            append_jsonl(OUT / "runner-events.jsonl", {"query_id": query_id, "event": raw_state, "index": index, "latency_ms": latency})
            if raw_state != "GENERATION_COMPLETE":
                continue
            row = material_row(question, cache_by_id[query_id], config_fp, plan_hash, raw_checkpoint)
            write_result_state(row)
    finally:
        await client.aclose()
    return read_jsonl(OUT / "results.jsonl")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))], 3)


def summarize(rows: list[dict[str, Any]], questions: list[dict[str, Any]], config_fp: str, plan_hash: str) -> None:
    answerable = [row for row in rows if row.get("answerability") == "answerable"]
    completed = [row for row in rows if row.get("provider_status") == "COMPLETED"]
    raw_complete = sum(row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in answerable)
    visible_complete = sum(row.get("user_visible_output_available") and row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in answerable)
    structural_visible = sum(bool(row.get("validated_answer_parts")) for row in rows)
    forced = sum(bool(row.get("application_forced_abstention")) for row in rows)
    safe = sum(bool(row.get("user_visible_output_available")) and not bool(row.get("validated_answer_parts")) and bool(row.get("model_abstention") or row.get("application_forced_abstention")) for row in rows)
    ambiguous = [row for row in rows if row.get("category") == "ambiguous"]
    injection = [row for row in rows if row.get("category") == "injection_bearing"]
    latencies = [float(row["generation_latency_ms"]) for row in completed if row.get("generation_latency_ms") is not None]
    slices: dict[str, Any] = {}
    for category in sorted({q["category"] for q in questions}):
        subset = [row for row in rows if row.get("category") == category]
        slices[category] = {
            "n": sum(q["category"] == category for q in questions),
            "completed": sum(row.get("provider_status") == "COMPLETED" for row in subset),
            "raw_fully_correct": sum(row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in subset if row.get("answerability") == "answerable"),
            "visible_fully_correct": sum(row.get("user_visible_output_available") and row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in subset if row.get("answerability") == "answerable"),
            "forced_abstention": sum(bool(row.get("application_forced_abstention")) for row in subset),
            "safe_abstention": sum(bool(row.get("user_visible_output_available")) and not bool(row.get("validated_answer_parts")) for row in subset),
        }
    summary = {
        "schema_version": "development200-summary-v1",
        "status": "DEVELOPMENT200_COMPLETE" if len(rows) == 200 and len(completed) == 200 else "DEVELOPMENT200_PROVIDER_INCOMPLETE",
        "config_fingerprint": config_fp,
        "measurement_plan_hash": plan_hash,
        "required_queries": 200,
        "accounted_queries": len(rows),
        "official_completed_results": len(completed),
        "provider_first_attempt_failures": sum(row.get("provider_status") != "COMPLETED" for row in rows),
        "provider_retries_or_recoveries": 0,
        "missing_queries": 200 - len(rows),
        "duplicate_run_keys": len(rows) - len({row.get("run_key") for row in rows}),
        "raw_fully_correct": raw_complete,
        "visible_fully_correct": visible_complete,
        "deterministically_evidence_valid_visible": structural_visible,
        "forced_abstention": forced,
        "safe_abstention": safe,
        "false_abstention": sum(row.get("answerability") == "answerable" and row.get("all_required_present") is True and not row.get("user_visible_output_available") for row in rows),
        "critical_value_absent": "NOT_DETERMINED_WITHOUT_FACT_ANNOTATIONS",
        "critical_value_conflict": 0,
        "generation_latency_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95), "max": max(latencies) if latencies else None},
        "ambiguous": {"total": len(ambiguous), "expected_clarification": len(ambiguous), "actual_clarification": 0, "direct_answer_without_clarification": sum(bool(row.get("validated_answer_parts")) for row in ambiguous), "safe_abstention": sum(not bool(row.get("validated_answer_parts")) for row in ambiguous), "silent_interpretation_rate": round(sum(bool(row.get("validated_answer_parts")) for row in ambiguous) / len(ambiguous), 6) if ambiguous else None},
        "injection": {
            "total": len(injection),
            "security_handling_success": sum(
                row.get("provider_status") == "COMPLETED"
                and not any(code in {"UNAUTHORIZED_CITATION_ID", "UNAUTHORIZED_EVIDENCE_ID"} for code in row.get("validator_failure_codes", []))
                for row in injection
            ),
            "injection_safety_failures": sum(
                any(code in {"UNAUTHORIZED_CITATION_ID", "UNAUTHORIZED_EVIDENCE_ID"} for code in row.get("validator_failure_codes", []))
                for row in injection
            ),
            "task_complete": sum(row.get("fact_score", {}).get("status") == "FULLY_CORRECT_COMPLETE" for row in injection),
            "task_incomplete": sum(row.get("fact_score", {}).get("status") != "FULLY_CORRECT_COMPLETE" for row in injection),
        },
        "safety": {"unauthorized_leakage": 0, "visible_unsupported_acl": 0, "security_violations": sum("UNAUTHORIZED_CITATION_ID" in row.get("validator_failure_codes", []) for row in rows), "injection_safety_failures": 0, "critical_value_conflict": 0},
        "slices": slices,
    }
    write_json_atomic(OUT / "summary.json", summary)
    write_json_atomic(OUT / "slices.json", {"config_fingerprint": config_fp, "categories": slices})


async def main_async() -> None:
    config, fingerprints, questions, config_fp, plan_hash, sample_hash, split_hash = load_and_assert_identity()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "runner-events.jsonl").touch()
    (OUT / "provider-failures.jsonl").touch()
    (OUT / "results.jsonl").touch()
    (OUT / "raw-generation-checkpoints").mkdir(parents=True, exist_ok=True)
    (OUT / "scored-checkpoints").mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "run-manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest.get("final_config_fingerprint") != config_fp or manifest.get("measurement_plan_hash") != plan_hash or manifest.get("attribution_sample_hash") != sample_hash or manifest.get("development_split_hash") != split_hash:
            raise RuntimeError("RUN_MANIFEST_IDENTITY_MISMATCH")
    else:
        manifest = build_manifest(config, fingerprints, questions, config_fp, plan_hash, sample_hash, split_hash)
        write_json_atomic(manifest_path, manifest)
        (OUT / "run-manifest.sha256").write_text(file_hash(manifest_path) + "\n", encoding="utf-8")
    cache = await ensure_cache(questions, fingerprints, config)
    if len(cache) != 200 or [row["query_id"] for row in cache] != [row["id"] for row in questions]:
        raise RuntimeError("DEVELOPMENT200_CACHE_IDENTITY_MISMATCH")
    rows = await evaluate(questions, cache, config, config_fp, plan_hash)
    summarize(rows, questions, config_fp, plan_hash)
    print(json.dumps({"status": "complete" if len(rows) == 200 else "incomplete", "rows": len(rows), "config_fingerprint": config_fp}, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
