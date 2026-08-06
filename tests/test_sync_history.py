from datetime import UTC, datetime, timedelta

from app.sync.history import SyncHistory
from app.sync.models import STATUS_ERROR, STATUS_RUNNING, STATUS_SUCCESS, TRIGGER_MANUAL


def _history(tmp_path) -> SyncHistory:
    return SyncHistory(tmp_path / "registry.db")


def test_start_run_creates_a_running_record(tmp_path):
    history = _history(tmp_path)

    run_id = history.start_run("filesystem", TRIGGER_MANUAL)
    run = history.get_run(run_id)

    assert run.source_type == "filesystem"
    assert run.trigger == TRIGGER_MANUAL
    assert run.status == STATUS_RUNNING
    assert run.finished_at is None
    assert isinstance(run.started_at, datetime)
    assert run.started_at.tzinfo is not None


def test_finish_run_records_success_stats(tmp_path):
    history = _history(tmp_path)
    run_id = history.start_run("filesystem", TRIGGER_MANUAL)

    history.finish_run(
        run_id,
        status=STATUS_SUCCESS,
        files_processed=3,
        files_skipped=5,
        files_deleted=1,
        chunks_upserted=42,
    )
    run = history.get_run(run_id)

    assert run.status == STATUS_SUCCESS
    assert run.finished_at is not None
    assert run.files_processed == 3
    assert run.files_skipped == 5
    assert run.files_deleted == 1
    assert run.chunks_upserted == 42
    assert run.error_message is None


def test_finish_run_records_error_message(tmp_path):
    history = _history(tmp_path)
    run_id = history.start_run("notion", TRIGGER_MANUAL)

    history.finish_run(run_id, status=STATUS_ERROR, error_message="boom")
    run = history.get_run(run_id)

    assert run.status == STATUS_ERROR
    assert run.error_message == "boom"


def test_finished_at_is_after_started_at(tmp_path):
    history = _history(tmp_path)
    before = datetime.now(UTC) - timedelta(seconds=1)
    run_id = history.start_run("filesystem", TRIGGER_MANUAL)

    history.finish_run(run_id, status=STATUS_SUCCESS)
    run = history.get_run(run_id)

    assert run.started_at >= before
    assert run.finished_at >= run.started_at


def test_get_run_returns_none_for_unknown_id(tmp_path):
    history = _history(tmp_path)

    assert history.get_run(999) is None


def test_list_runs_orders_most_recent_first(tmp_path):
    history = _history(tmp_path)
    first_id = history.start_run("filesystem", TRIGGER_MANUAL)
    second_id = history.start_run("filesystem", TRIGGER_MANUAL)

    runs = history.list_runs()

    assert [r.id for r in runs] == [second_id, first_id]


def test_list_runs_filters_by_source_type(tmp_path):
    history = _history(tmp_path)
    history.start_run("filesystem", TRIGGER_MANUAL)
    notion_id = history.start_run("notion", TRIGGER_MANUAL)

    runs = history.list_runs(source_type="notion")

    assert [r.id for r in runs] == [notion_id]


def test_list_runs_respects_limit(tmp_path):
    history = _history(tmp_path)
    for _ in range(5):
        history.start_run("filesystem", TRIGGER_MANUAL)

    runs = history.list_runs(limit=2)

    assert len(runs) == 2


def test_latest_run_returns_the_most_recent_for_that_source_type(tmp_path):
    history = _history(tmp_path)
    history.start_run("filesystem", TRIGGER_MANUAL)
    second_id = history.start_run("filesystem", TRIGGER_MANUAL)

    latest = history.latest_run("filesystem")

    assert latest.id == second_id


def test_latest_run_returns_none_when_no_runs_exist(tmp_path):
    history = _history(tmp_path)

    assert history.latest_run("filesystem") is None


def test_data_persists_across_separate_connections_to_the_same_file(tmp_path):
    db_path = tmp_path / "registry.db"
    first = SyncHistory(db_path)
    run_id = first.start_run("filesystem", TRIGGER_MANUAL)
    first.finish_run(run_id, status=STATUS_SUCCESS, files_processed=1)
    first.close()

    second = SyncHistory(db_path)
    run = second.get_run(run_id)

    assert run is not None
    assert run.status == STATUS_SUCCESS
    assert run.files_processed == 1
