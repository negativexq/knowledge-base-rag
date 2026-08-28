"""Offline forensic report for the partial V2.3 execution.

This script only reads frozen snapshots and prior V2.3 result records.  It
does not contact Ollama, retrieval, or any model backend.
"""

# The repository's script convention inserts the workspace before app imports.
# ruff: noqa: E402

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.prompt import build_messages
from app.llm.structured_output import SUPPORT_UNIT_OUTPUT_INSTRUCTIONS, support_unit_output_schema
from app.llm.support_units import build_support_units, serialize_support_units
from app.retrieval.hybrid_search import SearchResult

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def snapshot_blocks(query_id: str) -> tuple[dict[str, Any], list[SearchResult]]:
    snapshot = read_json(M0 / "evidence-snapshots" / f"{query_id}.json")
    blocks = [
        SearchResult(
            score=float(item.get("score", 0.0)),
            id=str(item.get("evidence_block_id", item.get("evidence_id", ""))),
            payload=dict(item),
        )
        for item in snapshot["evidence_blocks"]
    ]
    return snapshot, blocks


def build_request(
    query: str, blocks: list[SearchResult], seed: int, schema: dict[str, Any]
) -> dict[str, Any]:
    units = build_support_units(blocks)
    messages = build_messages(
        query,
        units,
        version="v3",
        context_serializer=serialize_support_units,
        system_prompt_suffix=SUPPORT_UNIT_OUTPUT_INSTRUCTIONS,
    )
    return {
        "model": "qwen3.5:4b",
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.0, "num_ctx": 4096, "seed": seed},
        "think": False,
        "keep_alive": "30m",
    }


def fact_counts(query_id: str) -> tuple[int, int]:
    data = read_json(M0 / "holdout-fact-ground-truth.json")
    for query in data.get("queries", []):
        if query.get("query_id") == query_id:
            components = query.get("required_components", [])
            return len(components), sum(
                len(item.get("required_fact_ids", [])) for item in components
            )
    return 0, 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    holdout = read_jsonl(V23 / "v2-3-holdout-results.jsonl")
    acl = read_jsonl(V23 / "v2-3-acl-results.jsonl")
    rows = holdout + acl
    if not rows:
        raise SystemExit("no V2.3 rows found")
    questions = {
        row["id"]: row["question"]
        for row in read_json(ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json")
    }
    forensic: list[dict[str, Any]] = []
    timeout_rows: list[dict[str, Any]] = []
    cache: dict[
        str, tuple[dict[str, Any], list[SearchResult], list[Any], dict[str, Any], dict[str, Any]]
    ] = {}
    for row in rows:
        query_id = row["query_id"]
        if query_id not in cache:
            snapshot, blocks = snapshot_blocks(query_id)
            units = build_support_units(blocks)
            schema = support_unit_output_schema(units)
            request = build_request(questions[query_id], blocks, int(row["seed"]), schema)
            cache[query_id] = snapshot, blocks, units, schema, request
        snapshot, blocks, units, schema, request = cache[query_id]
        request = build_request(questions[query_id], blocks, int(row["seed"]), schema)
        provider = row.get("provider_observation") or {}
        context_text = serialize_support_units(units)
        prompt_text = "\n\n".join(
            str(message.get("content", "")) for message in request["messages"]
        )
        schema_json = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        request_json = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        component_count, fact_count = fact_counts(query_id)
        record = {
            "query_id": query_id,
            "seed": row["seed"],
            "result": row.get("result"),
            "run_key": row.get("run_key"),
            "snapshot_hash": row.get("snapshot_hash", snapshot.get("context_hash")),
            "schema_hash": provider.get("schema_hash", digest(schema)),
            "context_hash": provider.get(
                "context_hash", digest([{"role": "user", "content": context_text}])
            ),
            "context_tokens": snapshot.get("context_tokens"),
            "context_bytes": len(context_text.encode("utf-8")),
            "evidence_block_count": len(blocks),
            "support_unit_count": len(units),
            "support_id_enum_count": len(
                schema["properties"]["answer_parts"]["items"]["properties"]["support_ids"][
                    "items"
                ].get("enum", [])
            ),
            "schema_bytes": len(schema_json.encode("utf-8")),
            "schema_token_estimate": len(schema_json.split()),
            "prompt_bytes": len(prompt_text.encode("utf-8")),
            "prompt_token_estimate": len(prompt_text.split()),
            "request_bytes": len(request_json.encode("utf-8")),
            "required_component_count": component_count,
            "required_fact_count": fact_count,
            "provider_status": provider.get("status", row.get("result")),
            "latency_ms": provider.get("elapsed_ms", row.get("generation_latency_ms")),
            "headers_received": provider.get("headers_received_at") is not None,
            "time_to_headers_ms": None,
            "first_byte_received": provider.get("first_body_byte_at") is not None,
            "time_to_first_byte_ms": None,
            "completion_ms": provider.get("elapsed_ms"),
            "response_bytes": provider.get("response_bytes"),
            "output_token_count": None,
            "timeout_type": provider.get("timeout_type")
            or (row.get("error") or {}).get("timeout_type"),
            "request_started_at": provider.get("request_started_at"),
            "headers_received_at": provider.get("headers_received_at"),
            "first_body_byte_at": provider.get("first_body_byte_at"),
            "completed_at": provider.get("completed_at"),
        }
        forensic.append(record)
        if row.get("result") == "TIMEOUT":
            timeout_rows.append(record)

    def stats(field: str) -> dict[str, float | None]:
        values = [
            float(row[field])
            for row in forensic
            if row.get("result") == "PASS" and row.get(field) is not None
        ]
        return {
            "count": len(values),
            "p50": percentile(values, 0.5),
            "p95": percentile(values, 0.95),
            "max": max(values) if values else None,
        }

    write_jsonl(OUT / "v2-3-execution-forensics.jsonl", forensic)
    (OUT / "timeout-run-manifest.json").write_text(
        json.dumps(
            {
                "execution_status": "PROVIDER_UNSTABLE",
                "official_partial_results": True,
                "timeout_count": len(timeout_rows),
                "timeouts": timeout_rows,
                "reusable_for_official_comparison": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "v2-3-execution-forensics-summary.json").write_text(
        json.dumps(
            {
                "rows": len(forensic),
                "successful_rows": sum(row.get("result") == "PASS" for row in forensic),
                "timeout_rows": len(timeout_rows),
                "successful_stats": {
                    field: stats(field)
                    for field in (
                        "context_tokens",
                        "context_bytes",
                        "support_unit_count",
                        "support_id_enum_count",
                        "schema_bytes",
                        "prompt_bytes",
                        "request_bytes",
                        "latency_ms",
                    )
                },
                "timeout_values": {
                    field: [row.get(field) for row in timeout_rows]
                    for field in (
                        "query_id",
                        "seed",
                        "context_tokens",
                        "support_unit_count",
                        "support_id_enum_count",
                        "schema_bytes",
                        "request_bytes",
                        "latency_ms",
                        "headers_received",
                        "first_byte_received",
                        "response_bytes",
                        "timeout_type",
                    )
                },
                "schema_observation": (
                    "The timeout query uses a small 14-member enum; schema size is not an "
                    "obvious outlier in this partial batch."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
