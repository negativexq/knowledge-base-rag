"""Run the permitted corrected initial-eight paired comparison.

This runner uses only the already-frozen evidence snapshots.  It does not
retrieve, embed, rerank, or rebuild evidence.  Both arms explicitly use the
same provider execution settings; only their output contract differs.
"""

# This script bootstraps the repository root before application imports.
# ruff: noqa: E402, E501

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evidence.section_aware import serialize_section_aware_context
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient, OllamaRequestTimeout, OllamaUnreachableError
from app.llm.structured_output import (
    parse_evidence_backed_answer,
    stream_evidence_backed_answer,
    stream_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult
from scripts.run_pipeline_v2_closure import build_offline_context

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
AUDIT = ROOT / "artifacts/phase-7/final-integrity-audit"
V22_OUT = AUDIT / "corrected-v2-2-results.jsonl"
V23_OUT = AUDIT / "corrected-v2-3-results.jsonl"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
MODEL = "qwen3.5:4b"
SEEDS = (41, 42, 43, 44, 45)
HOLDOUT = tuple(json.loads((M0 / "holdout-manifest.json").read_text())["query_ids"])
NUM_PREDICT = 1024


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def snapshot_and_blocks(qid: str) -> tuple[dict[str, Any], list[SearchResult]]:
    snapshot = read_json(M0 / "evidence-snapshots" / f"{qid}.json")
    blocks, _ = build_offline_context({"authorized_top5": snapshot["authorized_top5"]})
    return snapshot, blocks


def run_key(qid: str, seed: int, snapshot: dict[str, Any], pipeline: str) -> str:
    return sha256_json(
        {
            "pipeline": pipeline,
            "query_id": qid,
            "seed": seed,
            "snapshot_hash": snapshot["context_hash"],
            "generator": MODEL,
            "prompt": "v3",
            "num_ctx": 4096,
            "num_predict": NUM_PREDICT,
            "temperature": 0.0,
            "think": False,
            "stream": False,
        }
    )


async def generate_one(
    client: OllamaClient,
    qid: str,
    question: str,
    blocks: list[SearchResult],
    seed: int,
    pipeline: str,
) -> dict[str, Any]:
    observation = GenerationObservation()
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    result = "PASS"
    try:
        if pipeline == "v2.2":
            stream = stream_evidence_backed_answer(
                question,
                blocks,
                client,
                model=MODEL,
                prompt_version="v3",
                context_serializer=serialize_section_aware_context,
                evaluation_observation=observation,
                think=False,
                num_ctx=4096,
                num_predict=NUM_PREDICT,
                seed=seed,
            )
        else:
            stream = stream_support_unit_answer(
                question,
                blocks,
                client,
                model=MODEL,
                prompt_version="v3",
                evaluation_observation=observation,
                think=False,
                num_ctx=4096,
                seed=seed,
            )
        async for event in stream:
            if event.get("type") != "token":
                events.append(event)
    except OllamaRequestTimeout as exc:
        result = "TIMEOUT"
        error = {"type": type(exc).__name__, "message": str(exc), "timeout_type": exc.timeout_type}
    except (OllamaUnreachableError, ValueError, json.JSONDecodeError) as exc:
        result = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # one provider failure must remain observable
        result = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}

    raw = observation.raw_candidate_output or ""
    parsed_hash = None
    parsed_available = False
    try:
        if pipeline == "v2.2":
            parsed = parse_evidence_backed_answer(raw)
            parsed_hash = sha256_json(
                {
                    "answer_parts": [part.text for part in parsed.answer_parts],
                    "abstain": parsed.abstain,
                }
            )
            parsed_available = True
    except (ValueError, json.JSONDecodeError):
        parsed_available = False

    provider = client.last_call_observation or {}
    if provider.get("status") not in (None, "COMPLETE") and result == "PASS":
        result = "FAIL"
        error = {"type": "PROVIDER_STATUS", "message": provider.get("status")}
    return {
        "query_id": qid,
        "seed": seed,
        "pipeline_version": (
            "pipeline_v2_2_evidence_backed_corrected_num_predict_1024"
            if pipeline == "v2.2"
            else "pipeline_v2_3_2_support_units_bounded_output_corrected_pair"
        ),
        "output_contract_version": "output_contract_v2_2" if pipeline == "v2.2" else "output_contract_v2_3_2",
        "execution_config": {
            "model": MODEL,
            "num_ctx": 4096,
            "num_predict": NUM_PREDICT,
            "temperature": 0.0,
            "think": False,
            "stream": False,
        },
        "result": result,
        "error": error,
        "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "raw_output": raw,
        "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "parsed_output_hash": parsed_hash,
        "parsed_output_available": parsed_available,
        "raw_candidate_available": observation.raw_candidate_available,
        "validator_pass": observation.validator_pass,
        "validator_failure_codes": observation.validator_failure_codes,
        "model_abstention": observation.model_abstention,
        "application_forced_abstention": observation.application_forced_abstention,
        "user_visible_output": observation.validated_output,
        "user_visible_output_available": observation.user_visible_output_available,
        "provider_observation": provider,
        "events": events,
        "retrieval_calls": 0,
        "reranker_calls": 0,
    }


async def run_arm(
    client: OllamaClient,
    questions: dict[str, dict[str, Any]],
    output: Path,
    pipeline: str,
) -> tuple[list[dict[str, Any]], int]:
    existing = {(row.get("query_id"), row.get("seed")): row for row in read_jsonl(output)}
    failures = 0
    for qid in HOLDOUT:
        snapshot, blocks = snapshot_and_blocks(qid)
        for seed in SEEDS:
            key = (qid, seed)
            expected = run_key(qid, seed, snapshot, pipeline)
            if key in existing:
                if existing[key].get("run_key") != expected:
                    raise RuntimeError(f"CHECKPOINT_IDENTITY_MISMATCH:{pipeline}:{qid}:{seed}")
                continue
            row = await generate_one(client, qid, questions[qid]["question"], blocks, seed, pipeline)
            row.update({"run_key": expected, "snapshot_hash": snapshot["context_hash"]})
            existing[key] = row
            write_jsonl(output, [existing[item] for item in sorted(existing)])
            if row["result"] != "PASS":
                failures += 1
                # Preserve first-attempt failure and stop; resume can continue
                # after an operator/provider decision without hiding it.
                return [existing[item] for item in sorted(existing)], failures
    return [existing[item] for item in sorted(existing)], failures


async def main_async() -> int:
    questions = {row["id"]: row for row in read_json(DATASET)}
    if len(HOLDOUT) != 8:
        raise RuntimeError("INITIAL_HOLDOUT_MISMATCH")
    client = OllamaClient(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        think=False,
        num_ctx=4096,
        timeout=180.0,
        overall_timeout=240.0,
    )
    try:
        if MODEL not in await client.list_models():
            raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
        v22, f22 = await run_arm(client, questions, V22_OUT, "v2.2")
        if f22:
            print(json.dumps({"pipeline": "v2.2", "completed": len(v22), "provider_failures": f22}))
            return 2
        v23, f23 = await run_arm(client, questions, V23_OUT, "v2.3")
        print(json.dumps({"v2_2_rows": len(v22), "v2_3_rows": len(v23), "provider_failures": f23}))
        return 2 if f23 else 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
