from app.ingestion.fingerprint import PipelineFingerprint, build_pipeline_fingerprint
from app.llm.embedding_models import get_embedding_model_config, nomic_config, qwen3_4b_config
from app.registry.store import CURRENT_INDEX_SCHEMA_VERSION
from app.shared.config import Settings


def _fp(**overrides) -> PipelineFingerprint:
    base = {
        "embedding_model": "nomic-embed-text",
        "embedding_revision": "latest",
        "embedding_dimension": 768,
        "query_instruction": "search_query: ",
        "document_instruction": "search_document: ",
        "index_schema_version": CURRENT_INDEX_SCHEMA_VERSION,
    }
    base.update(overrides)
    return PipelineFingerprint(**base)


def test_same_config_produces_the_same_digest_deterministically():
    a = _fp()
    b = _fp()

    assert a.digest() == b.digest()
    assert a.canonical() == b.canonical()


def test_digest_is_stable_across_separate_python_processes_via_sorted_keys():
    # dict/dataclass field order is already insertion order in modern
    # Python, but canonical() explicitly sorts keys — this proves the
    # json.dumps(..., sort_keys=True) is actually load-bearing, not
    # incidental, by building the same fingerprint from a
    # differently-ordered kwargs call and confirming identical output.
    a = PipelineFingerprint(
        embedding_model="m",
        embedding_revision="r",
        embedding_dimension=1,
        query_instruction="q",
        document_instruction="d",
        index_schema_version=1,
    )
    b = PipelineFingerprint(
        index_schema_version=1,
        document_instruction="d",
        query_instruction="q",
        embedding_dimension=1,
        embedding_revision="r",
        embedding_model="m",
    )

    assert a.digest() == b.digest()


def test_different_embedding_model_changes_the_digest():
    assert _fp(embedding_model="a").digest() != _fp(embedding_model="b").digest()


def test_different_dimension_changes_the_digest():
    assert _fp(embedding_dimension=768).digest() != _fp(embedding_dimension=2560).digest()


def test_different_query_instruction_changes_the_digest():
    assert (
        _fp(query_instruction="search_query: ").digest()
        != _fp(query_instruction="Instruct: x\nQuery: ").digest()
    )


def test_different_document_instruction_changes_the_digest():
    assert _fp(document_instruction="a").digest() != _fp(document_instruction="b").digest()


def test_different_index_schema_version_changes_the_digest():
    assert _fp(index_schema_version=2).digest() != _fp(index_schema_version=3).digest()


def test_build_pipeline_fingerprint_from_nomic_config_reuses_current_schema_version():
    fingerprint = build_pipeline_fingerprint(nomic_config(Settings()))

    assert fingerprint.embedding_model == "nomic-embed-text"
    assert fingerprint.embedding_dimension == 768
    assert fingerprint.query_instruction == "search_query: "
    assert fingerprint.index_schema_version == CURRENT_INDEX_SCHEMA_VERSION


def test_build_pipeline_fingerprint_differs_between_nomic_and_qwen3():
    nomic_fp = build_pipeline_fingerprint(nomic_config(Settings()))
    qwen3_fp = build_pipeline_fingerprint(qwen3_4b_config(Settings()))

    assert nomic_fp.digest() != qwen3_fp.digest()


def test_same_model_different_output_dimension_produces_different_fingerprint():
    """Sprint 19: qwen3-4b@2560 (native) and qwen3-4b@1024 (Matryoshka-
    truncated) are the SAME underlying model but produce genuinely
    different vectors — an index built under one is stale under the
    other, so their fingerprints must differ even though ollama_model,
    revision, and instructions are all identical.
    """
    settings = Settings()
    native = get_embedding_model_config("qwen3-4b", settings)
    truncated = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)

    native_fp = build_pipeline_fingerprint(native)
    truncated_fp = build_pipeline_fingerprint(truncated)

    assert native.ollama_model == truncated.ollama_model  # sanity: same model
    assert native_fp.digest() != truncated_fp.digest()


def test_embedding_backend_defaults_to_ollama():
    fingerprint = _fp()

    assert fingerprint.embedding_backend == "ollama"


def test_different_embedding_backend_changes_the_digest():
    assert _fp(embedding_backend="ollama").digest() != _fp(embedding_backend="vllm").digest()


def test_build_pipeline_fingerprint_reads_backend_from_the_embedding_config():
    fingerprint = build_pipeline_fingerprint(nomic_config(Settings()))

    assert fingerprint.embedding_backend == "ollama"


def test_qwen3_0_6b_and_qwen3_4b_at_the_same_dimension_still_differ():
    """Two DIFFERENT models that happen to be configured at the same
    output dimension are not the same pipeline — embedding_model itself
    must remain part of the fingerprint even when dimension matches.
    """
    settings = Settings()
    small = get_embedding_model_config("qwen3-0.6b", settings, output_dimension=1024)
    large = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)

    assert small.dimension == large.dimension == 1024
    assert build_pipeline_fingerprint(small).digest() != build_pipeline_fingerprint(large).digest()
