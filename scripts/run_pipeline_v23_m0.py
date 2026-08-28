"""Run the preregistered V2.3 support-unit comparison on frozen snapshots."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.observability import GenerationObservation  # noqa: E402
from app.llm.ollama_client import (  # noqa: E402
    OllamaClient,
    OllamaRequestTimeout,
    OllamaUnreachableError,
)
from app.llm.structured_output import stream_support_unit_answer  # noqa: E402
from app.retrieval.hybrid_search import SearchResult  # noqa: E402

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
MODEL = "qwen3.5:4b"
SEEDS = (41, 42, 43, 44, 45)
HOLDOUT = tuple(json.loads((M0 / "holdout-manifest.json").read_text())[
    "query_ids"
])
ACL = tuple(json.loads((M0 / "acl-hard-safety-manifest.json").read_text())["query_ids"])
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"


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


def run_key(qid: str, seed: int, snapshot: dict[str, Any]) -> str:
    return sha256_json(
        {
            "pipeline": "pipeline_v2_3_2_support_units_bounded_output",
            "query_id": qid,
            "seed": seed,
            "snapshot_hash": snapshot["context_hash"],
            "generator": MODEL,
            "prompt": "v3",
            "output_contract": "output_contract_v2_3_2",
            "num_predict": 1024,
            "num_ctx": 4096,
            "temperature": 0.0,
            "think": False,
        }
    )


async def generate(
    client: OllamaClient, qid: str, question: str, blocks: list[SearchResult], seed: int
) -> dict[str, Any]:
    observation = GenerationObservation()
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    result = "PASS"
    try:
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
    except Exception as exc:  # keep one provider failure observable
        result = "FAIL"
        error = {"type": type(exc).__name__, "message": str(exc)}
    raw = observation.raw_candidate_output or ""
    return {
        "query_id": qid,
        "seed": seed,
        "pipeline_version": "pipeline_v2_3_2_support_units_bounded_output",
        "output_contract_version": "output_contract_v2_3_2",
        "result": result,
        "error": error,
        "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "raw_output": raw,
        "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "raw_candidate_available": observation.raw_candidate_available,
        "validator_pass": observation.validator_pass,
        "validator_failure_codes": observation.validator_failure_codes,
        "model_abstention": observation.model_abstention,
        "application_forced_abstention": observation.application_forced_abstention,
        "user_visible_output": observation.validated_output,
        "user_visible_output_available": observation.user_visible_output_available,
        "provider_observation": client.last_call_observation,
        "events": events,
    }


async def main_async(args: argparse.Namespace) -> int:
    questions = {row["id"]: row for row in read_json(DATASET)}
    if set(HOLDOUT) & set(ACL):
        raise RuntimeError("OVERLAPPING_HOLDOUT_ACL")
    if len(HOLDOUT) != 8 or len(ACL) != 3:
        raise RuntimeError("M0_QUERY_SET_MISMATCH")
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
        for qids, output in (
            (HOLDOUT, V23 / "v2-3-holdout-bounded-output-results.jsonl"),
            (ACL, V23 / "v2-3-acl-bounded-output-results.jsonl"),
        ):
            existing = {(row["query_id"], row["seed"]): row for row in read_jsonl(output)}
            for qid in qids:
                snapshot, blocks = blocks_for(qid)
                for seed in SEEDS:
                    key = (qid, seed)
                    expected_key = run_key(qid, seed, snapshot)
                    if key in existing:
                        if existing[key].get("run_key") != expected_key:
                            raise RuntimeError(f"CHECKPOINT_IDENTITY_MISMATCH:{qid}:{seed}")
                        continue
                    row = await generate(client, qid, questions[qid]["question"], blocks, seed)
                    row.update(
                        {
                            "run_key": expected_key,
                            "snapshot_hash": snapshot["context_hash"],
                            "top5_hash": sha256_json(snapshot["top5_ids"]),
                            "retrieval_calls": 0,
                            "reranker_calls": 0,
                        }
                    )
                    existing[key] = row
                    write_jsonl(output, [existing[item] for item in sorted(existing)])
                    if row["result"] != "PASS":
                        status_path = V23 / "paired-execution-status.json"
                        status_path.write_text(
                            json.dumps(
                                {
                                    "status": "PROVIDER_UNSTABLE",
                                    "query_id": qid,
                                    "seed": seed,
                                    "failure": row,
                                    "completed_rows": len(existing),
                                    "retrieval_calls": 0,
                                    "reranker_calls": 0,
                                },
                                ensure_ascii=False,
                                indent=2,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        return 2
    finally:
        await client.aclose()
    return 0


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
