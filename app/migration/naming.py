"""Sprint 22: centralized physical Qdrant collection naming for production
embedding migrations — deliberately separate from
scripts/benchmark_embeddings.py's own `kb_benchmark_*` naming (a distinct,
never-serves-traffic namespace), so a benchmark run and a real migration
can never collide on a collection name even if run against the same
Qdrant instance.

Physical collection names are deterministic and human-readable
(`kb_<model>_<dimension>_<fingerprint-prefix>`), combining the model
label (readable at a glance) with the pipeline fingerprint's own digest
prefix (guarantees uniqueness — a different instruction string or index
schema version produces a different physical collection even if the
model/dimension label is unchanged).
"""

from app.ingestion.fingerprint import PipelineFingerprint
from app.llm.embedding_models import EmbeddingModelConfig

_FINGERPRINT_PREFIX_LEN = 8


def sanitize_label(label: str) -> str:
    """"qwen3-4b@1024" -> "qwen3_4b_1024" — matches
    scripts/benchmark_embeddings.py's own _sanitize_label rule (`.` ->
    `_`, not dropped, so "qwen3-0.6b" reads as "qwen3_0_6b", never
    "qwen306b"), kept here as an independent copy rather than importing
    from the benchmark script — that script is a standalone CLI entry
    point, not a library this app should depend on at runtime.
    """
    return label.replace("@", "_").replace(".", "_").replace("-", "_")


def collection_name_for(config: EmbeddingModelConfig, fingerprint: PipelineFingerprint) -> str:
    return f"kb_{sanitize_label(config.label())}_{fingerprint.digest()[:_FINGERPRINT_PREFIX_LEN]}"
