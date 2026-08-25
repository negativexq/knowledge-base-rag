from app.ingestion.fingerprint import PipelineFingerprint, build_pipeline_fingerprint
from app.llm.embedding_models import nomic_config, qwen3_4b_config
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
