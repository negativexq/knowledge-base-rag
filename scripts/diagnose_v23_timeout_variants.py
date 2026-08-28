"""Small, non-benchmark V2.3 timeout variant probes.

Only the two historical timeout query/seed pairs are accepted.  This script
uses frozen evidence snapshots and never invokes retrieval or reranking.
"""

# The repository's script convention inserts the workspace before app imports.
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.ollama_client import OllamaClient, OllamaRequestTimeout, OllamaUnreachableError
from app.llm.prompt import build_messages
from app.llm.structured_output import (
    SUPPORT_UNIT_OUTPUT_INSTRUCTIONS,
    support_unit_output_schema,
    support_unit_pattern_output_schema,
)
from app.llm.support_units import build_support_units, serialize_support_units
from app.retrieval.hybrid_search import SearchResult

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"
TIMEOUT_PAIRS = {("multi-01-0", 41), ("multi-01-0", 42)}
KNOWN_TIMEOUT_SNAPSHOT_HASHES = {
    "multi-01-0": "2a036a28ff26c8a4eff8a3b9b45c1ae131a834efb55ef52de7316cdfe91ac41d",
    "multi-01-1": "470458401003fbe9868cdb522f44b633ad5d8ca550bd10392b59bd57ff98cbcb",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def blocks_for(qid: str) -> tuple[dict[str, Any], list[SearchResult]]:
    snapshot = read_json(M0 / "evidence-snapshots" / f"{qid}.json")
    blocks = [
        SearchResult(
            score=float(item.get("score", 0.0)),
            id=str(item.get("evidence_block_id", item.get("evidence_id", ""))),
            payload=dict(item),
        )
        for item in snapshot["evidence_blocks"]
    ]
    return snapshot, blocks


def request_for(
    question: str,
    blocks: list[SearchResult],
    seed: int,
    schema: dict[str, Any],
    *,
    stream: bool = False,
    num_predict: int | None = None,
) -> dict[str, Any]:
    units = build_support_units(blocks)
    messages = build_messages(
        question,
        units,
        version="v3",
        context_serializer=serialize_support_units,
        system_prompt_suffix=SUPPORT_UNIT_OUTPUT_INSTRUCTIONS,
    )
    options: dict[str, Any] = {"temperature": 0.0, "num_ctx": 4096, "seed": seed}
    if num_predict is not None:
        options["num_predict"] = num_predict
    return {
        "model": "qwen3.5:4b",
        "messages": messages,
        "stream": stream,
        "format": schema,
        "options": options,
        "think": False,
        "keep_alive": "30m",
    }


async def run_nonstream(
    variant: str,
    qid: str,
    seed: int,
    question: str,
    blocks: list[SearchResult],
    args: argparse.Namespace,
) -> dict[str, Any]:
    units = build_support_units(blocks)
    schema = (
        support_unit_pattern_output_schema()
        if variant == "pattern"
        else support_unit_output_schema(units)
    )
    num_predict = args.num_predict if variant == "reduced_output" else None
    body = request_for(question, blocks, seed, schema, num_predict=num_predict)
    client = OllamaClient(
        base_url=args.url,
        connect_timeout=10,
        timeout=args.timeout,
        overall_timeout=args.overall_timeout,
        think=False,
        num_ctx=4096,
    )
    started = time.perf_counter()
    status = "COMPLETE"
    error: dict[str, Any] | None = None
    raw = ""
    try:
        raw = await client.chat_json(
            body["messages"],
            model="qwen3.5:4b",
            think=False,
            temperature=0.0,
            schema=schema,
            num_ctx=4096,
            seed=seed,
            num_predict=num_predict,
        )
    except OllamaRequestTimeout as exc:
        status = "TIMEOUT"
        error = {"type": type(exc).__name__, "timeout_type": exc.timeout_type, "message": str(exc)}
    except (OllamaUnreachableError, ValueError, json.JSONDecodeError) as exc:
        status = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        observation = client.last_call_observation
        await client.aclose()
    return {
        "variant": variant,
        "query_id": qid,
        "seed": seed,
        "status": status,
        "error": error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest() if raw else None,
        "raw_output_bytes": len(raw.encode()),
        "request_hash": sha(body),
        "schema_hash": sha(schema),
        "schema_bytes": len(json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()),
        "support_unit_count": len(units),
        "stream": False,
        "provider_observation": observation,
        "retrieval_calls": 0,
        "reranker_calls": 0,
        "diagnostic": True,
        "recorded_at": now(),
    }


async def run_stream(
    qid: str, seed: int, question: str, blocks: list[SearchResult], args: argparse.Namespace
) -> dict[str, Any]:
    units = build_support_units(blocks)
    schema = support_unit_output_schema(units)
    body = request_for(question, blocks, seed, schema, stream=True)
    started = time.perf_counter()
    headers_at = None
    first_at = None
    response_bytes = 0
    status = "COMPLETE"
    error = None
    raw_lines: list[str] = []
    timeout = httpx.Timeout(
        args.timeout, connect=10, read=args.timeout, write=args.timeout, pool=10
    )
    try:
        async with httpx.AsyncClient(base_url=args.url, timeout=timeout) as http:
            async with asyncio.timeout(args.overall_timeout):
                async with http.stream("POST", "/api/chat", json=body) as response:
                    headers_at = now()
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if first_at is None:
                            first_at = now()
                        response_bytes += len(line.encode())
                        raw_lines.append(line)
    except TimeoutError as exc:
        status = "TIMEOUT"
        error = {"type": type(exc).__name__, "timeout_type": "OVERALL", "message": str(exc)}
    except httpx.ReadTimeout as exc:
        status = "TIMEOUT"
        error = {"type": type(exc).__name__, "timeout_type": "READ", "message": str(exc)}
    except httpx.HTTPError as exc:
        status = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}
    return {
        "variant": "streaming",
        "query_id": qid,
        "seed": seed,
        "status": status,
        "error": error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "request_hash": sha(body),
        "schema_hash": sha(schema),
        "schema_bytes": len(json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()),
        "support_unit_count": len(units),
        "stream": True,
        "headers_received": headers_at is not None,
        "headers_received_at": headers_at,
        "first_body_byte": first_at is not None,
        "first_body_byte_at": first_at,
        "response_bytes": response_bytes,
        "line_count": len(raw_lines),
        "retrieval_calls": 0,
        "reranker_calls": 0,
        "diagnostic": True,
        "recorded_at": now(),
    }


async def main_async(args: argparse.Namespace) -> None:
    questions = {
        row["id"]: row["question"]
        for row in read_json(ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json")
    }
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    pairs = {(args.query_id, args.seed)} if args.query_id else TIMEOUT_PAIRS
    variants = tuple(item for item in args.variants.split(",") if item)
    for qid, seed in sorted(pairs):
        snapshot, blocks = blocks_for(qid)
        # The explicit pair check makes accidental expansion impossible.
        if snapshot.get("context_hash") != KNOWN_TIMEOUT_SNAPSHOT_HASHES.get(qid):
            raise RuntimeError("TIMEOUT_SNAPSHOT_IDENTITY_MISMATCH")
        if "pattern" in variants:
            results.append(await run_nonstream("pattern", qid, seed, questions[qid], blocks, args))
        if "reduced_output" in variants:
            results.append(
                await run_nonstream("reduced_output", qid, seed, questions[qid], blocks, args)
            )
        if "streaming" in variants:
            results.append(await run_stream(qid, seed, questions[qid], blocks, args))
    path = OUT / "diagnostic-replay-results.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "historical_current_v23": {
            "status": "TIMEOUT",
            "pairs": [{"query_id": qid, "seed": seed} for qid, seed in sorted(TIMEOUT_PAIRS)],
            "source": "timeout-run-manifest / prior official partial results",
        },
        "new_results": results,
        "interpretation": {
            "pattern_passes_quickly": all(
                item["status"] == "COMPLETE" for item in results if item["variant"] == "pattern"
            ),
            "reduced_output_passes_quickly": all(
                item["status"] == "COMPLETE"
                for item in results
                if item["variant"] == "reduced_output"
            ),
            "streaming_starts": all(
                item.get("first_body_byte") for item in results if item["variant"] == "streaming"
            ),
        },
    }
    (OUT / "diagnostic-replay-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--overall-timeout", type=float, default=240.0)
    parser.add_argument("--query-id", default=None)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--variants", default="pattern,reduced_output,streaming")
    parser.add_argument("--num-predict", type=int, default=64)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
