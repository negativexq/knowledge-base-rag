import json
from collections.abc import AsyncIterator

import httpx

# A 10s default was measured to be too short for local generation — local
# models on CPU/limited-RAM hardware can legitimately take well over a
# minute for a single call.
DEFAULT_TIMEOUT_SECONDS = 120.0

# Ollama's own default is 5 minutes. A 7B model evicted between requests
# costs a real, measured ~22s to reload from disk on the next call vs ~4s
# when already warm — worth keeping loaded much longer than the default for
# an app where requests are bursty but not constant.
DEFAULT_KEEP_ALIVE = "30m"


class OllamaUnreachableError(Exception):
    """Raised when the native Ollama instance cannot be reached."""


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        think: bool | None = None,
    ):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self.think = think

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

        data = response.json()
        return [model["name"] for model in data.get("models", [])]

    async def embed(
        self, text: str, model: str, prefix: str = "", dimensions: int | None = None
    ) -> list[float]:
        # Sprint 19: dimensions is None for every existing caller (nomic's
        # production path included) — behavior there is UNCHANGED, still
        # the older singular /api/embeddings endpoint. Only a caller that
        # explicitly wants a non-native output dimension (a Matryoshka-
        # capable model like Qwen3-Embedding) passes dimensions, which
        # switches to /api/embed (plural) — Ollama's own real
        # dimension-truncation mechanism (verified: NOT a naive
        # front-truncate-and-renormalize of the native vector, confirmed
        # by direct comparison — this is the backend doing it, not a
        # local hack). Ollama silently CLAMPS an out-of-range request to
        # the model's native dimension rather than erroring, so a caller
        # that cares whether the requested dimension was honored must
        # check len(result) itself — this method doesn't raise on a
        # mismatch, it just returns whatever the backend actually gave.
        try:
            if dimensions is None:
                response = await self._client.post(
                    "/api/embeddings",
                    json={
                        "model": model,
                        "prompt": f"{prefix}{text}",
                        "keep_alive": DEFAULT_KEEP_ALIVE,
                    },
                )
                response.raise_for_status()
                return response.json()["embedding"]

            response = await self._client.post(
                "/api/embed",
                json={
                    "model": model,
                    "input": f"{prefix}{text}",
                    "dimensions": dimensions,
                    "keep_alive": DEFAULT_KEEP_ALIVE,
                },
            )
            response.raise_for_status()
            return response.json()["embeddings"][0]
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

    async def embed_many(
        self,
        texts: list[str],
        model: str,
        prefix: str = "",
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a batch through Ollama's plural endpoint.

        Sprint 27 uses this for the frozen query-vector phase of the
        chunking benchmark. It is semantically identical to calling
        ``embed`` once per text, but avoids reloading/re-scheduling the same
        local model for every configuration.
        """
        if not texts:
            return []
        try:
            response = await self._client.post(
                "/api/embed",
                json={
                    "model": model,
                    "input": [f"{prefix}{text}" for text in texts],
                    "dimensions": dimensions,
                    "keep_alive": DEFAULT_KEEP_ALIVE,
                },
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

    async def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "keep_alive": DEFAULT_KEEP_ALIVE,
                    **({"think": self.think} if self.think is not None else {}),
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
