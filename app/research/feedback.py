"""Tenant-scoped user reports; submitted snapshots are never trusted evidence."""

from __future__ import annotations

import builtins
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
    # What the reporter says is right; a reviewer must confirm it before it
    # becomes an evaluation candidate.
    expected_answer: str = Field(default="", max_length=2000)
    expected_source: str = Field(default="", max_length=500)
    expected_page: int | None = Field(default=None, ge=1, le=2000)


class Promotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Overrides the reporter's expected answer when the reviewer corrects it.
    expected_answer: str = Field(default="", max_length=2000)


class PromotionError(ValueError):
    pass


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
        self._db.execute("""CREATE TABLE IF NOT EXISTS evaluation_candidates (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, feedback_id TEXT NOT NULL UNIQUE,
            reviewer_id TEXT NOT NULL, row TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
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

    def promote(
        self, tenant: str, id: str, reviewer: str, body: Promotion
    ) -> dict[str, Any] | None:
        """Turn a reviewed report into an evaluation candidate; None if absent."""
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT * FROM research_feedback WHERE tenant_id=? AND id=?", (tenant, id)
            ).fetchone()
            if row is None:
                return None
            report = self._record(row)
            expected = body.expected_answer.strip() or report.get("expected_answer", "").strip()
            if not expected:
                raise PromotionError("An expected answer is required")
            now = datetime.now(UTC).isoformat()
            candidate = {
                "id": str(uuid.uuid4()),
                "question": report["question"],
                "expected_answer": expected,
                "expected_source": report.get("expected_source", ""),
                "expected_page": report.get("expected_page"),
                "reason": report["reason"],
                "origin": "user_feedback",
                "feedback_id": id,
                "created_at": now,
            }
            try:
                self._db.execute(
                    "INSERT INTO evaluation_candidates "
                    "(id, tenant_id, feedback_id, reviewer_id, row, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (candidate["id"], tenant, id, reviewer, json.dumps(candidate), now),
                )
            except sqlite3.IntegrityError as exc:
                raise PromotionError("Already promoted") from exc
            self._db.execute(
                "UPDATE research_feedback SET status='resolved', reviewer_id=?, updated_at=? "
                "WHERE tenant_id=? AND id=?",
                (reviewer, now, tenant, id),
            )
            return candidate

    def candidates(self, tenant: str) -> builtins.list[dict[str, Any]]:
        with self._lock:
            return [
                json.loads(row["row"])
                for row in self._db.execute(
                    "SELECT row FROM evaluation_candidates WHERE tenant_id=? "
                    "ORDER BY created_at, id",
                    (tenant,),
                )
            ]

    def close(self) -> None:
        with self._lock:
            self._db.close()
