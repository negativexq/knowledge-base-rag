import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.registry.models import DEFAULT_STATUS, DocumentRecord

# tenant_id is part of the PRIMARY KEY (not just a plain
# column) — the whole point is that two tenants using the identical
# (source_type, source_id) pair (e.g. both a "filesystem" source named
# "handbook.pdf") must never collide on one registry row. See
# _migrate_add_tenant_id_and_rebuild_pk for how an existing database gets
# here.
DEFAULT_TENANT_ID = "default"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    tenant_id      TEXT    NOT NULL,
    source_type    TEXT    NOT NULL,
    source_id      TEXT    NOT NULL,
    content_hash   TEXT    NOT NULL,
    last_synced_at TEXT    NOT NULL,
    version        INTEGER NOT NULL,
    status         TEXT    NOT NULL,
    chunk_count    INTEGER,
    pipeline_fingerprint TEXT,
    PRIMARY KEY (tenant_id, source_type, source_id)
);
"""


def _migrate_add_tenant_id_and_rebuild_pk(conn: sqlite3.Connection) -> None:
    # SQLite has no ALTER TABLE operation for adding a column to a PRIMARY
    # KEY, so widening the PK from (source_type, source_id) to
    # (tenant_id, source_type, source_id) requires a real table rebuild,
    # not just an ADD COLUMN. Every pre-existing row is backfilled with
    # DEFAULT_TENANT_ID ("default") — the same default
    # app/ingestion/models.py::Chunk.tenant_id and app/sync/manager.py's
    # tenant_ids.get(source_type, "default") fallback use, so a registry
    # row and the Qdrant points it describes agree on which tenant owns
    # them even for data that predates this schema. Run AFTER the
    # chunk_count/pipeline_fingerprint migrations below, so this rebuild
    # copies their already-corrected shape forward, not the legacy one.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "tenant_id" in columns:
        return
    conn.execute("ALTER TABLE documents RENAME TO documents_pre_23")
    conn.execute(_SCHEMA)
    conn.execute(
        f"""
        INSERT INTO documents
            (tenant_id, source_type, source_id, content_hash, last_synced_at, version, status,
             chunk_count, pipeline_fingerprint)
        SELECT
            '{DEFAULT_TENANT_ID}', source_type, source_id, content_hash, last_synced_at, version,
            status, chunk_count, pipeline_fingerprint
        FROM documents_pre_23;
        """
    )
    conn.execute("DROP TABLE documents_pre_23")


def _migrate_add_pipeline_fingerprint_column(conn: sqlite3.Connection) -> None:
    # Keep this nullable: pre-existing rows are intentionally marked as
    # never fingerprinted, not assigned a value that could collide with a
    # real digest. See app/ingestion/fingerprint.py.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "pipeline_fingerprint" not in columns:
        conn.execute("ALTER TABLE documents ADD COLUMN pipeline_fingerprint TEXT")


def _migrate_add_chunk_count_column(conn: sqlite3.Connection) -> None:
    # CREATE TABLE IF NOT EXISTS alone doesn't add a new
    # column to a table that already exists from before this column was
    # introduced — a real ALTER TABLE migration is needed for those.
    # Nullable, no default — an ADD COLUMN with no default
    # leaves every existing row NULL, which is exactly the correct
    # "never tracked" state for anything that predates this column
    # (distinct from a real, tracked 0).
    #
    # An older database may already have this column as NOT NULL DEFAULT 0.
    # The membership check below detects that shape and rebuilds the table;
    # the NOT NULL constraint otherwise survives, and DocumentRegistry's own
    # public chunk_count=None default could raise sqlite3.IntegrityError
    # against it. SQLite has no ALTER COLUMN to relax NOT NULL, so a
    # genuinely NOT NULL chunk_count column is fixed by rebuilding the
    # table: rename it aside, create the (now nullable) real schema,
    # copy every row across — converting the ambiguous legacy 0 to NULL
    # specifically (not every value: a real non-zero count already is
    # unambiguous and is kept
    # as-is; only 0 was ever ambiguous between "genuinely empty" and
    # "the column's own untouched default") — then drop the renamed
    # original.
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "chunk_count" not in columns:
        conn.execute("ALTER TABLE documents ADD COLUMN chunk_count INTEGER")
        return

    # PRAGMA table_info row shape: (cid, name, type, notnull, dflt_value, pk)
    still_not_null = columns["chunk_count"][3] == 1
    if still_not_null:
        conn.execute("ALTER TABLE documents RENAME TO documents_pre_17_4")
        conn.execute(
            """
            CREATE TABLE documents (
                source_type    TEXT    NOT NULL,
                source_id      TEXT    NOT NULL,
                content_hash   TEXT    NOT NULL,
                last_synced_at TEXT    NOT NULL,
                version        INTEGER NOT NULL,
                status         TEXT    NOT NULL,
                chunk_count    INTEGER,
                PRIMARY KEY (source_type, source_id)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO documents
                (source_type, source_id, content_hash, last_synced_at, version, status,
                 chunk_count)
            SELECT
                source_type, source_id, content_hash, last_synced_at, version, status,
                CASE WHEN chunk_count = 0 THEN NULL ELSE chunk_count END
            FROM documents_pre_17_4;
            """
        )
        conn.execute("DROP TABLE documents_pre_17_4")


_METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS registry_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_INDEX_SCHEMA_VERSION_KEY = "index_schema_version"

# Bumped whenever a change to how Qdrant point identity or
# registry content is derived would leave EXISTING (already-synced) data
# silently wrong until its next real content edit — content_hash alone
# can't detect this, since it's unrelated to the point-ID formula.
# Version 2 includes source_id in point_id_for, so
# two documents with identical content no longer collide on point ID).
# Version 3 includes heading occurrence, so repeated identical
# Markdown heading paths now get distinct point IDs and citation
# locations) — an unchanged document's content_hash can never detect
# this on its own, same reasoning as version 2's bump. See
# Version 4 is tenant-aware point identity — point_id_for now
# prepends chunk.tenant_id to its canonical key, so EVERY previously
# indexed point's ID changes (not just points for tenants other than
# "default" — the default tenant's own points move too, since the old
# key format never included any tenant segment at all). See
# app/ingestion/qdrant_store.py::point_id_for and docs/security.md.
# Version 1 is implicit: any registry with no stored version at all.
CURRENT_INDEX_SCHEMA_VERSION = 4


class IndexSchemaMismatchError(Exception):
    """Raised by ensure_index_schema_version() when this registry's
    tracked index schema version is older than what this code expects —
    e.g. a registry built before source_id was included in point_id_for (which
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
    ordinary boot.

    Fix: wipe and rebuild the index —
        docker compose down -v && docker compose up
    A fresh (empty) registry self-stamps the current version
    automatically on next boot, no further action needed.
    """

# version only increments when content_hash actually changes — re-syncing
# unchanged content (the common case) just refreshes last_synced_at, so a
# incremental sync's "skip unchanged documents" logic can tell "still current"
# apart from "content actually changed" using version alone.
_UPSERT = """
INSERT INTO documents
    (tenant_id, source_type, source_id, content_hash, last_synced_at, version, status,
     chunk_count, pipeline_fingerprint)
VALUES (:tenant_id, :source_type, :source_id, :content_hash, :last_synced_at, 1, :status,
        :chunk_count, :pipeline_fingerprint)
ON CONFLICT(tenant_id, source_type, source_id) DO UPDATE SET
    content_hash = excluded.content_hash,
    last_synced_at = excluded.last_synced_at,
    status = excluded.status,
    chunk_count = excluded.chunk_count,
    pipeline_fingerprint = excluded.pipeline_fingerprint,
    version = CASE WHEN documents.content_hash != excluded.content_hash
                    THEN documents.version + 1
                    ELSE documents.version
              END;
"""

_SELECT_ONE = """
SELECT tenant_id, source_type, source_id, content_hash, last_synced_at, version, status,
       chunk_count, pipeline_fingerprint
FROM documents WHERE tenant_id = ? AND source_type = ? AND source_id = ?;
"""

_SELECT_ALL = """
SELECT tenant_id, source_type, source_id, content_hash, last_synced_at, version, status,
       chunk_count, pipeline_fingerprint
FROM documents ORDER BY tenant_id, source_type, source_id;
"""

_SELECT_BY_SOURCE_TYPE = _SELECT_ALL.replace(
    "FROM documents ORDER BY", "FROM documents WHERE source_type = ? ORDER BY"
)

_SELECT_BY_TENANT = _SELECT_ALL.replace(
    "FROM documents ORDER BY", "FROM documents WHERE tenant_id = ? ORDER BY"
)

_SELECT_BY_TENANT_AND_SOURCE_TYPE = _SELECT_ALL.replace(
    "FROM documents ORDER BY", "FROM documents WHERE tenant_id = ? AND source_type = ? ORDER BY"
)

_DELETE_ONE = "DELETE FROM documents WHERE tenant_id = ? AND source_type = ? AND source_id = ?;"


def _row_to_record(row: tuple) -> DocumentRecord:
    (
        tenant_id,
        source_type,
        source_id,
        content_hash,
        last_synced_at,
        version,
        status,
        chunk_count,
        pipeline_fingerprint,
    ) = row
    return DocumentRecord(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        content_hash=content_hash,
        last_synced_at=datetime.fromisoformat(last_synced_at),
        version=version,
        status=status,
        chunk_count=chunk_count,
        pipeline_fingerprint=pipeline_fingerprint,
    )


class DocumentRegistry:
    """SQLite-backed metadata store for tracking known documents across all
    source types — the foundation incremental sync compares
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
            _migrate_add_chunk_count_column(self._conn)
            _migrate_add_pipeline_fingerprint_column(self._conn)
            _migrate_add_tenant_id_and_rebuild_pk(self._conn)
            self._conn.execute(_METADATA_SCHEMA)

    def upsert_document(
        self,
        tenant_id: str,
        source_type: str,
        source_id: str,
        content_hash: str,
        status: str = DEFAULT_STATUS,
        chunk_count: int | None = None,
        pipeline_fingerprint: str | None = None,
    ) -> DocumentRecord:
        # tenant_id has no default — every write call site (only
        # app/ingestion/ingest.py::ingest_connector) must say explicitly
        # which tenant owns this row, sourced from server-side connector
        # configuration (app/wiring.py::connector_tenant_ids), never a
        # request value. See app/ingestion/models.py::Chunk.tenant_id for
        # the matching Qdrant-payload half of this.
        #
        # Timestamp is written as an ISO 8601 string, not a datetime
        # object — sqlite3's implicit datetime adapters were deprecated
        # in Python 3.12, so this avoids relying on them or writing a
        # custom adapter.
        last_synced_at = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                _UPSERT,
                {
                    "tenant_id": tenant_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "content_hash": content_hash,
                    "last_synced_at": last_synced_at,
                    "status": status,
                    "chunk_count": chunk_count,
                    "pipeline_fingerprint": pipeline_fingerprint,
                },
            )
        return self.get_document(tenant_id, source_type, source_id)

    def get_document(
        self, tenant_id: str, source_type: str, source_id: str
    ) -> DocumentRecord | None:
        row = self._conn.execute(_SELECT_ONE, (tenant_id, source_type, source_id)).fetchone()
        return _row_to_record(row) if row else None

    def delete_document(self, tenant_id: str, source_type: str, source_id: str) -> None:
        with self._conn:
            self._conn.execute(_DELETE_ONE, (tenant_id, source_type, source_id))

    def has_changed(
        self, tenant_id: str, source_type: str, source_id: str, content_hash: str
    ) -> bool:
        existing = self.get_document(tenant_id, source_type, source_id)
        if existing is None:
            return True
        return existing.content_hash != content_hash

    def list_documents(
        self, tenant_id: str | None = None, source_type: str | None = None
    ) -> list[DocumentRecord]:
        """tenant_id=None means ALL tenants — an admin/system-only query
        shape (app/api/sources.py's user-facing endpoint always passes a
        real tenant_id; only internal maintenance code should ever pass
        None here). Combining both filters is supported since
        app/ingestion/ingest.py::ingest_connector needs exactly
        "this tenant's documents of this source_type" for its
        deletion-detection phase.
        """
        if tenant_id is not None and source_type is not None:
            rows = self._conn.execute(
                _SELECT_BY_TENANT_AND_SOURCE_TYPE, (tenant_id, source_type)
            ).fetchall()
        elif tenant_id is not None:
            rows = self._conn.execute(_SELECT_BY_TENANT, (tenant_id,)).fetchall()
        elif source_type is not None:
            rows = self._conn.execute(_SELECT_BY_SOURCE_TYPE, (source_type,)).fetchall()
        else:
            rows = self._conn.execute(_SELECT_ALL).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_index_schema_version(self) -> int | None:
        row = self._conn.execute(
            "SELECT value FROM registry_metadata WHERE key = ?", (_INDEX_SCHEMA_VERSION_KEY,)
        ).fetchone()
        if row is None:
            return None
        try:
            return int(row[0])
        except ValueError as exc:
            # A corrupted/non-numeric stored value must fail the same clear
            # way every other schema-mismatch path
            # in this codebase does, not a raw ValueError.
            raise IndexSchemaMismatchError(
                f"registry_metadata.{_INDEX_SCHEMA_VERSION_KEY!r} is not a valid integer: "
                f"{row[0]!r}. Wipe and rebuild the index: "
                "`docker compose down -v && docker compose up`."
            ) from exc

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
        # exist (a registry that predates this tracking mechanism entirely),
        # or an explicitly stored version is behind current.
        effective_stored = stored if stored is not None else 1
        raise IndexSchemaMismatchError(
            f"registry index schema version is {effective_stored}, this code requires "
            f"{CURRENT_INDEX_SCHEMA_VERSION}. Wipe and rebuild the index: "
            "`docker compose down -v && docker compose up`. See "
            "IndexSchemaMismatchError's docstring for why this doesn't happen automatically."
        )

    def get_metadata(self, key: str) -> str | None:
        """Generic key-value read on the same registry_metadata table
        get_index_schema_version already uses — migrations reuse this
        table (rather than adding a new one) to record which physical
        Qdrant collection/alias is active, the previous one (rollback
        target), and the current migration_id, so a process restart can
        answer "what's active, what's the rollback target, what
        migration state are we in" without depending on the migration
        artifact JSON file still being present. See
        app/migration/embedding_migration.py.
        """
        row = self._conn.execute(
            "SELECT value FROM registry_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO registry_metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_metadata(self, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM registry_metadata WHERE key = ?", (key,))

    def close(self) -> None:
        self._conn.close()
