from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager

COLLECTION = "test_api_sources"


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


def test_get_sources_lists_known_connectors_with_zero_documents_before_any_sync(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _real_client(tmp_path, docs_dir)

    response = client.get("/sources")

    assert response.status_code == 200
    body = response.json()
    assert body == [{"source_type": "filesystem", "document_count": 0, "is_running": False}]


def test_get_sources_reflects_document_count_after_a_real_sync(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nSome content.")
    (docs_dir / "b.md").write_text("# B\n\nMore content.")
    client = _real_client(tmp_path, docs_dir)

    client.post("/sync/filesystem")
    response = client.get("/sources")

    body = response.json()
    assert body == [{"source_type": "filesystem", "document_count": 2, "is_running": False}]


def test_get_sources_lists_multiple_connectors():
    class _StubRegistry:
        def list_documents(self, source_type=None):
            return [1, 2, 3] if source_type == "filesystem" else []

    class _StubManager:
        known_source_types = ["filesystem", "notion"]

        def is_running(self, source_type):
            return source_type == "notion"

    class _StubHistory:
        def list_runs(self, source_type=None, limit=50):
            return []

    client = TestClient(create_app(_StubManager(), _StubHistory(), _StubRegistry()))
    response = client.get("/sources")

    assert response.status_code == 200
    assert response.json() == [
        {"source_type": "filesystem", "document_count": 3, "is_running": False},
        {"source_type": "notion", "document_count": 0, "is_running": True},
    ]
