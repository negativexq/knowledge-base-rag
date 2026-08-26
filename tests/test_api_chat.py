from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.api.chat import ChatDependencies, _sse_event_stream
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.security.models import RetrievalContext
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager


class _StubConnector:
    source_type = "filesystem"

    async def list_documents(self):
        return []

    async def fetch_content(self, document):
        raise NotImplementedError

    async def get_content_hash(self, document):
        raise NotImplementedError


class _FakeSparseEncoder:
    def embed_document(self, text):
        return None


def _client_with_chat_deps(chat_deps: ChatDependencies, tmp_path) -> TestClient:
    manager = SyncManager(
        connectors={"filesystem": _StubConnector()},
        store=None,
        registry=DocumentRegistry(tmp_path / "registry.db"),
        history=SyncHistory(tmp_path / "registry.db"),
        embed_fn=None,
        sparse_encoder=_FakeSparseEncoder(),
    )
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return TestClient(
        create_app(manager, history, registry, chat_deps=chat_deps, auth_enabled=False)
    )


async def _fake_search(
    question: str, context: RetrievalContext, report: RetrievalReport
) -> list[SearchResult]:
    return [
        SearchResult(
            score=0.9,
            payload={
                "source_type": "filesystem",
                "source_id": "handbook",
                "page_number": 1,
                "paragraph_index": 0,
                "text": "Refunds within 30 days.",
            },
        )
    ]


async def _fake_stream(question: str, chunks: list[SearchResult]):
    yield {"type": "metadata", "prompt_version": "v1", "trace_id": "abc123"}
    yield {"type": "token", "content": "30 "}
    yield {"type": "token", "content": "days [s.filesystem:handbook/1/0]."}
    yield {
        "type": "grounding",
        "grounded": True,
        "citations_found": [("filesystem", "handbook", "1/0")],
        "ungrounded_citations": [],
    }


def test_chat_endpoint_streams_sse_events_with_tokens_metadata_and_grounding(tmp_path):
    deps = ChatDependencies(search_fn=_fake_search, stream_fn=_fake_stream)
    client = _client_with_chat_deps(deps, tmp_path)

    response = client.post("/chat", json={"question": "How long is the refund window?"})

    assert response.status_code == 200
    body = response.text
    assert "event: metadata" in body
    assert '"trace_id": "abc123"' in body
    assert '"token": "30 "' in body
    assert "event: grounding" in body
    assert '"grounded": true' in body


async def test_sse_event_stream_calls_search_fn_with_the_question_and_passes_results_to_stream_fn():
    received = {}

    async def search_fn(
        question: str, context: RetrievalContext, report: RetrievalReport
    ) -> list[SearchResult]:
        received["question"] = question
        return [SearchResult(score=1.0, payload={"text": "x"})]

    async def stream_fn(question: str, chunks: list[SearchResult]):
        received["chunks"] = chunks
        yield {"type": "token", "content": "ok"}

    deps = ChatDependencies(search_fn=search_fn, stream_fn=stream_fn)
    context = RetrievalContext(tenant_id="default")
    events = [line async for line in _sse_event_stream("What is X?", deps, context)]

    assert received["question"] == "What is X?"
    assert len(received["chunks"]) == 1
    # Sprint 24: the stream also carries sources/retrieval/done events
    # now — this asserts the token event is still emitted as before,
    # not that it's the ONLY event.
    assert 'data: {"token": "ok"}\n\n' in events
    assert any(e.startswith("event: sources\n") for e in events)
    assert any(e.startswith("event: retrieval\n") for e in events)
    assert any(e.startswith("event: security\n") for e in events)
    assert any(e.startswith("event: done\n") for e in events)


def test_chat_requires_authentication(tmp_path):
    deps = ChatDependencies(search_fn=_fake_search, stream_fn=_fake_stream)
    manager = SyncManager(
        connectors={"filesystem": _StubConnector()},
        store=None,
        registry=DocumentRegistry(tmp_path / "registry.db"),
        history=SyncHistory(tmp_path / "registry.db"),
        embed_fn=None,
        sparse_encoder=_FakeSparseEncoder(),
    )
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    client = TestClient(
        create_app(manager, history, registry, chat_deps=deps, auth_enabled=True)
    )

    response = client.post("/chat", json={"question": "hi"})

    assert response.status_code == 401


def test_chat_passes_the_authenticated_users_own_tenant_as_retrieval_context(tmp_path):
    """The concrete proof that /chat never lets tenant_id come from the
    request body — it's derived exclusively from the resolved
    UserContext and handed to search_fn as a RetrievalContext.
    """
    from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator

    received_context = {}

    async def _capturing_search(
        question: str, context: RetrievalContext, report: RetrievalReport
    ):
        received_context["context"] = context
        return []

    deps = ChatDependencies(search_fn=_capturing_search, stream_fn=_fake_stream)
    manager = SyncManager(
        connectors={"filesystem": _StubConnector()},
        store=None,
        registry=DocumentRegistry(tmp_path / "registry.db"),
        history=SyncHistory(tmp_path / "registry.db"),
        embed_fn=None,
        sparse_encoder=_FakeSparseEncoder(),
    )
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    client = TestClient(
        create_app(
            manager, history, registry, chat_deps=deps,
            token_authenticator=TokenAuthenticator(DEFAULT_DEV_TOKENS), auth_enabled=True,
        )
    )

    client.post(
        "/chat", json={"question": "hi"}, headers={"Authorization": "Bearer token-user-a"}
    )

    assert received_context["context"] == RetrievalContext(tenant_id="tenant-a")


async def test_sse_event_stream_opens_a_chat_request_root_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    async def search_fn(
        question: str, context: RetrievalContext, report: RetrievalReport
    ) -> list[SearchResult]:
        return []

    async def stream_fn(question: str, chunks: list[SearchResult]):
        yield {"type": "token", "content": "ok"}

    deps = ChatDependencies(search_fn=search_fn, stream_fn=stream_fn)
    context = RetrievalContext(tenant_id="default")
    _ = [line async for line in _sse_event_stream("q", deps, context, tracer=tracer)]

    span_names = {s.name for s in exporter.get_finished_spans()}
    assert "chat_request" in span_names
