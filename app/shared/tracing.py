from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def setup_tracing(
    service_name: str = "knowledge-base-rag", *, endpoint: str = "http://localhost:4317"
) -> None:
    """Configure the global TracerProvider to export spans to Jaeger via
    OTLP gRPC. Idempotent — safe to call multiple times.
    """
    global _configured
    if _configured:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
