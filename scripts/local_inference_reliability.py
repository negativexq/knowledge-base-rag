# ruff: noqa: E402
"""Bounded local Ollama diagnosis for the M0 resume.

The matrix is deliberately tiny and sequential.  It never performs retrieval
and it never starts an official M0/V2.2 run unless all four probes pass.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evidence.section_aware import serialize_section_aware_context  # noqa: E402
from app.llm.observability import GenerationObservation  # noqa: E402
from app.llm.ollama_client import (  # noqa: E402
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_OVERALL_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    OllamaClient,
    OllamaRequestTimeout,
    OllamaUnreachableError,
)
from app.llm.structured_output import (  # noqa: E402
    stream_evidence_backed_answer,
    stream_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult  # noqa: E402

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
OUT = ROOT / "artifacts/phase-7/local-inference-reliability"
MODEL = "qwen3.5:4b"
SNAPSHOT_ID = "multi-00-1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def blocks_from_snapshot(snapshot_id: str) -> list[SearchResult]:
    snapshot = read_json(M0 / "evidence-snapshots" / f"{snapshot_id}.json")
    return [
        SearchResult(
            score=float(block.get("score", 0.0)),
            id=str(block.get("evidence_block_id", block.get("evidence_id", ""))),
            payload=dict(block),
        )
        for block in snapshot["evidence_blocks"]
    ]


def result_base(probe: str, client: OllamaClient, started: float) -> dict[str, Any]:
    return {
        "probe": probe,
        "model": MODEL,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "client_observation": client.last_call_observation,
    }


async def run_probe(client: OllamaClient, probe: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if probe == "A":
            raw = await client.chat_text(
                [{"role": "user", "content": "Reply with the single word OK."}],
                MODEL,
                think=False,
                temperature=0.0,
                seed=42,
            )
            result = result_base(probe, client, started)
            result.update({"result": "PASS", "response": raw})
            return result
        if probe == "B":
            raw = await client.chat_json(
                [{"role": "user", "content": "Return answer=OK."}],
                MODEL,
                think=False,
                temperature=0.0,
                seed=42,
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                },
            )
            result = result_base(probe, client, started)
            result.update({"result": "PASS", "response": raw})
            return result

        blocks = blocks_from_snapshot(SNAPSHOT_ID)
        observation = GenerationObservation()
        events = []
        if probe == "C":
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
                seed=42,
            )
        elif probe == "D":
            stream = stream_support_unit_answer(
                "What is the return window and what fields are required?",
                blocks,
                client,
                model=MODEL,
                prompt_version="v3",
                evaluation_observation=observation,
                think=False,
                num_ctx=4096,
                seed=42,
            )
        else:
            raise ValueError(f"unknown probe {probe}")
        async for event in stream:
            if event.get("type") != "token":
                events.append(event)
        result = result_base(probe, client, started)
        result.update(
            {
                "result": "PASS",
                "events": events,
                "observation": observation.as_dict(),
            }
        )
        return result
    except OllamaRequestTimeout as exc:
        result = result_base(probe, client, started)
        result.update(
            {
                "result": "TIMEOUT",
                "timeout_type": exc.timeout_type,
                "error": str(exc),
            }
        )
        return result
    except (OllamaUnreachableError, ValueError, json.JSONDecodeError) as exc:
        result = result_base(probe, client, started)
        result.update({"result": "FAIL", "error": str(exc)})
        return result
    except Exception as exc:  # diagnostic boundary: serialize unexpected provider errors
        result = result_base(probe, client, started)
        result.update({"result": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        return result


async def main_async(args: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    client = OllamaClient(
        base_url=args.ollama_url,
        connect_timeout=args.connect_timeout,
        timeout=args.read_timeout,
        overall_timeout=args.overall_timeout,
        think=False,
        num_ctx=4096,
    )
    try:
        try:
            models = await client.list_models()
            availability = {
                "reachable": True,
                "model": MODEL,
                "available": MODEL in models,
                "models": models,
            }
        except Exception as exc:
            availability = {
                "reachable": False,
                "model": MODEL,
                "available": False,
                "error": str(exc),
            }
        write_json(
            OUT / "timeout-config.json",
            {
                "connect_timeout_seconds": args.connect_timeout,
                "read_timeout_seconds": args.read_timeout,
                "overall_timeout_seconds": args.overall_timeout,
                "default_connect_timeout_seconds": DEFAULT_CONNECT_TIMEOUT_SECONDS,
                "default_read_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
                "default_overall_timeout_seconds": DEFAULT_OVERALL_TIMEOUT_SECONDS,
                "attempts": 1,
            },
        )
        write_json(OUT / "provider-availability.json", availability)
        if not availability["available"]:
            write_json(
                OUT / "provider-preflight.json",
                {"status": "TARGET_GENERATOR_UNAVAILABLE", "availability": availability},
            )
            return 2

        results = []
        for probe in ("A", "B", "C", "D"):
            result = await run_probe(client, probe)
            results.append(result)
            names = {"A": "plain", "B": "structured", "C": "v2-2-real", "D": "v2-3-real"}
            write_json(OUT / f"probe-{probe.lower()}-{names[probe]}.json", result)
            if result["result"] != "PASS":
                break

        status = (
            "PASS"
            if len(results) == 4 and all(item["result"] == "PASS" for item in results)
            else "PROVIDER_BLOCKED"
        )
        write_json(
            OUT / "provider-preflight.json",
            {
                "status": status,
                "availability": availability,
                "probes": results,
                "official_m0_allowed": status == "PASS",
            },
        )
        write_json(
            OUT / "provider-failure-taxonomy.json",
            {
                "PROVIDER_CONNECT_FAILURE": 0,
                "PROVIDER_READ_TIMEOUT": sum(
                    item.get("timeout_type") == "READ" for item in results
                ),
                "PROVIDER_OVERALL_TIMEOUT": sum(
                    item.get("timeout_type") == "OVERALL" for item in results
                ),
                "PROVIDER_HTTP_ERROR": sum(item.get("result") == "FAIL" for item in results),
                "PROVIDER_INVALID_RESPONSE": 0,
                "PROVIDER_PARSE_FAILURE": 0,
                "PROVIDER_SCHEMA_FAILURE": 0,
                "PROVIDER_PROCESS_EXIT": 0,
                "PROVIDER_UNKNOWN_FAILURE": 0,
            },
        )
        return 0 if status == "PASS" else 1
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT_SECONDS)
    parser.add_argument("--read-timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--overall-timeout", type=float, default=DEFAULT_OVERALL_TIMEOUT_SECONDS)
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
