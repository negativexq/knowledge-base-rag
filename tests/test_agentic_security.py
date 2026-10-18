import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import fitz
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ui import router
from app.llm.agentic import EvidenceLedger
from app.llm.visual_answer import PdfPages
from app.research.traces import TraceStore
from app.retrieval.hybrid_search import SearchResult
from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
from app.security.models import RetrievalContext
from app.shared.config import Settings
from app.shared.trace_client import SpanSummary, fetch_trace_spans


def test_evidence_ledger_rechecks_server_tenant_and_document_scope():
    ledger = EvidenceLedger(
        lambda _: 1, 1000, context=RetrievalContext("a"), source_ids=frozenset({"manual"})
    )
    for tenant, source in [("b", "manual"), ("a", "other"), (None, "manual")]:
        assert (
            ledger.add(
                [
                    SearchResult(
                        id="c",
                        score=1,
                        payload={
                            "tenant_id": tenant,
                            "source_id": source,
                            "text": "unauthorized",
                        },
                    )
                ]
            )
            == []
        )
    assert (
        len(
            ledger.add(
                [
                    SearchResult(
                        id="a",
                        score=1,
                        payload={
                            "tenant_id": "a",
                            "source_id": "manual",
                            "text": "authorized",
                        },
                    )
                ]
            )
        )
        == 1
    )


def test_pdf_snapshot_rejects_changed_versions_and_pins_authorized_bytes(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Authorized source")
        pdf.save(path)
    original = path.read_bytes()
    renderer = PdfPages(str(tmp_path))
    assert renderer.snapshot("manual_pdf", "incorrect-version") is None
    snapshot = renderer.snapshot("manual_pdf", hashlib.sha256(original).hexdigest())
    assert snapshot is not None
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Different tenant document")
        path.unlink()
        pdf.save(path)
    assert renderer.snapshot("manual_pdf", hashlib.sha256(original).hexdigest()) is None
    assert snapshot.content == original
    assert snapshot("manual_pdf", 1) is not None
    assert snapshot("other_pdf", 1) is None


def test_trace_parser_never_exports_content_secrets_or_exception_events():
    payload = {
        "data": [
            {
                "spans": [
                    {
                        "spanID": "r",
                        "operationName": "chat_request",
                        "startTime": 100,
                        "duration": 50,
                        "tags": [
                            {"key": "security.tenant_id", "value": "tenant-a"},
                            {"key": "research.user_id", "value": "user_a"},
                            {"key": "gen_ai.usage.input_tokens", "value": 12},
                            {"key": "api_key", "value": "SECRET"},
                            {"key": "gen_ai.input.messages", "value": "PRIVATE QUESTION"},
                            {"key": "exception.message", "value": "PRIVATE ERROR"},
                        ],
                        "logs": [{"fields": [{"key": "event", "value": "PRIVATE EVENT"}]}],
                    }
                ]
            }
        ]
    }
    client = httpx.Client(
        base_url="http://jaeger.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    spans = fetch_trace_spans("a" * 32, client=client)
    assert spans[0].attributes == {"gen_ai.usage.input_tokens": 12}
    assert "PRIVATE" not in repr(spans) and "SECRET" not in repr(spans)
    client.close()


def test_trace_details_and_index_require_ownership_and_reviewer_role(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    store = TraceStore(tmp_path / "traces.db")
    id = "a" * 32
    store.save(
        {
            "trace_id": id,
            "tenant_id": "tenant-a",
            "user_id": "user_a",
            "started_at": datetime.now(UTC).isoformat(),
            "outcome": "answered",
        }
    )
    app.state.request_trace_store = store
    app.state.settings = Settings(_env_file=None)
    app.state.auth_enabled = True
    app.state.token_authenticator = TokenAuthenticator(DEFAULT_DEV_TOKENS)
    app.state.tenant_ids = {}
    app.state.sync_history = SimpleNamespace(list_runs=lambda **kwargs: [])
    monkeypatch.setattr(
        "app.shared.trace_client.fetch_trace_spans",
        lambda *a, **k: [
            SpanSummary("chat_request", 5, 1, span_id="r", tenant_id="tenant-a", user_id="user_a"),
            SpanSummary(
                "llm.request",
                2,
                2,
                span_id="c",
                parent_span_id="r",
                attributes={"gen_ai.usage.input_tokens": 12},
            ),
        ],
    )
    with TestClient(app) as client:
        assert client.get("/ui/chat-traces").status_code == 401
        assert client.get(f"/ui/traces/{id}").status_code == 401
        for token in ["token-user-b", "token-operator-b"]:
            auth = {"Authorization": f"Bearer {token}"}
            assert client.get("/ui/chat-traces", headers=auth).json() == []
            hidden = client.get(f"/ui/traces/{id}", headers=auth).json()
            assert not hidden["available"] and hidden["spans"] == []
        auth = {"Authorization": "Bearer token-user-a"}
        detail = client.get(f"/ui/traces/{id}", headers=auth).json()
        assert detail["available"] and detail["spans"][1]["parent_span_id"] == "r"
        assert detail["can_open_external"] is False
        assert len(client.get("/ui/chat-traces", headers=auth).json()) == 1
        # Even a same-tenant ordinary user cannot read another user's trace.
        store.save(
            {
                "trace_id": id,
                "tenant_id": "tenant-a",
                "user_id": "another",
                "started_at": datetime.now(UTC).isoformat(),
                "outcome": "answered",
            }
        )
        monkeypatch.setattr(
            "app.shared.trace_client.fetch_trace_spans",
            lambda *a, **k: [
                SpanSummary("chat_request", 5, 1, tenant_id="tenant-a", user_id="another")
            ],
        )
        assert not client.get(f"/ui/traces/{id}", headers=auth).json()["available"]
        auth = {"Authorization": "Bearer token-operator-a"}
        assert client.get(f"/ui/traces/{id}", headers=auth).json()["available"]
    store.close()


def test_agent_does_not_inherit_sdk_wide_content_capture(monkeypatch):
    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel

    from app.llm.agentic import build_agent

    monkeypatch.setattr(Agent, "_instrument_default", True)
    agent = build_agent(FunctionModel(lambda *_: None))
    assert agent.instrument is False


def test_pdf_snapshot_rejects_oversized_raster_before_allocation(tmp_path):
    path = tmp_path / "oversized.pdf"
    with fitz.open() as pdf:
        pdf.new_page(width=14400, height=14400)
        pdf.save(path)
    renderer = PdfPages(str(tmp_path))
    snapshot = renderer.snapshot("oversized_pdf", hashlib.sha256(path.read_bytes()).hexdigest())
    assert snapshot is not None
    assert snapshot("oversized_pdf", 1) is None
