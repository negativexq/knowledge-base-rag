"""FastAPI native telemetry (0.142+) wired to the application's own
TracerProvider: HTTP spans become the trace root, the existing
"chat_request" span nests under them, and health probes stay out of
traces. Without a provider, create_app() stays a pure factory that emits
no FastAPI telemetry at all.
"""

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.api.chat as chat_module
from app.api.chat import ChatDependencies
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.security.models import RetrievalContext
from app.sync.history import SyncHistory


class _StubManager:
    known_source_types: list[str] = []

    def is_running(self, source_type):
        return False


async def _empty_search(
    question: str, context: RetrievalContext, report: RetrievalReport
) -> list[SearchResult]:
    return []


async def _ok_stream(question: str, chunks: list[SearchResult]):
    yield {"type": "token", "content": "ok"}


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _client(tmp_path, tracer_provider=None) -> TestClient:
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return TestClient(
        create_app(
            _StubManager(),
            history,
            registry,
            chat_deps=ChatDependencies(search_fn=_empty_search, stream_fn=_ok_stream),
            auth_enabled=False,
            tracer_provider=tracer_provider,
        )
    )


def test_chat_request_span_nests_under_the_fastapi_http_span(tmp_path, monkeypatch):
    provider, exporter = _provider()
    monkeypatch.setattr(chat_module, "get_tracer", provider.get_tracer)

    response = _client(tmp_path, tracer_provider=provider).post("/chat", json={"question": "q"})

    assert response.status_code == 200
    spans = {s.name: s for s in exporter.get_finished_spans()}
    http_span = spans["POST /chat"]
    chat_span = spans["chat_request"]
    assert http_span.parent is None
    assert chat_span.context.trace_id == http_span.context.trace_id
    # FastAPI may put its own operation span (endpoint execution) between
    # the HTTP span and chat_request; walk up to the HTTP span.
    by_id = {s.context.span_id: s for s in exporter.get_finished_spans()}
    ancestor = chat_span
    while ancestor.parent is not None:
        ancestor = by_id[ancestor.parent.span_id]
    assert ancestor is http_span


def test_health_probes_are_excluded_from_traces(tmp_path):
    provider, exporter = _provider()
    client = _client(tmp_path, tracer_provider=provider)

    assert client.get("/health").status_code == 200

    assert exporter.get_finished_spans() == ()


def test_incoming_traceparent_is_honored(tmp_path):
    provider, exporter = _provider()
    client = _client(tmp_path, tracer_provider=provider)
    upstream_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"

    client.get(
        "/sources",
        headers={"traceparent": f"00-{upstream_trace_id}-00f067aa0ba902b7-01"},
    )

    http_spans = [s for s in exporter.get_finished_spans() if s.name.startswith("GET ")]
    assert http_spans
    assert format(http_spans[0].context.trace_id, "032x") == upstream_trace_id


def test_without_a_provider_create_app_emits_no_fastapi_telemetry(tmp_path):
    app = _client(tmp_path).app

    assert app._telemetry["tracing"] is False
    assert app._telemetry["metrics"] is False
    assert app._telemetry["logs"] is False
    assert app._telemetry["auto_configure"] is False


def test_with_a_provider_auto_configure_stays_off(tmp_path, monkeypatch):
    """FastAPI's env-driven exporter setup would add a second OTLP
    exporter next to ours and duplicate every span."""
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    provider, _ = _provider()

    app = _client(tmp_path, tracer_provider=provider).app

    assert app._telemetry["auto_configure"] is False
    assert app._telemetry["tracer_provider"] is provider
