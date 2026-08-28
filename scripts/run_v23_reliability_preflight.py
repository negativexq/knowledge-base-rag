"""Five sequential post-fix V2.3 provider calls on one frozen snapshot."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

# ruff: noqa: E402
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient, OllamaRequestTimeout
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"
QID = "multi-00-0"
SEEDS = (41, 42, 43, 44, 45)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


async def main_async(args: argparse.Namespace) -> None:
    dataset = {
        row["id"]: row
        for row in read_json(ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json")
    }
    snapshot = read_json(M0 / "evidence-snapshots" / f"{QID}.json")
    blocks = [
        SearchResult(
            score=float(item.get("score", 0.0)),
            id=str(item.get("evidence_block_id", item.get("evidence_id", ""))),
            payload=dict(item),
        )
        for item in snapshot["evidence_blocks"]
    ]
    client = OllamaClient(
        base_url=args.url,
        connect_timeout=10,
        timeout=args.timeout,
        overall_timeout=args.overall_timeout,
        think=False,
        num_ctx=4096,
    )
    rows = []
    try:
        for seed in SEEDS:
            observation = GenerationObservation()
            started = time.perf_counter()
            error = None
            result = "PASS"
            try:
                async for _ in stream_support_unit_answer(
                    dataset[QID]["question"],
                    blocks,
                    client,
                    model="qwen3.5:4b",
                    prompt_version="v3",
                    evaluation_observation=observation,
                    think=False,
                    num_ctx=4096,
                    seed=seed,
                ):
                    pass
            except OllamaRequestTimeout as exc:
                result = "TIMEOUT"
                error = {
                    "type": type(exc).__name__,
                    "timeout_type": exc.timeout_type,
                    "message": str(exc),
                }
            except Exception as exc:  # provider preflight must preserve failures
                result = "FAIL"
                error = {"type": type(exc).__name__, "message": str(exc)}
            raw = observation.raw_candidate_output or ""
            rows.append(
                {
                    "query_id": QID,
                    "seed": seed,
                    "result": result,
                    "error": error,
                    "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "raw_candidate_available": observation.raw_candidate_available,
                    "validator_pass": observation.validator_pass,
                    "provider_observation": client.last_call_observation,
                    "snapshot_hash": snapshot["context_hash"],
                    "retrieval_calls": 0,
                    "reranker_calls": 0,
                }
            )
    finally:
        await client.aclose()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "five-call-v2-3-reliability.json").write_text(
        json.dumps(
            {
                "query_id": QID,
                "snapshot_hash": snapshot["context_hash"],
                "required_calls": 5,
                "completed_calls": len(rows),
                "success_count": sum(row["result"] == "PASS" for row in rows),
                "timeout_count": sum(row["result"] == "TIMEOUT" for row in rows),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--overall-timeout", type=float, default=240.0)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
