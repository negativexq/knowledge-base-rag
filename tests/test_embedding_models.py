import pytest

from app.llm.embedding_models import (
    get_embedding_model_config,
    nomic_config,
    parse_config_token,
    qwen3_0_6b_config,
    qwen3_4b_config,
)
from app.shared.config import Settings


def test_nomic_config_matches_existing_hardcoded_prefixes():
    """nomic's behavior must stay byte-for-byte identical to the
    hardcoded constants app/ingestion/ingest.py::SEARCH_DOCUMENT_PREFIX
    and app/retrieval/search.py::SEARCH_QUERY_PREFIX already use.
    """
    config = nomic_config(Settings(ollama_embed_model="nomic-embed-text"))

    assert config.ollama_model == "nomic-embed-text"
    assert config.dimension == 768
    assert config.query_prefix() == "search_query: "
    assert config.document_prefix() == "search_document: "


def test_qwen3_config_uses_asymmetric_instruction_format():
    """Qwen3-Embedding's published convention: queries get an
    "Instruct: ...\\nQuery: " prefix, documents get NO instruction at
    all — nomic's prefix pair must not be carried over blindly.
    """
    settings = Settings(
        qwen3_embed_model="qwen3-embedding:4b",
        qwen3_query_instruction="Given a search query, retrieve relevant passages",
        qwen3_document_instruction="",
    )

    config = qwen3_4b_config(settings)

    assert config.ollama_model == "qwen3-embedding:4b"
    assert config.query_prefix() == (
        "Instruct: Given a search query, retrieve relevant passages\nQuery: "
    )
    assert config.document_prefix() == ""


def test_qwen3_config_instruction_is_configurable_not_hardcoded():
    settings = Settings(qwen3_query_instruction="A completely different custom instruction")

    config = qwen3_4b_config(settings)

    assert "A completely different custom instruction" in config.query_prefix()


def test_qwen3_config_dimension_and_revision_are_configurable():
    settings = Settings(qwen3_embed_dimension=1024, qwen3_embed_revision="v1.2")

    config = qwen3_4b_config(settings)

    assert config.dimension == 1024
    assert config.revision == "v1.2"


def test_qwen3_config_empty_instruction_produces_empty_query_prefix():
    settings = Settings(qwen3_query_instruction="")

    config = qwen3_4b_config(settings)

    assert config.query_prefix() == ""


def test_get_embedding_model_config_dispatches_by_key():
    settings = Settings()

    assert get_embedding_model_config("nomic", settings).key == "nomic"
    assert get_embedding_model_config("qwen3-4b", settings).key == "qwen3-4b"


def test_get_embedding_model_config_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown embedding model key"):
        get_embedding_model_config("not-a-real-model", Settings())


def test_qwen3_0_6b_config_uses_the_same_asymmetric_instruction_convention_as_4b():
    """Sprint 19: Qwen3-Embedding's asymmetric instruction format is a
    property of the model FAMILY, not the 4B size specifically — the
    0.6B config must produce the identical instruction shape, sharing
    settings.qwen3_query_instruction rather than needing its own.
    """
    settings = Settings(qwen3_query_instruction="retrieve relevant passages")

    config = qwen3_0_6b_config(settings)

    assert config.ollama_model == "qwen3-embedding:0.6b"
    assert config.query_prefix() == "Instruct: retrieve relevant passages\nQuery: "
    assert config.document_prefix() == ""


def test_qwen3_0_6b_config_native_dimension_is_1024_not_the_4b_dimension():
    config = qwen3_0_6b_config(Settings())

    assert config.dimension == 1024
    assert config.output_dimension is None


def test_get_embedding_model_config_with_output_dimension_overrides_native():
    settings = Settings()

    native = get_embedding_model_config("qwen3-4b", settings)
    truncated = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)

    assert native.dimension == 2560
    assert native.output_dimension is None
    assert truncated.dimension == 1024
    assert truncated.output_dimension == 1024
    # Everything else about the config (model, instructions) is preserved
    # — only dimension/output_dimension change.
    assert truncated.ollama_model == native.ollama_model
    assert truncated.query_instruction == native.query_instruction


def test_config_label_distinguishes_native_from_truncated():
    settings = Settings()

    native = get_embedding_model_config("qwen3-4b", settings)
    truncated = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)

    assert native.label() == "qwen3-4b@native"
    assert truncated.label() == "qwen3-4b@1024"


def test_parse_config_token_native_shorthand():
    settings = Settings()

    from_bare = parse_config_token("qwen3-0.6b", settings)
    from_explicit = parse_config_token("qwen3-0.6b@native", settings)

    assert from_bare.output_dimension is None
    assert from_bare.dimension == from_explicit.dimension
    assert from_bare.label() == from_explicit.label() == "qwen3-0.6b@native"


def test_parse_config_token_with_dimension():
    config = parse_config_token("qwen3-4b@1024", Settings())

    assert config.key == "qwen3-4b"
    assert config.output_dimension == 1024
    assert config.dimension == 1024


def test_parse_config_token_rejects_unknown_model():
    with pytest.raises(ValueError, match="Unknown embedding model key"):
        parse_config_token("not-a-real-model@1024", Settings())
