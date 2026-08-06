from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.shared.config import Settings


@runtime_checkable
class ChatProvider(Protocol):
    """Shape required by app/llm/generate.py::stream_answer. messages is the
    OpenAI/Ollama-style list app/llm/prompt.py::build_messages() produces
    (a role="system" entry followed by a role="user" entry); the provider
    is responsible for translating that into whatever shape its own API
    needs (see ClaudeProvider, which splits the system message out into
    Anthropic's separate system= parameter).
    """

    def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Shape required by app/retrieval/search.py::search. Embedding is a
    separate choice from chat/generation — Claude has no embedding
    endpoint, so an EmbeddingProvider selection can never follow a
    ChatProvider selection.
    """

    async def embed(self, text: str, model: str, prefix: str = "") -> list[float]: ...


def default_chat_model(settings: Settings) -> str:
    if settings.generation_provider == "claude":
        return settings.claude_model
    return settings.ollama_model


def default_embed_model(settings: Settings) -> str:
    return settings.ollama_embed_model


def get_chat_provider(settings: Settings) -> ChatProvider:
    if settings.generation_provider == "claude":
        from app.llm.claude_provider import ClaudeProvider

        if not settings.claude_api_key:
            raise ValueError(
                "settings.claude_api_key must be set to use generation_provider='claude'"
            )
        return ClaudeProvider(
            api_key=settings.claude_api_key, max_tokens=settings.claude_max_tokens
        )

    from app.llm.ollama_provider import OllamaProvider

    return OllamaProvider(base_url=settings.ollama_base_url)


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    # Only Ollama today (see docs/sprint-01-plan.md's embedding/generation
    # decision) — settings.embedding_provider is a single-value Literal so
    # there is nothing to branch on yet, but callers still go through this
    # factory rather than constructing OllamaProvider directly, so adding a
    # second embedding backend later won't require call-site changes.
    from app.llm.ollama_provider import OllamaProvider

    return OllamaProvider(base_url=settings.ollama_base_url)
