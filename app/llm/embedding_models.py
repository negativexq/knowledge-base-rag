from dataclasses import dataclass, replace

from app.shared.config import Settings

# nomic-embed-text's own asymmetric instruction convention (Sprint 0) —
# reused here verbatim, not reinvented, so the "nomic" EmbeddingModelConfig
# produces the EXACT prefix strings app/ingestion/ingest.py and
# app/retrieval/search.py already hardcode.
_NOMIC_QUERY_PREFIX = "search_query: "
_NOMIC_DOCUMENT_PREFIX = "search_document: "


@dataclass(frozen=True)
class EmbeddingModelConfig:
    """Everything that distinguishes one embedding model from another for
    this app's purposes — the "provider" Sprint 18 asked for. Deliberately
    NOT a new EmbeddingProvider subclass: every embedding model this
    project uses is served over the same Ollama HTTP API
    (app/llm/ollama_client.py::OllamaClient.embed(text, model, prefix,
    dimensions) already covers the transport), so the only real per-model
    surface is which model name to call, what prefix/instruction to
    prepend, and (Sprint 19) what output dimension to request — captured
    here as plain config, not a class hierarchy. Core retrieval/ingest
    code takes this object and calls query_prefix()/document_prefix() —
    it never branches on which model is configured.
    """

    key: str
    ollama_model: str
    revision: str
    # The dimension THIS config expects to get back — for a native config
    # this is the model's own real output size; for a truncated config
    # (Sprint 19) it's the requested size, assumed honored until a real
    # probe call (scripts/benchmarks/benchmark_embeddings.py) proves otherwise.
    # Qdrant collection sizing and PipelineFingerprint both use this
    # field, not output_dimension, so a config whose probe turns out
    # unsupported never silently sizes a collection wrong.
    dimension: int
    query_instruction: str
    document_instruction: str
    # None = native (no `dimensions` param sent to Ollama at all — see
    # OllamaClient.embed). An int = Sprint 19's Matryoshka-truncation
    # request, passed straight through to Ollama's own /api/embed
    # `dimensions` parameter — never truncated client-side.
    output_dimension: int | None = None
    # Every config in this app is served over Ollama today — a plain
    # string, not an enum, so a future non-Ollama backend doesn't require
    # restructuring this dataclass, just a new value here.
    backend: str = "ollama"

    def query_prefix(self) -> str:
        return self.query_instruction

    def document_prefix(self) -> str:
        return self.document_instruction

    def label(self) -> str:
        """Human/machine-readable config identity, e.g. "qwen3-4b@native"
        or "qwen3-4b@1024" — used for benchmark collection names and
        report tables so a size AND a dimension are both always visible
        together, never just one.
        """
        dim = "native" if self.output_dimension is None else str(self.output_dimension)
        return f"{self.key}@{dim}"


def nomic_config(settings: Settings) -> EmbeddingModelConfig:
    """The production default — behavior is BYTE-FOR-BYTE what
    app/ingestion/ingest.py::SEARCH_DOCUMENT_PREFIX and
    app/retrieval/search.py::SEARCH_QUERY_PREFIX already hardcode. This
    function exists so the benchmark script can address "nomic" the same
    way it addresses "qwen3-4b", not to change nomic's real code path —
    the production embed_fn/search() call sites still use their own
    hardcoded constants directly, unchanged.
    """
    return EmbeddingModelConfig(
        key="nomic",
        ollama_model=settings.ollama_embed_model,
        revision="latest",
        dimension=768,
        query_instruction=_NOMIC_QUERY_PREFIX,
        document_instruction=_NOMIC_DOCUMENT_PREFIX,
    )


def _qwen3_instruction(settings: Settings) -> str:
    if not settings.qwen3_query_instruction:
        return ""
    return f"Instruct: {settings.qwen3_query_instruction}\nQuery: "


def qwen3_4b_config(settings: Settings) -> EmbeddingModelConfig:
    """Qwen3-Embedding-4B's published usage convention: an asymmetric
    instruction format where only the QUERY side gets an
    "Instruct: {task}\\nQuery: " prefix — the document side gets no
    instruction at all (bare text). This is deliberately NOT nomic's
    "search_query: "/"search_document: " pair carried over blindly; the
    instruction text itself is configurable (settings.qwen3_query_
    instruction) rather than hardcoded, per Sprint 18's rules.
    """
    return EmbeddingModelConfig(
        key="qwen3-4b",
        ollama_model=settings.qwen3_embed_model,
        revision=settings.qwen3_embed_revision,
        dimension=settings.qwen3_embed_dimension,
        query_instruction=_qwen3_instruction(settings),
        document_instruction=settings.qwen3_document_instruction,
    )


def qwen3_0_6b_config(settings: Settings) -> EmbeddingModelConfig:
    """Sprint 19: Qwen3-Embedding-0.6B — same instruction semantics as
    qwen3_4b_config (Qwen3-Embedding's asymmetric convention is a
    property of the Qwen3-Embedding family, not the 4B size specifically)
    so settings.qwen3_query_instruction/qwen3_document_instruction are
    shared across both sizes rather than duplicated per-size settings.
    """
    return EmbeddingModelConfig(
        key="qwen3-0.6b",
        ollama_model=settings.qwen3_0_6b_embed_model,
        revision=settings.qwen3_0_6b_embed_revision,
        dimension=settings.qwen3_0_6b_embed_dimension,
        query_instruction=_qwen3_instruction(settings),
        document_instruction=settings.qwen3_document_instruction,
    )


_REGISTRY = {
    "nomic": nomic_config,
    "qwen3-4b": qwen3_4b_config,
    "qwen3-0.6b": qwen3_0_6b_config,
}


def get_embedding_model_config(
    key: str, settings: Settings, output_dimension: int | None = None
) -> EmbeddingModelConfig:
    """output_dimension=None (default, every Sprint 18 call site) returns
    the model's native config, UNCHANGED from Sprint 18's behavior — the
    Sprint 19 truncation path only activates when a caller explicitly
    passes a dimension.
    """
    try:
        builder = _REGISTRY[key]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model key {key!r} — known keys: {sorted(_REGISTRY)}"
        ) from None
    config = builder(settings)
    if output_dimension is None:
        return config
    return replace(config, dimension=output_dimension, output_dimension=output_dimension)


def active_embedding_config(settings: Settings) -> EmbeddingModelConfig:
    """The ONE config that actually serves production traffic —
    settings.embedding_model_key/embedding_output_dimension (Sprint 22)
    are the single source of truth this resolves against, so every real
    call site (app/wiring.py's embed_fn/search_fn, app/migration's target
    config, the startup schema-mismatch guard) reads the same value
    instead of each hardcoding "nomic" or duplicating model/instruction
    strings of its own.
    """
    return get_embedding_model_config(
        settings.embedding_model_key, settings, output_dimension=settings.embedding_output_dimension
    )


def parse_config_token(token: str, settings: Settings) -> EmbeddingModelConfig:
    """Parses a "model@dimension" CLI token (e.g. "qwen3-4b@1024",
    "qwen3-0.6b@native", "nomic@native") into a resolved
    EmbeddingModelConfig — the format scripts/benchmarks/benchmark_embeddings.py's
    --configs flag uses. "native" (or a bare "model" with no "@") means
    output_dimension=None.
    """
    if "@" in token:
        key, dim_str = token.split("@", 1)
    else:
        key, dim_str = token, "native"
    output_dimension = None if dim_str == "native" else int(dim_str)
    return get_embedding_model_config(key, settings, output_dimension=output_dimension)
