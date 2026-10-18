"""Tenant-scoped user reports; submitted snapshots are never trusted evidence."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=6000)
    answer: str = Field(min_length=1, max_length=30000)
    claim: str = Field(default="", max_length=8000)
    reason: Literal["incorrect", "unsupported", "outdated", "incomplete", "other"]
    note: str = Field(default="", max_length=4000)
    support_ids: list[str] = Field(default_factory=list, max_length=100)
    trace_id: str | None = Field(default=None, max_length=64)


class FeedbackReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["triaged", "resolved", "dismissed"]
    note: str = Field(default="", max_length=4000)


class FeedbackStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("""CREATE TABLE IF NOT EXISTS research_feedback (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
            snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            reviewer_id TEXT, reviewer_note TEXT NOT NULL DEFAULT ''
        )""")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS feedback_tenant_date "
            "ON research_feedback(tenant_id, created_at)"
        )
        self._db.commit()

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value.update(json.loads(value.pop("snapshot")))
        value["snapshot_origin"] = "user_submitted"
        return value

    def add(self, tenant: str, user: str, body: FeedbackRequest) -> dict[str, Any]:
        id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO research_feedback "
                "(id, tenant_id, user_id, snapshot, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (id, tenant, user, body.model_dump_json(), now, now),
            )
            row = self._db.execute("SELECT * FROM research_feedback WHERE id=?", (id,)).fetchone()
            return self._record(row)

    def list(
        self,
        tenant: str,
        *,
        user: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM research_feedback WHERE tenant_id=?"
        args: list[Any] = [tenant]
        if user is not None:
            sql += " AND user_id=?"
            args.append(user)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC, id LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        with self._lock:
            return [self._record(row) for row in self._db.execute(sql, args)]

    def review(
        self, tenant: str, id: str, reviewer: str, body: FeedbackReview
    ) -> dict[str, Any] | None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE research_feedback SET status=?, reviewer_note=?, "
                "reviewer_id=?, updated_at=? WHERE tenant_id=? AND id=?",
                (body.status, body.note, reviewer, datetime.now(UTC).isoformat(), tenant, id),
            )
            row = self._db.execute(
                "SELECT * FROM research_feedback WHERE tenant_id=? AND id=?", (tenant, id)
            ).fetchone()
            return self._record(row) if row else None

    def close(self) -> None:
        with self._lock:
            self._db.close()
