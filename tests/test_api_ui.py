import json

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager

COLLECTION = "test_api_ui"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[1], values=[1.0])


async def _fake_embed(text: str) -> list[float]:
    return [0.01] * EMBEDDING_DIM


def _client(tmp_path, docs_dir, tenant_ids=None, cors_origins=None) -> TestClient:
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
        tenant_ids=tenant_ids or {"filesystem": "tenant-a"},
    )
    return TestClient(
        create_app(
            manager,
            history,
            registry,
            token_authenticator=TokenAuthenticator(DEFAULT_DEV_TOKENS),
            auth_enabled=True,
            tenant_ids=tenant_ids or {"filesystem": "tenant-a"},
            cors_origins=cors_origins,
        )
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_identity_requires_authentication(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/identity")

    assert response.status_code == 401


def test_all_ui_read_endpoints_reject_missing_and_invalid_credentials(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)
    paths = [
        "/ui/identity",
        "/ui/overview",
        "/ui/active-index",
        "/ui/documents",
        "/ui/settings",
        "/ui/evaluations",
        "/ui/traces/not-indexed",
        "/ui/sync-runs",
    ]

    for path in paths:
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=_auth("not-a-real-token")).status_code == 401, path


def test_ui_payloads_do_not_expose_credentials_or_internal_clients(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    responses = [
        client.get("/ui/identity", headers=_auth("token-user-a")),
        client.get("/ui/overview", headers=_auth("token-user-a")),
        client.get("/ui/settings", headers=_auth("token-user-a")),
        client.get("/ui/evaluations", headers=_auth("token-user-a")),
        client.get("/ui/traces/not-indexed", headers=_auth("token-user-a")),
    ]
    body = json.dumps([response.json() for response in responses])
    for forbidden in (
        "token-user-a",
        "AUTH_TOKENS_JSON",
        "claude_api_key",
        "notion_api_key",
        "QdrantClient(",
        "Bearer ",
    ):
        assert forbidden not in body


def test_cors_is_explicit_allow_list_and_non_credentialed(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(
        tmp_path,
        docs_dir,
        cors_origins=["http://localhost:5173"],
    )

    allowed = client.options(
        "/ui/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") != "true"

    disallowed = client.options(
        "/ui/overview",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in disallowed.headers


def test_identity_reflects_the_resolved_user_context(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/identity", headers=_auth("token-operator-a"))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "operator_a"
    assert body["tenant_id"] == "tenant-a"
    assert body["roles"] == ["OPERATOR"]
    assert body["can_sync"] is True
    assert body["is_admin"] is False


def test_identity_never_lets_the_caller_choose_a_tenant():
    """There is no request parameter/body this endpoint even reads for
    tenant_id — the response is entirely derived from the resolved
    token. This test documents that by checking the route signature has
    no such input, rather than a runtime probe."""
    import inspect

    from app.api.ui import identity

    params = inspect.signature(identity).parameters
    assert set(params) == {"user"}


def test_overview_is_tenant_scoped(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nSome content.")
    client = _client(tmp_path, docs_dir)
    client.post("/sync/filesystem", headers=_auth("token-operator-a"))

    tenant_a = client.get("/ui/overview", headers=_auth("token-user-a"))
    tenant_b = client.get("/ui/overview", headers=_auth("token-user-b"))

    assert tenant_a.status_code == 200
    body_a = tenant_a.json()
    assert body_a["document_count"] == 1
    assert body_a["source_count"] == 1

    body_b = tenant_b.json()
    assert body_b["document_count"] == 0
    assert body_b["source_count"] == 0
    assert body_b["sources"] == []


def test_overview_reports_incomplete_chunk_count_honestly(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/overview", headers=_auth("token-user-a"))

    body = response.json()
    assert body["document_count"] == 0
    assert body["chunk_count"] is None  # no documents at all -> nothing to sum, not 0


def test_documents_endpoint_is_tenant_scoped(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent.")
    client = _client(tmp_path, docs_dir)
    client.post("/sync/filesystem", headers=_auth("token-operator-a"))

    tenant_a_docs = client.get("/ui/documents", headers=_auth("token-user-a")).json()
    tenant_b_docs = client.get("/ui/documents", headers=_auth("token-user-b")).json()

    assert len(tenant_a_docs) == 1
    assert tenant_a_docs[0]["tenant_id"] == "tenant-a"
    assert tenant_b_docs == []


def test_settings_never_exposes_a_write_path():
    """No POST/PUT/PATCH route exists under /ui/settings — this is a
    structural check that the read-only claim is actually true, not
    just documented."""
    from app.api.ui import router

    settings_routes = [r for r in router.routes if r.path == "/ui/settings"]
    assert settings_routes
    for route in settings_routes:
        assert route.methods == {"GET"}


def test_settings_reports_real_retrieval_and_auth_configuration(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/settings", headers=_auth("token-user-a"))

    body = response.json()
    assert body["retrieval"]["fusion"] == "RRF"
    assert body["authentication"]["enabled"] is True
    assert body["authentication"]["scheme"] == "bearer"
    assert set(body["authentication"]["roles"]) == {"USER", "OPERATOR", "ADMIN"}
    assert body["retrieval"]["reranker_model"] == "BAAI/bge-reranker-v2-m3"
    assert body["retrieval"]["reranker_enabled"] is True


def test_evaluations_reports_unavailable_rather_than_fabricating(tmp_path, monkeypatch):
    import app.api.ui as ui_module

    monkeypatch.setattr(ui_module, "EVALUATION_ARTIFACT_ROOT", tmp_path / "no-artifacts-here")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/evaluations", headers=_auth("token-user-a"))

    body = response.json()
    assert body["available"] is False
    assert body["baseline"] is None
    assert all(entry["available"] is False for entry in body["timeline"])


def test_evaluations_reads_the_real_sprint21_artifact_when_present(tmp_path, monkeypatch):
    import json

    import app.api.ui as ui_module

    artifact_root = tmp_path / "artifacts"
    sprint21_dir = artifact_root / "embedding-benchmark-sprint21"
    sprint21_dir.mkdir(parents=True)
    (sprint21_dir / "stability.json").write_text(
        json.dumps(
            {
                "run_to_run_distributions": {
                    "qwen3-4b@1024": {
                        "cross_lingual_recall_at_5": {"mean": 0.963, "stddev": 0.0, "n_runs": 10},
                        "cross_lingual_mrr": {"mean": 0.7336, "stddev": 0.0, "n_runs": 10},
                        "ndcg_at_5": {"mean": 0.8362, "stddev": 0.0, "n_runs": 10},
                    }
                }
            }
        )
    )
    monkeypatch.setattr(ui_module, "EVALUATION_ARTIFACT_ROOT", artifact_root)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/evaluations", headers=_auth("token-user-a"))

    body = response.json()
    assert body["available"] is True
    assert body["baseline"]["config"] == "qwen3-4b@1024"
    recall = next(m for m in body["baseline"]["metrics"] if m["key"] == "cross_lingual_recall_at_5")
    assert recall["value"] == 0.963


def test_sync_runs_refuses_a_wrong_tenant_source_type(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get(
        "/ui/sync-runs", params={"source_type": "filesystem"}, headers=_auth("token-user-b")
    )

    assert response.status_code == 403


def test_sync_runs_scoped_to_the_callers_tenant_when_no_source_type_given(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent.")
    client = _client(tmp_path, docs_dir)
    client.post("/sync/filesystem", headers=_auth("token-operator-a"))

    tenant_a_runs = client.get("/ui/sync-runs", headers=_auth("token-user-a")).json()
    tenant_b_runs = client.get("/ui/sync-runs", headers=_auth("token-user-b")).json()

    assert len(tenant_a_runs) == 1
    assert tenant_b_runs == []


def test_trace_detail_reports_unavailable_when_jaeger_unreachable(tmp_path, monkeypatch):
    import app.ui.trace_client as trace_client_module

    def _raise(*args, **kwargs):
        raise ConnectionError("no jaeger here")

    monkeypatch.setattr(trace_client_module, "fetch_trace_spans", _raise)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)

    response = client.get("/ui/traces/deadbeef", headers=_auth("token-user-a"))

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_active_index_degrades_gracefully_without_a_qdrant_client(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    client = _client(tmp_path, docs_dir)  # create_app() called with no qdrant_client here

    response = client.get("/ui/active-index", headers=_auth("token-user-a"))

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["model"]  # still reports the CONFIGURED model, just not live alias state
