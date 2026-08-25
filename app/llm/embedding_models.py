from dataclasses import dataclass

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
    (app/llm/ollama_client.py::OllamaClient.embed(text, model, prefix)
    already covers the transport), so the only real per-model surface is
    which model name to call and what prefix/instruction to prepend —
    captured here as plain config, not a class hierarchy. Core retrieval/
    ingest code takes this object and calls query_prefix()/
    document_prefix() — it never branches on which model is configured.
    """

    key: str
    ollama_model: str
    revision: str
    dimension: int
    query_instruction: str
    document_instruction: str

    def query_prefix(self) -> str:
        return self.query_instruction

    def document_prefix(self) -> str:
        return self.document_instruction


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


def qwen3_4b_config(settings: Settings) -> EmbeddingModelConfig:
    """Qwen3-Embedding-4B's published usage convention: an asymmetric
    instruction format where only the QUERY side gets an
    "Instruct: {task}\\nQuery: " prefix — the document side gets no
    instruction at all (bare text). This is deliberately NOT nomic's
    "search_query: "/"search_document: " pair carried over blindly; the
    instruction text itself is configurable (settings.qwen3_query_
    instruction) rather than hardcoded, per Sprint 18's rules.
    """
    query_instruction = (
        f"Instruct: {settings.qwen3_query_instruction}\nQuery: "
        if settings.qwen3_query_instruction
        else ""
    )
    return EmbeddingModelConfig(
        key="qwen3-4b",
        ollama_model=settings.qwen3_embed_model,
        revision=settings.qwen3_embed_revision,
        dimension=settings.qwen3_embed_dimension,
        query_instruction=query_instruction,
        document_instruction=settings.qwen3_document_instruction,
    )


_REGISTRY = {
    "nomic": nomic_config,
    "qwen3-4b": qwen3_4b_config,
}


def get_embedding_model_config(key: str, settings: Settings) -> EmbeddingModelConfig:
    try:
        builder = _REGISTRY[key]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model key {key!r} — known keys: {sorted(_REGISTRY)}"
        ) from None
    return builder(settings)
