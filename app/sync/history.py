import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.sync.models import STATUS_RUNNING, SyncRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type     TEXT    NOT NULL,
    trigger         TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    files_processed INTEGER,
    files_skipped   INTEGER,
    files_deleted   INTEGER,
    chunks_upserted INTEGER,
    error_message   TEXT
);
"""

_COLUMNS = (
    "id, source_type, trigger, status, started_at, finished_at, "
    "files_processed, files_skipped, files_deleted, chunks_upserted, error_message"
)

_INSERT = """
INSERT INTO sync_runs (source_type, trigger, status, started_at)
VALUES (:source_type, :trigger, :status, :started_at);
"""

_FINISH = """
UPDATE sync_runs SET
    status = :status,
    finished_at = :finished_at,
    files_processed = :files_processed,
    files_skipped = :files_skipped,
    files_deleted = :files_deleted,
    chunks_upserted = :chunks_upserted,
    error_message = :error_message
WHERE id = :run_id;
"""

_SELECT_ONE = f"SELECT {_COLUMNS} FROM sync_runs WHERE id = ?;"

_SELECT_ALL = f"SELECT {_COLUMNS} FROM sync_runs ORDER BY id DESC LIMIT ?;"

_SELECT_BY_SOURCE_TYPE = (
    f"SELECT {_COLUMNS} FROM sync_runs WHERE source_type = ? ORDER BY id DESC LIMIT ?;"
)


def _row_to_run(row: tuple) -> SyncRun:
    (
        run_id,
        source_type,
        trigger,
        status,
        started_at,
        finished_at,
        files_processed,
        files_skipped,
        files_deleted,
        chunks_upserted,
        error_message,
    ) = row
    return SyncRun(
        id=run_id,
        source_type=source_type,
        trigger=trigger,
        status=status,
        started_at=datetime.fromisoformat(started_at),
        finished_at=datetime.fromisoformat(finished_at) if finished_at else None,
        files_processed=files_processed,
        files_skipped=files_skipped,
        files_deleted=files_deleted,
        chunks_upserted=chunks_upserted,
        error_message=error_message,
    )


class SyncHistory:
    """SQLite-backed record of every sync run — the data source for
    Sprint 10's "Sync Status" page. Same db file as DocumentRegistry
    (registry_db_path), a separate table — one metadata database is enough,
    no need for a second file/connection-pattern.
    """

    def __init__(self, db_path: str | Path):
        # check_same_thread=False — see the same note in
        # app/registry/store.py: an ASGI server can run handlers in a
        # worker thread different from the construction thread.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        with self._conn:
            self._conn.execute(_SCHEMA)

    def start_run(self, source_type: str, trigger: str) -> int:
        started_at = datetime.now(UTC).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                _INSERT,
                {
                    "source_type": source_type,
                    "trigger": trigger,
                    "status": STATUS_RUNNING,
                    "started_at": started_at,
                },
            )
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        status: str,
        files_processed: int | None = None,
        files_skipped: int | None = None,
        files_deleted: int | None = None,
        chunks_upserted: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                _FINISH,
                {
                    "run_id": run_id,
                    "status": status,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "files_processed": files_processed,
                    "files_skipped": files_skipped,
                    "files_deleted": files_deleted,
                    "chunks_upserted": chunks_upserted,
                    "error_message": error_message,
                },
            )

    def get_run(self, run_id: int) -> SyncRun | None:
        row = self._conn.execute(_SELECT_ONE, (run_id,)).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(self, source_type: str | None = None, limit: int = 50) -> list[SyncRun]:
        if source_type is None:
            rows = self._conn.execute(_SELECT_ALL, (limit,)).fetchall()
        else:
            rows = self._conn.execute(_SELECT_BY_SOURCE_TYPE, (source_type, limit)).fetchall()
        return [_row_to_run(row) for row in rows]

    def latest_run(self, source_type: str) -> SyncRun | None:
        runs = self.list_runs(source_type=source_type, limit=1)
        return runs[0] if runs else None

    def close(self) -> None:
        self._conn.close()
