import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as OTLPHttpSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from app.shared.config import Settings

_provider: TracerProvider | None = None

# Instrumentation scopes (tracer names) whose spans stay in Jaeger only.
# Scheduled syncs, ingestion and embedding migrations emit one span per
# batch every few minutes; Langfuse is for the request/LLM path.
_LANGFUSE_EXCLUDED_SCOPES = ("app.ingestion", "app.sync", "app.migration")


@dataclass(frozen=True)
class LangfuseExport:
    host: str
    public_key: str
    secret_key: str


def langfuse_export_from(settings: "Settings") -> LangfuseExport | None:
    """Langfuse export is opt-in: LANGFUSE_ENABLED and both keys."""
    if (
        not settings.langfuse_enabled
        or not settings.langfuse_public_key
        or not settings.langfuse_secret_key
    ):
        return None
    return LangfuseExport(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


class _ScopeFilteringProcessor(SpanProcessor):
    """Forwards finished spans to `delegate` unless their instrumentation
    scope starts with one of `excluded_prefixes`."""

    def __init__(self, delegate: SpanProcessor, excluded_prefixes: tuple[str, ...]) -> None:
        self._delegate = delegate
        self._excluded_prefixes = excluded_prefixes

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        self._delegate.on_start(span, parent_context=parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
        if scope.startswith(self._excluded_prefixes):
            return
        self._delegate.on_end(span)

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)


def setup_tracing(
    service_name: str = "knowledge-base-rag",
    *,
    endpoint: str = "http://localhost:4317",
    langfuse: LangfuseExport | None = None,
) -> TracerProvider:
    """Configure the global TracerProvider to export spans to Jaeger via
    OTLP gRPC, and additionally to Langfuse via OTLP HTTP when `langfuse`
    is given. Returns the provider so the FastAPI app can be handed the
    same one (FastAPI native telemetry). Idempotent — safe to call
    multiple times; later calls return the first provider unchanged.
    """
    global _provider
    if _provider is not None:
        return _provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    if langfuse is not None:
        credentials = f"{langfuse.public_key}:{langfuse.secret_key}".encode()
        langfuse_exporter = OTLPHttpSpanExporter(
            endpoint=f"{langfuse.host.rstrip('/')}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {base64.b64encode(credentials).decode()}"},
        )
        provider.add_span_processor(
            _ScopeFilteringProcessor(
                BatchSpanProcessor(langfuse_exporter), _LANGFUSE_EXCLUDED_SCOPES
            )
        )
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def mark_llm_generation(span: trace.Span, model: str) -> None:
    """Tag a span as an LLM call using OTel GenAI semantic-convention
    attributes, which Langfuse renders as a generation. Only metadata:
    prompt and completion text never go on spans."""
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("langfuse.observation.type", "generation")
