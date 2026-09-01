# ruff: noqa: E402
"""Run the bounded five-call provider reliability preflight.

This consumes one already-frozen V2.2 evidence snapshot.  It never performs
retrieval and writes one complete record per attempt atomically so a partial
provider failure cannot be mistaken for a successful call.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evidence.section_aware import serialize_section_aware_context
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient, OllamaRequestTimeout, OllamaUnreachableError
from app.llm.structured_output import stream_evidence_backed_answer
from app.retrieval.hybrid_search import SearchResult

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
OUT = ROOT / "artifacts/phase-7/local-inference-reliability"
QUERY_ID = "multi-00-1"
SEED = 42
MODEL = "qwen3.5:4b"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def snapshot_blocks() -> tuple[str, list[SearchResult], dict[str, Any]]:
    snapshot = read_json(M0 / "evidence-snapshots" / f"{QUERY_ID}.json")
    blocks = [
        SearchResult(
            score=float(block.get("score", 0.0)),
            id=str(block.get("evidence_block_id", block.get("evidence_id", ""))),
            payload=dict(block),
        )
        for block in snapshot["evidence_blocks"]
    ]
    return snapshot["context_hash"], blocks, snapshot


async def run_call(client: OllamaClient, blocks: list[SearchResult]) -> dict[str, Any]:
    observation = GenerationObservation()
    started = time.perf_counter()
    try:
        events = []
        stream = stream_evidence_backed_answer(
            "What is the return window and what fields are required?",
            blocks,
            client,
            model=MODEL,
            prompt_version="v3",
            context_serializer=serialize_section_aware_context,
            evaluation_observation=observation,
            think=False,
            num_ctx=4096,
            seed=SEED,
        )
        async for event in stream:
            if event.get("type") != "token":
                events.append(event)
        result = "PASS"
        error = None
    except OllamaRequestTimeout as exc:
        result = "TIMEOUT"
        error = {"type": type(exc).__name__, "message": str(exc), "timeout_type": exc.timeout_type}
        events = []
    except (OllamaUnreachableError, ValueError, json.JSONDecodeError) as exc:
        result = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}
        events = []
    return {
        "query_id": QUERY_ID,
        "seed": SEED,
        "pipeline_version": "pipeline_v2_2_evidence_backed",
        "output_contract_version": "output_contract_v2_2",
        "result": result,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "error": error,
        "provider_observation": client.last_call_observation,
        "raw_candidate_available": observation.raw_candidate_available,
        "raw_output_hash": hashlib.sha256(
            (observation.raw_candidate_output or "").encode()
        ).hexdigest(),
        "parsed_output_hash": sha256_json(observation.structured_candidate),
        "validator_pass": observation.validator_pass,
        "validator_failure_codes": observation.validator_failure_codes,
        "model_abstention": observation.model_abstention,
        "application_forced_abstention": observation.application_forced_abstention,
        "events": events,
    }


async def main_async(args: argparse.Namespace) -> int:
    context_hash, blocks, snapshot = snapshot_blocks()
    output = OUT / "five-call-reliability.jsonl"
    existing = read_jsonl(output)
    if any(row.get("context_hash") not in (None, context_hash) for row in existing):
        raise RuntimeError("SNAPSHOT_HASH_MISMATCH")
    client = OllamaClient(
        base_url=args.ollama_url,
        connect_timeout=args.connect_timeout,
        timeout=args.read_timeout,
        overall_timeout=args.overall_timeout,
        think=False,
        num_ctx=4096,
    )
    try:
        if MODEL not in await client.list_models():
            raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
        for index in range(1, 6):
            if any(row.get("attempt") == index for row in existing):
                continue
            row = await run_call(client, blocks)
            row.update(
                {
                    "attempt": index,
                    "context_hash": context_hash,
                    "snapshot_query_id": QUERY_ID,
                    "snapshot_top5_hash": sha256_json(snapshot["top5_ids"]),
                }
            )
            existing.append(row)
            write_jsonl(output, sorted(existing, key=lambda item: item["attempt"]))
    finally:
        await client.aclose()
    completed = [row for row in existing if row.get("result") == "PASS"]
    summary = {
        "query_id": QUERY_ID,
        "required_calls": 5,
        "completed_calls": len(existing),
        "success_count": len(completed),
        "timeout_count": sum(row.get("result") == "TIMEOUT" for row in existing),
        "failure_count": sum(row.get("result") == "FAIL" for row in existing),
        "max_latency_ms": max((row.get("elapsed_ms", 0) for row in existing), default=None),
        "all_terminated": len(existing) == 5,
        "all_pass": len(existing) == 5 and len(completed) == 5,
        "snapshot_hash": context_hash,
        "retrieval_calls": 0,
        "reranker_calls": 0,
    }
    write_json(OUT / "five-call-reliability-summary.json", summary)
    return 0 if summary["all_pass"] else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--read-timeout", type=float, default=180.0)
    parser.add_argument("--overall-timeout", type=float, default=240.0)
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
