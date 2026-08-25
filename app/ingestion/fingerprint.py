import hashlib
import json
from dataclasses import asdict, dataclass

from app.llm.embedding_models import EmbeddingModelConfig
from app.registry.store import CURRENT_INDEX_SCHEMA_VERSION


@dataclass(frozen=True)
class PipelineFingerprint:
    """Identifies the exact combination of embedding model + chunking/
    parsing/point-identity scheme a document was indexed under — Sprint 18
    closes a gap the existing point-identity content_hash comparison can't
    see: swapping embedding models (or their instruction/dimension) leaves
    a document's content_hash completely unchanged, so incremental sync
    would otherwise trust stale vectors forever. index_schema_version
    reuses app/registry/store.py::CURRENT_INDEX_SCHEMA_VERSION rather than
    inventing a second, parallel version counter — chunker/parser/point-ID
    changes already bump that constant (Sprint 17/17.1/17.5/17.6), so this
    fingerprint just folds it in alongside the embedding-model dimension.
    """

    embedding_model: str
    embedding_revision: str
    embedding_dimension: int
    query_instruction: str
    document_instruction: str
    index_schema_version: int
    # Sprint 22: defaulted (not required) so every existing direct
    # PipelineFingerprint(...) construction in tests/benchmark scripts
    # keeps working unchanged. A future non-Ollama backend would produce
    # a genuinely different vector space even with an identical model
    # name, so this is a real fingerprint dimension, not decoration.
    embedding_backend: str = "ollama"

    def canonical(self) -> str:
        # sort_keys=True is what makes this deterministic across
        # dict-ordering/process differences — two PipelineFingerprints
        # built with the same field values always produce the same
        # string, and therefore the same digest().
        return json.dumps(asdict(self), sort_keys=True)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()[:16]


def build_pipeline_fingerprint(embedding_config: EmbeddingModelConfig) -> PipelineFingerprint:
    return PipelineFingerprint(
        embedding_model=embedding_config.ollama_model,
        embedding_revision=embedding_config.revision,
        embedding_dimension=embedding_config.dimension,
        query_instruction=embedding_config.query_prefix(),
        document_instruction=embedding_config.document_prefix(),
        index_schema_version=CURRENT_INDEX_SCHEMA_VERSION,
        embedding_backend=embedding_config.backend,
    )
