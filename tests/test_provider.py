import pytest

from app.llm.claude_provider import ClaudeProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_client import OPENAI_MODEL, OpenAIGeneratorClient
from app.llm.provider import (
    ChatProvider,
    EmbeddingProvider,
    default_chat_model,
    default_embed_model,
    get_chat_provider,
    get_embedding_provider,
)
from app.shared.config import Settings


def test_ollama_provider_satisfies_chat_provider_protocol():
    assert isinstance(OllamaProvider(base_url="http://localhost:11434"), ChatProvider)


def test_ollama_provider_satisfies_embedding_provider_protocol():
    assert isinstance(OllamaProvider(base_url="http://localhost:11434"), EmbeddingProvider)


def test_claude_provider_satisfies_chat_provider_protocol():
    assert isinstance(ClaudeProvider(api_key="x"), ChatProvider)


def test_claude_provider_does_not_satisfy_embedding_provider_protocol():
    # Claude has no embedding endpoint — this is the concrete proof that
    # embedding is a separate abstraction from chat/generation.
    assert not isinstance(ClaudeProvider(api_key="x"), EmbeddingProvider)


def test_default_chat_model_is_ollama_model_for_ollama_provider():
    settings = Settings(generation_provider="ollama", ollama_model="qwen2.5:7b-instruct")

    assert default_chat_model(settings) == "qwen2.5:7b-instruct"


def test_default_chat_model_is_claude_model_for_claude_provider():
    settings = Settings(generation_provider="claude", claude_model="claude-haiku-4-5-20251001")

    assert default_chat_model(settings) == "claude-haiku-4-5-20251001"


def test_default_chat_model_is_openai_model_for_openai_provider():
    settings = Settings(
        generation_provider="openai", openai_api_key="sk-test", openai_model=OPENAI_MODEL
    )

    assert default_chat_model(settings) == OPENAI_MODEL


def test_default_embed_model_follows_the_active_embedding_model_key():
    # Sprint 22: default_embed_model no longer reads ollama_embed_model
    # directly — it resolves through active_embedding_config(), whose
    # single source of truth is embedding_model_key/
    # embedding_output_dimension. Production default is now qwen3-4b
    # (docs/PLANNING.md Sprint 21/22 closing notes).
    settings = Settings(generation_provider="claude")

    assert default_embed_model(settings) == settings.qwen3_embed_model


def test_default_embed_model_switches_when_embedding_model_key_is_nomic():
    settings = Settings(embedding_model_key="nomic", ollama_embed_model="nomic-embed-text")

    assert default_embed_model(settings) == "nomic-embed-text"


def test_get_chat_provider_returns_ollama_provider_by_default():
    settings = Settings()

    provider = get_chat_provider(settings)

    assert isinstance(provider, OllamaProvider)


def test_get_chat_provider_returns_claude_provider_when_configured():
    settings = Settings(generation_provider="claude", claude_api_key="sk-ant-test")

    provider = get_chat_provider(settings)

    assert isinstance(provider, ClaudeProvider)


def test_get_chat_provider_raises_when_claude_selected_without_api_key():
    settings = Settings(generation_provider="claude", claude_api_key=None)

    with pytest.raises(ValueError):
        get_chat_provider(settings)


def test_get_chat_provider_returns_openai_provider_when_configured():
    settings = Settings(generation_provider="openai", openai_api_key="sk-test")

    provider = get_chat_provider(settings)

    assert isinstance(provider, OpenAIGeneratorClient)


def test_get_chat_provider_raises_when_openai_selected_without_api_key():
    settings = Settings(generation_provider="openai", openai_api_key=None)

    with pytest.raises(ValueError):
        get_chat_provider(settings)


def test_get_embedding_provider_returns_ollama_provider():
    settings = Settings()

    provider = get_embedding_provider(settings)

    assert isinstance(provider, OllamaProvider)
