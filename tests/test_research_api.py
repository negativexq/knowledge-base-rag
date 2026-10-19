from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.research import router
from app.research.feedback import FeedbackRequest, FeedbackStore
from app.security.models import Role, UserContext


def user(tenant="a", id="u", role=Role.USER):
    return UserContext(id, tenant, frozenset({role}))


@pytest.fixture
def client(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")
    app = FastAPI()
    app.include_router(router)
    app.state.research_feedback_store = store
    app.state.chat_rate_limiter = None
    app.state.auth_enabled = True
    app.state.token_authenticator = None
    app.state.chat_deps = None
    app.dependency_overrides[get_current_user] = lambda: user()
    with TestClient(app) as client:
        yield client
    store.close()


def body(**kwargs):
    return {
        "question": "Which protocol?",
        "answer": "TLS. [E1.S1]",
        "claim": "TLS.",
        "reason": "incorrect",
        "support_ids": ["E1.S1"],
        **kwargs,
    }


def identity(client, who):
    client.app.dependency_overrides[get_current_user] = lambda: who


def test_feedback_requires_identity_and_cannot_assign_tenant(client):
    assert client.post("/research/feedback", json=body(tenant_id="b")).status_code == 422
    client.app.dependency_overrides.clear()
    assert client.post("/research/feedback", json=body()).status_code == 401
    assert client.get("/research/feedback/mine").status_code == 401


def test_submit_own_reports_and_role_scoped_review(client):
    response = client.post("/research/feedback", json=body())
    assert response.status_code == 201
    record = response.json()
    assert record["snapshot_origin"] == "user_submitted"
    assert record["tenant_id"] == "a"
    assert len(client.get("/research/feedback/mine").json()) == 1
    assert client.get("/research/feedback").status_code == 403
    assert (
        client.post(
            f"/research/feedback/{record['id']}/review", json={"status": "resolved"}
        ).status_code
        == 403
    )
    identity(client, user(id="another"))
    assert client.get("/research/feedback/mine").json() == []
    identity(client, user(role=Role.OPERATOR))
    assert len(client.get("/research/feedback").json()) == 1
    reviewed = client.post(
        f"/research/feedback/{record['id']}/review",
        json={"status": "triaged", "note": "Reproduce with source version"},
    )
    assert reviewed.json()["status"] == "triaged"
    assert client.get("/research/feedback?status=open").json() == []
    assert len(client.get("/research/feedback?status=triaged").json()) == 1


def test_review_cannot_cross_tenant_or_reveal_record_existence(client):
    record = client.post("/research/feedback", json=body()).json()
    identity(client, user(tenant="b", role=Role.ADMIN))
    assert client.get("/research/feedback").json() == []
    assert (
        client.post(
            f"/research/feedback/{record['id']}/review", json={"status": "resolved"}
        ).status_code
        == 404
    )


def test_feedback_survives_reopening_storage(tmp_path):
    path = tmp_path / "feedback.db"
    store = FeedbackStore(path)
    record = store.add("a", "u", FeedbackRequest(**body()))
    store.close()
    reopened = FeedbackStore(path)
    assert reopened.list("a")[0]["id"] == record["id"]
    assert reopened.list("b") == []
    reopened.close()


def test_document_read_fails_closed_without_reader(client):
    response = client.post(
        "/research/documents/read",
        json={
            "document": {
                "source_type": "filesystem",
                "source_id": "manual",
                "document_version": "v1",
            },
        },
    )
    assert response.status_code == 503


def test_document_read_passes_only_server_identity_and_reports_freshness(client):
    from app.evidence.documents import DocumentResult

    seen = []

    class Reader:
        async def read(self, request):
            return DocumentResult([], [])

    def factory(context, scope):
        seen.append((context.tenant_id, scope))
        return Reader()

    client.app.state.chat_deps = SimpleNamespace(documents_factory=factory)
    client.app.state.registry = SimpleNamespace(get_document=lambda *args: None)
    response = client.post(
        "/research/documents/read",
        json={
            "document": {
                "source_type": "filesystem",
                "source_id": "manual",
                "document_version": "v1",
            },
            "action": "outline",
        },
    )
    assert response.status_code == 200
    assert seen == [("a", None)]
    assert response.json()["indexed_at"] is None
