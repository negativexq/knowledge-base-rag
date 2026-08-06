from collections.abc import AsyncIterator

import httpx
from anthropic import AnthropicError, AsyncAnthropic


class ClaudeUnreachableError(Exception):
    """Raised when the Anthropic API cannot be reached or returns an error."""


class ClaudeProvider:
    """ChatProvider backed by the real Anthropic API. There is no
    EmbeddingProvider counterpart — Claude has no embedding endpoint (see
    docs/sprint-01-plan.md's embedding/generation decision).
    """

    def __init__(
        self,
        api_key: str,
        max_tokens: int = 2048,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._client = AsyncAnthropic(api_key=api_key, http_client=http_client)
        self._max_tokens = max_tokens

    async def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]:
        system_text, converted = _split_system_messages(messages)
        try:
            async with self._client.messages.stream(
                model=model,
                max_tokens=self._max_tokens,
                system=system_text,
                messages=converted,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except AnthropicError as exc:
            raise ClaudeUnreachableError(f"Could not reach Claude API: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.close()


def _split_system_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Anthropic's API takes the system prompt as a separate top-level
    parameter, not as a message with role="system" the way Ollama's chat
    API does. app/llm/prompt.py::build_messages() always produces the
    latter shape (one system message, one user message) — this adapts it
    at the provider boundary instead of changing the shared, provider-
    agnostic prompt-building code.
    """
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    return "\n\n".join(system_parts), rest
