"""Sprint 22: typed migration state — a plain enum + dataclass, not a
workflow-engine framework (the spec explicitly asks to avoid one). All
state needed to resume/inspect a migration after a process restart is
just these fields, serialized as JSON to
artifacts/embedding-migration-sprint22/migration-result.json and mirrored
into the registry's existing key-value metadata table (Sprint 26) so
`status`/`rollback` work even if the artifact file is missing.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


class MigrationStatus(str, Enum):
    PLANNED = "PLANNED"
    INDEXING = "INDEXING"
    VALIDATING = "VALIDATING"
    READY_TO_SWITCH = "READY_TO_SWITCH"
    SWITCHING = "SWITCHING"
    ACTIVE = "ACTIVE"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MigrationManifest:
    migration_id: str
    started_at: str
    source_collection: str
    source_fingerprint: str
    target_collection: str
    target_fingerprint: str
    target_model: str
    target_dimension: int
    expected_document_count: int
    expected_chunk_count: int
    status: MigrationStatus = MigrationStatus.PLANNED
    documents_completed: int = 0
    chunks_completed: int = 0
    updated_at: str = field(default_factory=utcnow_iso)
    finished_at: str | None = None
    error: str | None = None
    validation: dict | None = None
    activated_at: str | None = None
    rolled_back_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str | Path) -> MigrationManifest:
        data = json.loads(Path(path).read_text())
        data["status"] = MigrationStatus(data["status"])
        return cls(**data)

    def touch(self) -> None:
        self.updated_at = utcnow_iso()
