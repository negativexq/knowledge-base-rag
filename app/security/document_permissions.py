"""Server-managed document permissions, independent of embeddings/index versions."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.security.models import DocumentRules, UserContext

Principal = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S(?:.*\S)?$")]


class DocumentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=500)
    access: Literal["tenant", "restricted"]
    user_ids: list[Principal] = Field(default_factory=list, max_length=200)
    group_ids: list[Principal] = Field(default_factory=list, max_length=200)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def coherent_grants(self) -> DocumentPolicy:
        if self.access == "tenant" and (self.user_ids or self.group_ids):
            raise ValueError("Tenant-wide access cannot also carry principal grants")
        return self


class PolicyConflictError(Exception):
    pass


@dataclass(frozen=True)
class PermissionView:
    store: DocumentPermissionStore
    user: UserContext

    def rules(self) -> DocumentRules:
        return self.store.rules(self.user)


class DocumentPermissionStore:
    def __init__(
        self, path: str | Path, default_access: Literal["tenant", "restricted"] = "restricted"
    ):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.default_access = default_access
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("""CREATE TABLE IF NOT EXISTS document_permissions (
            tenant_id TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
            policy TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, source_type, source_id)
        )""")
        self._db.commit()

    def get(self, tenant: str, source_type: str, source_id: str) -> DocumentPolicy:
        with self._lock:
            row = self._db.execute(
                "SELECT policy FROM document_permissions "
                "WHERE tenant_id=? AND source_type=? AND source_id=?",
                (tenant, source_type, source_id),
            ).fetchone()
        return (
            DocumentPolicy.model_validate_json(row["policy"])
            if row
            else DocumentPolicy(
                source_type=source_type,
                source_id=source_id,
                access=self.default_access,
            )
        )

    def set(self, tenant: str, actor: str, policy: DocumentPolicy) -> DocumentPolicy:
        with self._lock, self._db:
            # Lock before checking revision, including across worker processes.
            self._db.execute("BEGIN IMMEDIATE")
            current = self.get(tenant, policy.source_type, policy.source_id)
            if current.revision != policy.revision:
                raise PolicyConflictError("Document policy has changed")
            saved = policy.model_copy(update={"revision": current.revision + 1})
            self._db.execute(
                "INSERT OR REPLACE INTO document_permissions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tenant,
                    policy.source_type,
                    policy.source_id,
                    saved.model_dump_json(),
                    actor,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return saved

    def for_user(self, user: UserContext) -> PermissionView:
        return PermissionView(self, user)

    def rules(self, user: UserContext) -> DocumentRules:
        with self._lock:
            rows = self._db.execute(
                "SELECT policy FROM document_permissions WHERE tenant_id=?", (user.tenant_id,)
            ).fetchall()
        allowed: set[tuple[str, str]] = set()
        denied: set[tuple[str, str]] = set()
        for row in rows:
            policy = DocumentPolicy.model_validate_json(row["policy"])
            permitted = (
                policy.access == "tenant"
                or user.user_id in policy.user_ids
                or bool(user.group_ids.intersection(policy.group_ids))
            )
            (allowed if permitted else denied).add((policy.source_type, policy.source_id))
        return DocumentRules(self.default_access, frozenset(allowed), frozenset(denied))

    def close(self) -> None:
        with self._lock:
            self._db.close()
