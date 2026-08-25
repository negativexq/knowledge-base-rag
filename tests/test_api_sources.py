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
        tenant_ids={"filesystem": "local-dev"},
    )
    # Sprint 23: auth_enabled=False (the explicit local-dev bypass — see
    # app/api/deps.py) makes every request an ADMIN in tenant "local-dev";
    # tenant_ids maps "filesystem" to that same tenant so /sources'
    # ownership filter doesn't hide it.
    return TestClient(
        create_app(
            manager, history, registry, auth_enabled=False,
            tenant_ids={"filesystem": "local-dev"},
        )
    )


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


def test_sources_requires_authentication(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    connector = LocalFilesystemConnector(docs_dir)
    store = QdrantStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    manager = SyncManager(
        connectors={"filesystem": connector}, store=store, registry=registry, history=history,
        embed_fn=_fake_embed, sparse_encoder=_FakeSparseEncoder(),
        tenant_ids={"filesystem": "tenant-a"},
    )
    client = TestClient(
        create_app(
            manager, history, registry, tenant_ids={"filesystem": "tenant-a"}, auth_enabled=True,
        )
    )

    response = client.get("/sources")

    assert response.status_code == 401


def test_sources_only_shows_source_types_owned_by_the_callers_own_tenant(tmp_path):
    """Section 11: a tenant-b user must never learn that a "filesystem"
    source_type exists at all when it's owned by tenant-a — not even as
    a zero-document row (that would still leak its existence/name).
    """
    from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nTenant A only content.")
    connector = LocalFilesystemConnector(docs_dir)
    store = QdrantStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    manager = SyncManager(
        connectors={"filesystem": connector}, store=store, registry=registry, history=history,
        embed_fn=_fake_embed, sparse_encoder=_FakeSparseEncoder(),
        tenant_ids={"filesystem": "tenant-a"},
    )
    client = TestClient(
        create_app(
            manager, history, registry,
            token_authenticator=TokenAuthenticator(DEFAULT_DEV_TOKENS),
            tenant_ids={"filesystem": "tenant-a"}, auth_enabled=True,
        )
    )
    client.post("/sync/filesystem", headers={"Authorization": "Bearer token-operator-a"})

    tenant_a_response = client.get("/sources", headers={"Authorization": "Bearer token-user-a"})
    tenant_b_response = client.get("/sources", headers={"Authorization": "Bearer token-user-b"})

    assert tenant_a_response.json() == [
        {"source_type": "filesystem", "document_count": 1, "is_running": False}
    ]
    assert tenant_b_response.json() == []  # "filesystem" doesn't even appear


def test_get_sources_lists_multiple_connectors():
    class _StubRegistry:
        def list_documents(self, tenant_id=None, source_type=None):
            return [1, 2, 3] if source_type == "filesystem" else []

    class _StubManager:
        known_source_types = ["filesystem", "notion"]

        def is_running(self, source_type):
            return source_type == "notion"

    class _StubHistory:
        def list_runs(self, source_type=None, limit=50):
            return []

    client = TestClient(
        create_app(
            _StubManager(), _StubHistory(), _StubRegistry(), auth_enabled=False,
            tenant_ids={"filesystem": "local-dev", "notion": "local-dev"},
        )
    )
    response = client.get("/sources")

    assert response.status_code == 200
    assert response.json() == [
        {"source_type": "filesystem", "document_count": 3, "is_running": False},
        {"source_type": "notion", "document_count": 0, "is_running": True},
    ]
