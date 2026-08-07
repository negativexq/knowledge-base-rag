from fastapi.testclient import TestClient

from app.main import create_app
from app.registry.store import DocumentRegistry
from app.sync.history import SyncHistory


class _StubManager:
    known_source_types: list[str] = []

    def is_running(self, source_type):
        return False


class _SpyScheduler:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _client(tmp_path, scheduler=None) -> tuple[TestClient, DocumentRegistry, SyncHistory]:
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    app = create_app(_StubManager(), history, registry, scheduler=scheduler)
    return TestClient(app)


def test_scheduler_is_started_on_app_startup_and_stopped_on_shutdown(tmp_path):
    scheduler = _SpyScheduler()
    client = _client(tmp_path, scheduler=scheduler)

    assert scheduler.started is False
    with client:
        assert scheduler.started is True
        assert scheduler.stopped is False

    assert scheduler.stopped is True


def test_app_without_a_scheduler_starts_and_stops_cleanly(tmp_path):
    client = _client(tmp_path, scheduler=None)

    with client:
        response = client.get("/health")
        assert response.status_code == 200
