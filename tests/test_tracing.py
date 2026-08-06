from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.shared.tracing import get_tracer, setup_tracing


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
    setup_tracing(service_name="test-service")
    provider_first = trace.get_tracer_provider()

    setup_tracing(service_name="test-service")
    provider_second = trace.get_tracer_provider()

    assert provider_first is provider_second


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
