import pytest

from app.llm.embedding_models import get_embedding_model_config, nomic_config, qwen3_4b_config
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
