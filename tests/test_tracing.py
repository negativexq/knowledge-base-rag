import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.shared.tracing import get_tracer, setup_tracing


@pytest.fixture(autouse=True)
def _no_network_exporters(monkeypatch):
    """setup_tracing() would otherwise install a real OTLP gRPC exporter
    on the process-global provider, which retries localhost:4317 for
    about a minute at interpreter exit when Jaeger isn't running."""
    import app.shared.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "OTLPSpanExporter", _RecordingExporter)
    monkeypatch.setattr(tracing_module, "OTLPHttpSpanExporter", _RecordingExporter)
    monkeypatch.setattr(tracing_module, "_provider", None)


def _local_tracer_with_in_memory_exporter() -> tuple[trace.Tracer, InMemorySpanExporter]:
    """A tracer from a locally-scoped TracerProvider (not the global one),
    so tests can inspect emitted spans without any network/Jaeger
    dependency and without fighting OTel's rule that the global
    TracerProvider can only be set once per process.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test-module"), exporter


def test_setup_tracing_configures_a_tracer_provider():
    setup_tracing(service_name="test-service")

    provider = trace.get_tracer_provider()
    assert provider is not None


def test_setup_tracing_is_idempotent():
    returned_first = setup_tracing(service_name="test-service")
    provider_first = trace.get_tracer_provider()

    returned_second = setup_tracing(service_name="test-service")
    provider_second = trace.get_tracer_provider()

    assert provider_first is provider_second
    assert returned_first is returned_second


def test_setup_tracing_uses_explicit_endpoint(monkeypatch):
    import app.shared.tracing as tracing_module

    captured = {}

    class FakeExporter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def shutdown(self):
            return None

    monkeypatch.setattr(tracing_module, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(tracing_module, "_provider", None)

    tracing_module.setup_tracing(endpoint="http://custom-jaeger:4317")

    assert captured["endpoint"] == "http://custom-jaeger:4317"
    assert captured["insecure"] is True


def test_get_tracer_produces_spans_with_attributes():
    tracer, exporter = _local_tracer_with_in_memory_exporter()

    with tracer.start_as_current_span("example-span") as span:
        span.set_attribute("example.count", 3)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "example-span"
    assert spans[0].attributes["example.count"] == 3


def test_get_tracer_returns_a_tracer_instance():
    assert get_tracer("test-module") is not None


class _RecordingExporter:
    """Stands in for both OTLP exporters: records constructor kwargs and
    every exported span name, never touches the network."""

    instances: list["_RecordingExporter"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.exported: list[str] = []
        _RecordingExporter.instances.append(self)

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult

        self.exported.extend(s.name for s in spans)
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis=30000):
        return True

    def shutdown(self):
        return None


def _fresh_setup(monkeypatch, **kwargs):
    import app.shared.tracing as tracing_module

    _RecordingExporter.instances = []
    monkeypatch.setattr(tracing_module, "OTLPSpanExporter", _RecordingExporter)
    monkeypatch.setattr(tracing_module, "OTLPHttpSpanExporter", _RecordingExporter)
    monkeypatch.setattr(tracing_module, "_provider", None)
    return tracing_module.setup_tracing(**kwargs)


def test_setup_tracing_without_langfuse_exports_only_to_jaeger(monkeypatch):
    _fresh_setup(monkeypatch, endpoint="http://jaeger:4317")

    assert len(_RecordingExporter.instances) == 1
    assert _RecordingExporter.instances[0].kwargs["endpoint"] == "http://jaeger:4317"


def test_setup_tracing_adds_langfuse_otlp_http_exporter_with_basic_auth(monkeypatch):
    import base64

    from app.shared.tracing import LangfuseExport

    _fresh_setup(
        monkeypatch,
        endpoint="http://jaeger:4317",
        langfuse=LangfuseExport(
            host="http://localhost:3000/", public_key="pk-lf-1", secret_key="sk-lf-1"
        ),
    )

    assert len(_RecordingExporter.instances) == 2
    langfuse = _RecordingExporter.instances[1]
    assert langfuse.kwargs["endpoint"] == "http://localhost:3000/api/public/otel/v1/traces"
    expected = base64.b64encode(b"pk-lf-1:sk-lf-1").decode()
    assert langfuse.kwargs["headers"] == {"Authorization": f"Basic {expected}"}


def test_langfuse_receives_query_path_spans_but_not_sync_or_ingestion(monkeypatch):
    """Scheduled syncs run every few minutes and produce one embed/upsert
    span per batch; those stay in Jaeger only. Langfuse gets the
    request/LLM path it is built for."""
    from app.shared.tracing import LangfuseExport

    provider = _fresh_setup(
        monkeypatch,
        langfuse=LangfuseExport(host="http://lf", public_key="pk", secret_key="sk"),
    )
    for scope, name in (
        ("app.api.chat", "chat_request"),
        ("app.llm.generate", "generate"),
        ("app.sync.manager", "sync_run"),
        ("app.ingestion.ingest", "embed_batch"),
        ("app.migration.embedding_migration", "migrate"),
    ):
        with provider.get_tracer(scope).start_as_current_span(name):
            pass
    provider.force_flush()

    jaeger, langfuse = _RecordingExporter.instances
    assert sorted(jaeger.exported) == [
        "chat_request",
        "embed_batch",
        "generate",
        "migrate",
        "sync_run",
    ]
    assert sorted(langfuse.exported) == ["chat_request", "generate"]


def test_langfuse_export_from_settings_requires_both_keys():
    from app.shared.config import Settings
    from app.shared.tracing import LangfuseExport, langfuse_export_from

    assert langfuse_export_from(Settings(_env_file=None, langfuse_public_key="pk")) is None
    assert langfuse_export_from(
        Settings(
            _env_file=None,
            langfuse_public_key="pk",
            langfuse_secret_key="sk",
            langfuse_host="http://lf",
        )
    ) == LangfuseExport(host="http://lf", public_key="pk", secret_key="sk")
