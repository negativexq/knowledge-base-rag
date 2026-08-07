from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager
from app.sync.models import STATUS_REJECTED, STATUS_SUCCESS, SyncRunResult

COLLECTION = "test_api_sync"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


async def _fake_embed(text: str) -> list[float]:
    return [0.01] * EMBEDDING_DIM


def _real_client(tmp_path, docs_dir) -> TestClient:
    connector = LocalFilesystemConnector(docs_dir)
    store = QdrantStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    manager = SyncManager(
        connectors={"filesystem": connector},
        store=store,
        registry=registry,
        history=history,
        embed_fn=_fake_embed,
        sparse_encoder=_FakeSparseEncoder(),
    )
    return TestClient(create_app(manager, history, registry))


def test_post_sync_triggers_a_real_ingest_and_returns_the_result(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nReal content via a real HTTP request.")

    client = _real_client(tmp_path, docs_dir)
    response = client.post("/sync/filesystem")

    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "filesystem"
    assert body["status"] == STATUS_SUCCESS
    assert body["stats"]["files_processed"] == 1
    assert body["run_id"] is not None
    assert body["trace_id"] is not None


def test_post_sync_for_unknown_connector_returns_404(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _real_client(tmp_path, docs_dir)

    response = client.post("/sync/notion")

    assert response.status_code == 404


def test_post_sync_when_already_running_returns_409():
    class _StubManager:
        async def trigger_sync(self, source_type, trigger):
            return SyncRunResult(
                source_type=source_type, status=STATUS_REJECTED, run_id=None, stats=None, error=None
            )

    class _StubHistory:
        def list_runs(self, source_type=None, limit=50):
            return []

    class _StubRegistry:
        def list_documents(self, source_type=None):
            return []

    client = TestClient(create_app(_StubManager(), _StubHistory(), _StubRegistry()))
    response = client.post("/sync/filesystem")

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == STATUS_REJECTED


def test_get_sync_history_returns_recorded_runs(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")
    client = _real_client(tmp_path, docs_dir)

    client.post("/sync/filesystem")
    response = client.get("/sync/filesystem/history")

    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["source_type"] == "filesystem"
    assert runs[0]["status"] == STATUS_SUCCESS
    assert runs[0]["files_processed"] == 1
    assert runs[0]["trace_id"] is not None


def test_get_sync_history_for_a_source_with_no_runs_returns_empty_list(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _real_client(tmp_path, docs_dir)

    response = client.get("/sync/filesystem/history")

    assert response.status_code == 200
    assert response.json() == []
