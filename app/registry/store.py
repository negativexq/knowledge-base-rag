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

_METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS registry_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_INDEX_SCHEMA_VERSION_KEY = "index_schema_version"

# Sprint 17.1: bumped whenever a change to how Qdrant point identity or
# registry content is derived would leave EXISTING (already-synced) data
# silently wrong until its next real content edit — content_hash alone
# can't detect this, since it's unrelated to the point-ID formula.
# Version 2 = Sprint 17's point_id_for fix (now includes source_id, so
# two documents with identical content no longer collide on point ID).
# Version 1 is implicit: any registry with no stored version at all.
CURRENT_INDEX_SCHEMA_VERSION = 2


class IndexSchemaMismatchError(Exception):
    """Raised by ensure_index_schema_version() when this registry's
    tracked index schema version is older than what this code expects —
    e.g. a registry built before Sprint 17's point_id_for fix (which
    added source_id to the point-ID key) may already have silently
    collided/overwritten points for documents with identical content but
    different sources, and incremental sync's content_hash comparison
    can never detect or self-heal that (the hash is unrelated to the
    point-ID formula, so an unaffected document is never re-synced).

    Deliberately fail-fast rather than an automatic re-index: the same
    "don't guess, tell the human" policy QdrantStore.ensure_collection()
    already applies to schema mismatches (see
    UnexpectedCollectionSchemaError) — an automatic re-index would need
    real, possibly slow or failing, network calls per connector before
    the app can even serve /health, hidden inside what looks like an
    ordinary boot. See docs/sprint-17-1-plan.md.

    Fix: wipe and rebuild the index —
        docker compose down -v && docker compose up
    A fresh (empty) registry self-stamps the current version
    automatically on next boot, no further action needed.
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
        # check_same_thread=False: an ASGI server (uvicorn, or FastAPI's
        # TestClient in tests — confirmed via a real ProgrammingError, not
        # assumed) can run request handlers in a worker thread different
        # from the one that constructed this object. Usage stays
        # effectively single-threaded (one request at a time in that
        # worker), so this doesn't introduce real concurrent access — it
        # just allows the creation-thread/usage-thread mismatch.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        with self._conn:
            self._conn.execute(_SCHEMA)
            self._conn.execute(_METADATA_SCHEMA)

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

    def get_index_schema_version(self) -> int | None:
        row = self._conn.execute(
            "SELECT value FROM registry_metadata WHERE key = ?", (_INDEX_SCHEMA_VERSION_KEY,)
        ).fetchone()
        return int(row[0]) if row else None

    def _set_index_schema_version(self, version: int) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO registry_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_INDEX_SCHEMA_VERSION_KEY, str(version)),
            )

    def ensure_index_schema_version(self) -> None:
        """Raises IndexSchemaMismatchError if this registry's index
        predates CURRENT_INDEX_SCHEMA_VERSION — called once at app
        startup (app/wiring.py::build_app()) so a stale index is caught
        before the app starts serving traffic, not discovered later by a
        confused user. See IndexSchemaMismatchError's docstring for why
        this is fail-fast, not an automatic re-index.
        """
        stored = self.get_index_schema_version()
        if stored == CURRENT_INDEX_SCHEMA_VERSION:
            return
        if stored is None and not self.list_documents():
            # Genuinely fresh install — nothing to migrate. Self-stamps
            # so a `docker compose down -v` + `up` cycle resolves a
            # mismatch automatically on next boot, no operator action
            # beyond the wipe they already had to do.
            self._set_index_schema_version(CURRENT_INDEX_SCHEMA_VERSION)
            return
        # Either no version was ever recorded but real documents already
        # exist (a registry that predates this tracking mechanism
        # entirely, and therefore predates Sprint 17's point-ID fix too),
        # or an explicitly stored version is behind current.
        effective_stored = stored if stored is not None else 1
        raise IndexSchemaMismatchError(
            f"registry index schema version is {effective_stored}, this code requires "
            f"{CURRENT_INDEX_SCHEMA_VERSION}. Wipe and rebuild the index: "
            "`docker compose down -v && docker compose up`. See "
            "IndexSchemaMismatchError's docstring for why this doesn't happen automatically."
        )

    def close(self) -> None:
        self._conn.close()
