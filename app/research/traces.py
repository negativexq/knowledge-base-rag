"""Tenant/user-owned request trace index. Stores metadata, never model content."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import trace

from app.llm.agent_observability import RequestUsage, operation, outcome, usage_scope

logger = logging.getLogger(__name__)


class TraceStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("""CREATE TABLE IF NOT EXISTS request_traces (
            trace_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
            started_at TEXT NOT NULL, record TEXT NOT NULL
        )""")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS traces_owner_date "
            "ON request_traces(tenant_id, user_id, started_at)"
        )
        self._db.commit()

    def save(self, record: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO request_traces VALUES (?, ?, ?, ?, ?)",
                (
                    record["trace_id"],
                    record["tenant_id"],
                    record["user_id"],
                    record["started_at"],
                    json.dumps(record, allow_nan=False),
                ),
            )

    def get(self, id: str, tenant: str, user: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM request_traces WHERE trace_id=? AND tenant_id=?", (id, tenant)
            ).fetchone()
        if row is None or (user is not None and row["user_id"] != user):
            return None
        record: dict[str, Any] = json.loads(row["record"])
        return record

    def list(self, tenant: str, user: str | None = None, offset: int = 0) -> list[dict[str, Any]]:
        sql, args = "SELECT record FROM request_traces WHERE tenant_id=?", [tenant]
        if user is not None:
            sql += " AND user_id=?"
            args.append(user)
        with self._lock:
            rows = self._db.execute(
                sql + " ORDER BY started_at DESC LIMIT 50 OFFSET ?", [*args, offset]
            ).fetchall()
        return [json.loads(row["record"]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()


@contextmanager
def request_trace(
    *,
    tracer: trace.Tracer,
    tenant: str | None,
    user: str | None,
    usage: RequestUsage,
    store: TraceStore | None,
    pipeline: str,
    parent_trace_id: str | None = None,
) -> Iterator[trace.Span]:
    started = time.monotonic()
    stamp = datetime.now(UTC).isoformat()
    with (
        operation(
            "chat_request",
            # A client-supplied traceparent must not select/overwrite an owned
            # trace index entry. Retain HTTP correlation as an OTel link.
            new_root=True,
            tracer=tracer,
            attributes={
                "security.tenant_id": tenant,
                "research.user_id": user,
                "research.pipeline": pipeline,
                "research.parent_trace_id": parent_trace_id,
            },
        ) as span,
        usage_scope(usage),
    ):
        context = span.get_span_context()
        record: dict[str, Any] = {
            "trace_id": format(context.trace_id, "032x"),
            "span_id": format(context.span_id, "016x"),
            "tenant_id": tenant,
            "user_id": user,
            "started_at": stamp,
            "outcome": "running",
            "pipeline": pipeline,
            "parent_trace_id": parent_trace_id,
        }

        def persist() -> None:
            if store is not None and context.is_valid and tenant and user:
                try:
                    store.save(record)
                except Exception as exc:
                    logger.warning("trace_index_write_failed error_class=%s", type(exc).__name__)

        persist()
        try:
            yield span
        except BaseException as exc:
            name = type(exc).__name__
            state = (
                "cancelled"
                if name in {"CancelledError", "GeneratorExit"}
                else "timeout"
                if isinstance(exc, TimeoutError)
                else "failed"
            )
            outcome(span, state, name if state != "cancelled" else None)
            record["outcome"] = state
            record["error_type"] = name if state != "cancelled" else None
            raise
        finally:
            attrs = getattr(span, "attributes", {})
            state = attrs.get("research.outcome", record["outcome"])
            record["outcome"] = "completed" if state == "running" else state
            record["error_type"] = attrs.get("error.type", record.get("error_type"))
            record["duration_ms"] = (time.monotonic() - started) * 1000
            record["usage"] = usage.snapshot()
            for key, value in usage.snapshot().items():
                if isinstance(value, int | float | bool):
                    span.set_attribute("research." + key, value)
            persist()
