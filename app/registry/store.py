import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.registry.models import DEFAULT_STATUS, DocumentRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    source_type    TEXT    NOT NULL,
    source_id      TEXT    NOT NULL,
    content_hash   TEXT    NOT NULL,
    last_synced_at TEXT    NOT NULL,
    version        INTEGER NOT NULL,
    status         TEXT    NOT NULL,
    PRIMARY KEY (source_type, source_id)
);
"""

# version only increments when content_hash actually changes — re-syncing
# unchanged content (the common case) just refreshes last_synced_at, so a
# later sprint's "skip unchanged documents" logic can tell "still current"
# apart from "content actually changed" using version alone.
_UPSERT = """
INSERT INTO documents (source_type, source_id, content_hash, last_synced_at, version, status)
VALUES (:source_type, :source_id, :content_hash, :last_synced_at, 1, :status)
ON CONFLICT(source_type, source_id) DO UPDATE SET
    content_hash = excluded.content_hash,
    last_synced_at = excluded.last_synced_at,
    status = excluded.status,
    version = CASE WHEN documents.content_hash != excluded.content_hash
                    THEN documents.version + 1
                    ELSE documents.version
              END;
"""

_SELECT_ONE = """
SELECT source_type, source_id, content_hash, last_synced_at, version, status
FROM documents WHERE source_type = ? AND source_id = ?;
"""

_SELECT_ALL = """
SELECT source_type, source_id, content_hash, last_synced_at, version, status
FROM documents ORDER BY source_type, source_id;
"""

_SELECT_BY_SOURCE_TYPE = _SELECT_ALL.replace(
    "FROM documents ORDER BY", "FROM documents WHERE source_type = ? ORDER BY"
)

_DELETE_ONE = "DELETE FROM documents WHERE source_type = ? AND source_id = ?;"


def _row_to_record(row: tuple) -> DocumentRecord:
    source_type, source_id, content_hash, last_synced_at, version, status = row
    return DocumentRecord(
        source_type=source_type,
        source_id=source_id,
        content_hash=content_hash,
        last_synced_at=datetime.fromisoformat(last_synced_at),
        version=version,
        status=status,
    )


class DocumentRegistry:
    """SQLite-backed metadata store for tracking known documents across all
    source types — the foundation incremental sync (Sprint 4) compares
    against. Not async: sqlite3 file I/O here is local and fast, matching
    QdrantStore's precedent of a synchronous store called from async
    ingestion code.
    """

    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        with self._conn:
            self._conn.execute(_SCHEMA)

    def upsert_document(
        self,
        source_type: str,
        source_id: str,
        content_hash: str,
        status: str = DEFAULT_STATUS,
    ) -> DocumentRecord:
        # Timestamp is written as an ISO 8601 string, not a datetime object —
        # sqlite3's implicit datetime adapters were deprecated in Python
        # 3.12, so this avoids relying on them or writing a custom adapter.
        last_synced_at = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                _UPSERT,
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "content_hash": content_hash,
                    "last_synced_at": last_synced_at,
                    "status": status,
                },
            )
        return self.get_document(source_type, source_id)

    def get_document(self, source_type: str, source_id: str) -> DocumentRecord | None:
        row = self._conn.execute(_SELECT_ONE, (source_type, source_id)).fetchone()
        return _row_to_record(row) if row else None

    def delete_document(self, source_type: str, source_id: str) -> None:
        with self._conn:
            self._conn.execute(_DELETE_ONE, (source_type, source_id))

    def has_changed(self, source_type: str, source_id: str, content_hash: str) -> bool:
        existing = self.get_document(source_type, source_id)
        if existing is None:
            return True
        return existing.content_hash != content_hash

    def list_documents(self, source_type: str | None = None) -> list[DocumentRecord]:
        if source_type is None:
            rows = self._conn.execute(_SELECT_ALL).fetchall()
        else:
            rows = self._conn.execute(_SELECT_BY_SOURCE_TYPE, (source_type,)).fetchall()
        return [_row_to_record(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
