from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.api.chat import ChatDependencies, _sse_event_stream
from app.evidence.documents import DocumentReader
from app.llm.agentic import EvidenceLedger
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.filters import build_acl_filter, filter_authorized_candidates
from app.retrieval.hybrid_search import SearchResult
from app.security.auth import TokenAuthenticator, parse_auth_tokens
from app.security.document_permissions import (
    DocumentPermissionStore,
    DocumentPolicy,
    PolicyConflictError,
)
from app.security.models import RetrievalContext, Role, UserContext
from app.sync.history import SyncHistory


def user(id="alice", tenant="a", groups=(), role=Role.USER):
    return UserContext(id, tenant, frozenset({role}), frozenset(groups))


def result(source="secret", tenant="a", source_type="filesystem"):
    return SearchResult(
        id="1",
        score=1,
        payload={
            "tenant_id": tenant,
            "source_type": source_type,
            "source_id": source,
            "document_version": "v1",
            "text": "Private payload",
            "page_number": 1,
        },
    )


def policy(**kwargs):
    return DocumentPolicy(
        source_type="filesystem", source_id="secret", access="restricted", **kwargs
    )


@pytest.mark.parametrize("role", list(Role))
def test_explicit_user_and_group_grants_without_role_bypass(role):
    store = DocumentPermissionStore(":memory:")
    store.set("a", "admin", policy(user_ids=["alice"], group_ids=["engineering"]))
    for who, expected in [
        (user(role=role), True),
        (user("bob", groups=["engineering"], role=role), True),
        (user("bob", role=role), False),
        (user(tenant="b", role=role), False),
    ]:
        context = RetrievalContext.for_user(who, store.for_user(who))
        assert bool(filter_authorized_candidates([result()], context)) == expected
    assert filter_authorized_candidates([result()], RetrievalContext.system())
    store.close()


def test_default_deny_persistence_revision_and_live_revocation(tmp_path):
    path = tmp_path / "acl.db"
    store = DocumentPermissionStore(path)
    context = RetrievalContext.for_user(user(), store.for_user(user()))
    assert filter_authorized_candidates([result()], context) == []
    saved = store.set("a", "admin", policy(user_ids=["alice"]))
    assert filter_authorized_candidates([result()], context)
    with pytest.raises(PolicyConflictError):
        store.set("a", "admin", policy(user_ids=["bob"]))
    store.set("a", "admin", policy(revision=saved.revision))
    assert filter_authorized_candidates([result()], context) == []
    store.close()
    reopened = DocumentPermissionStore(path)
    assert reopened.get("a", "filesystem", "secret").revision == 2
    assert not reopened.rules(user()).allows("filesystem", "secret")
    reopened.close()


@pytest.mark.parametrize("default_access", ["restricted", "tenant"])
def test_qdrant_filter_matches_post_filter_and_ledger(default_access):
    store = DocumentPermissionStore(":memory:", default_access=default_access)
    store.set("a", "admin", policy(user_ids=["alice"]))
    store.set(
        "a",
        "admin",
        DocumentPolicy(source_type="filesystem", source_id="denied", access="restricted"),
    )
    context = RetrievalContext.for_user(user(), store.for_user(user()))
    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("c", vectors_config=qm.VectorParams(size=2, distance=qm.Distance.DOT))
    candidates = [
        result(),
        result("denied"),
        result("unconfigured"),
        result(tenant="b"),
        result(source_type="notion"),
    ]
    qdrant.upsert(
        "c",
        points=[
            qm.PointStruct(id=i, vector=[1.0, 0.0], payload=r.payload)
            for i, r in enumerate(candidates)
        ],
    )
    points, _ = qdrant.scroll("c", scroll_filter=build_acl_filter(context), limit=20)
    expected = filter_authorized_candidates(candidates, context)
    assert sorted(p.payload["source_id"] for p in points) == sorted(
        r.payload["source_id"] for r in expected
    )
    ledger = EvidenceLedger(lambda _: 1, 1000, context=context)
    ledger.add(candidates)
    assert len(ledger.blocks) == len(expected)
    store.set("a", "admin", policy(revision=1))
    assert len(ledger.units) == len(expected) - 1
    qdrant.close()
    store.close()


def test_default_deny_matches_no_qdrant_points():
    store = DocumentPermissionStore(":memory:")
    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("c", vectors_config=qm.VectorParams(size=2, distance=qm.Distance.DOT))
    qdrant.upsert("c", points=[qm.PointStruct(id=1, vector=[1.0, 0.0], payload=result().payload)])
    context = RetrievalContext.for_user(user(), store.for_user(user()))
    assert qdrant.scroll("c", scroll_filter=build_acl_filter(context))[0] == []
    qdrant.close()
    store.close()


def test_group_memberships_come_from_validated_server_token_configuration():
    parsed = parse_auth_tokens(
        '{"t":{"user_id":"alice","tenant_id":"a","roles":["USER"],"group_ids":["engineering"]}}'
    )
    assert parsed["t"].group_ids == frozenset({"engineering"})
    with pytest.raises(ValueError):
        parse_auth_tokens(
            '{"t":{"user_id":"alice","tenant_id":"a","roles":["USER"],"group_ids":"engineering"}}'
        )


@pytest.fixture
def permission_client(tmp_path):
    store = DocumentPermissionStore(tmp_path / "acl.db")
    registry = DocumentRegistry(tmp_path / "registry.db")
    registry.upsert_document("a", "filesystem", "secret", "v1", chunk_count=1)
    registry.upsert_document("b", "filesystem", "other", "v1")
    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("c", vectors_config=qm.VectorParams(size=2, distance=qm.Distance.DOT))
    qdrant.upsert("c", points=[qm.PointStruct(id=1, vector=[1.0, 0.0], payload=result().payload)])

    async def search(*args, **kwargs):
        return [result()]

    async def stream(q, chunks, **kwargs):
        yield {"type": "token", "content": "Private payload" if chunks else "No evidence"}

    manager = SimpleNamespace(known_source_types=["filesystem"], is_running=lambda _: False)
    app = create_app(
        manager,
        SyncHistory(tmp_path / "registry.db"),
        registry,
        chat_deps=ChatDependencies(
            search_fn=search,
            stream_fn=stream,
            documents_factory=lambda context, sources: DocumentReader(
                qdrant, "c", context, sources
            ),
        ),
        document_permission_store=store,
        cors_origins=["http://localhost:5173"],
        tenant_ids={"filesystem": "a"},
        token_authenticator=TokenAuthenticator(
            {
                "alice": user(),
                "admin": user("admin", role=Role.ADMIN),
                "other-admin": user("other", tenant="b", role=Role.ADMIN),
            }
        ),
    )
    with TestClient(app) as client:
        yield client
    qdrant.close()
    store.close()


def test_api_grant_revoke_metadata_isolation_admin_boundary_and_conflicts(permission_client):
    client = permission_client
    alice, admin = {"Authorization": "Bearer alice"}, {"Authorization": "Bearer admin"}
    body = {
        "document": {"source_type": "filesystem", "source_id": "secret", "document_version": "v1"}
    }
    assert client.get("/research/document-permissions").status_code == 401
    assert client.get("/research/document-permissions", headers=alice).status_code == 403
    assert (
        client.put(
            "/research/document-permissions", headers=alice, json=policy().model_dump()
        ).status_code
        == 403
    )
    assert client.get("/ui/documents", headers=alice).json() == []
    assert client.get("/sources", headers=alice).json()[0]["document_count"] == 0
    assert client.post("/research/documents/read", headers=alice, json=body).status_code == 404
    assert (
        "Private payload"
        not in client.post(
            "/chat", headers=alice, json={"question": "Read secret", "group_ids": ["engineering"]}
        ).text
    )
    assert client.post("/research/documents/read", headers=admin, json=body).status_code == 404
    assert len(client.get("/research/document-permissions", headers=admin).json()) == 1
    saved = client.put(
        "/research/document-permissions",
        headers=admin,
        json=policy(user_ids=["alice"]).model_dump(),
    )
    assert saved.status_code == 200
    assert (
        client.put(
            "/research/document-permissions", headers=admin, json=policy().model_dump()
        ).status_code
        == 409
    )
    assert len(client.get("/ui/documents", headers=alice).json()) == 1
    assert client.post("/research/documents/read", headers=alice, json=body).status_code == 200
    denied = client.put(
        "/research/document-permissions", headers=admin, json=policy(revision=1).model_dump()
    )
    assert denied.status_code == 200
    assert client.post("/research/documents/read", headers=alice, json=body).status_code == 404
    assert (
        client.put(
            "/research/document-permissions",
            headers={"Authorization": "Bearer other-admin"},
            json=policy().model_dump(),
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/research/document-permissions",
            headers=admin,
            json={**policy(revision=2).model_dump(), "tenant_id": "b"},
        ).status_code
        == 422
    )


async def test_revocation_during_agent_work_stops_token_release():
    store = DocumentPermissionStore(":memory:")
    store.set("a", "admin", policy(user_ids=["alice"]))
    context = RetrievalContext.for_user(user(), store.for_user(user()))

    async def search(*_):
        return [result()]

    async def stream(*args, **kwargs):
        store.set("a", "admin", policy(revision=1))
        yield {"type": "token", "content": "Private payload"}

    events = [
        e
        async for e in _sse_event_stream(
            "Read?", ChatDependencies(search_fn=search, stream_fn=stream), context
        )
    ]
    assert not any('"token": "Private payload"' in e for e in events)
    assert any("DOCUMENT_ACCESS_REVOKED" in e for e in events)
    store.close()


def test_production_factory_requires_permission_storage(tmp_path):
    from app.shared.config import Settings

    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_tokens_json='{"real":{"user_id":"alice","tenant_id":"a","roles":["USER"]}}',
    )
    registry = DocumentRegistry(tmp_path / "registry.db")
    with pytest.raises(ValueError, match="document permission store"):
        create_app(
            SimpleNamespace(), SyncHistory(tmp_path / "registry.db"), registry, settings=settings
        )


async def test_filename_slug_collision_cannot_merge_document_permission_identities(tmp_path):
    from app.connectors.filesystem import LocalFilesystemConnector

    (tmp_path / "Guide?.md").write_text("One document")
    (tmp_path / "Guide!.md").write_text("A different document")
    with pytest.raises(ValueError, match="identifiers collide"):
        await LocalFilesystemConnector(tmp_path).list_documents()


async def test_newly_cited_legacy_metadata_cannot_bypass_document_permissions():
    store = DocumentPermissionStore(":memory:")
    store.set(
        "a", "admin", DocumentPolicy(source_type="filesystem", source_id="public", access="tenant")
    )
    context = RetrievalContext.for_user(user(), store.for_user(user()))

    async def search(*_):
        return [result("public")]

    async def stream(*args, **kwargs):
        yield {
            "type": "metadata",
            "support_units": [
                {"source_type": "filesystem", "source_id": "secret", "text": "HIDDEN_METADATA"}
            ],
        }
        yield {"type": "token", "content": "HIDDEN_ANSWER"}

    events = [
        e
        async for e in _sse_event_stream(
            "Read?", ChatDependencies(search_fn=search, stream_fn=stream), context
        )
    ]
    assert "HIDDEN" not in "".join(events)
    assert "DOCUMENT_ACCESS_REVOKED" in "".join(events)
    store.close()


def test_permission_writes_support_authenticated_browser_preflight(permission_client):
    response = permission_client.options(
        "/research/document-permissions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
