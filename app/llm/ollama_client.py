import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

# Local generation can legitimately take well over a minute.  Keep the
# transport limits explicit and separate from the overall request deadline so
# a stalled response cannot leave a benchmark process blocked forever.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_OVERALL_TIMEOUT_SECONDS = 240.0

# Ollama's own default is 5 minutes. A 7B model evicted between requests
# costs a real, measured ~22s to reload from disk on the next call vs ~4s
# when already warm — worth keeping loaded much longer than the default for
# an app where requests are bursty but not constant.
DEFAULT_KEEP_ALIVE = "30m"


class OllamaUnreachableError(Exception):
    """Raised when the native Ollama instance cannot be reached."""


class OllamaRequestTimeout(OllamaUnreachableError):
    """A bounded Ollama request exceeded its connect/read/overall deadline."""

    def __init__(self, timeout_type: str, elapsed_ms: float):
        self.timeout_type = timeout_type
        self.elapsed_ms = elapsed_ms
        super().__init__(f"Ollama {timeout_type.lower()} timeout after {elapsed_ms:.1f}ms")


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        overall_timeout: float = DEFAULT_OVERALL_TIMEOUT_SECONDS,
        think: bool | None = None,
        num_ctx: int | None = None,
    ):
        self._owns_client = http_client is None
        self.overall_timeout = overall_timeout
        transport_timeout = httpx.Timeout(
            connect=connect_timeout,
            read=timeout,
            write=timeout,
            pool=connect_timeout,
        )
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url, timeout=transport_timeout
        )
        self.think = think
        self.num_ctx = num_ctx
        self.last_call_observation: dict[str, Any] | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _hash(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _begin_observation(self, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
        started = asyncio.get_running_loop().time()
        messages = body.get("messages", [])
        observation = {
            "request_id": uuid4().hex,
            "model": body.get("model"),
            "seed": (body.get("options") or {}).get("seed"),
            "request_hash": self._hash(body),
            "prompt_hash": self._hash([item for item in messages if item.get("role") == "system"]),
            "context_hash": self._hash([item for item in messages if item.get("role") == "user"]),
            "schema_hash": self._hash(body.get("format")),
            "request_started_at": self._now(),
            "connection_established_at": None,
            "headers_received_at": None,
            "first_body_byte_at": None,
            "completed_at": None,
            "elapsed_ms": None,
            "streaming": bool(body.get("stream")),
            "status_code": None,
            "response_bytes": None,
            "status": "STARTED",
            "timeout_type": None,
            "attempt": 1,
        }
        self.last_call_observation = observation
        return observation, started

    def _finish_observation(
        self, observation: dict[str, Any], started: float, *, status: str
    ) -> None:
        observation["completed_at"] = self._now()
        observation["elapsed_ms"] = round((asyncio.get_running_loop().time() - started) * 1000, 3)
        observation["status"] = status

    async def _chat_response(self, body: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        observation, started = self._begin_observation(body)
        response_bytes = bytearray()
        try:
            async with asyncio.timeout(self.overall_timeout):
                async with self._client.stream("POST", "/api/chat", json=body) as response:
                    observation["headers_received_at"] = self._now()
                    observation["connection_established_at"] = observation["headers_received_at"]
                    observation["status_code"] = response.status_code
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk and observation["first_body_byte_at"] is None:
                            observation["first_body_byte_at"] = self._now()
                        response_bytes.extend(chunk)
            observation["response_bytes"] = len(response_bytes)
            self._finish_observation(observation, started, status="COMPLETE")
            return json.loads(bytes(response_bytes)), bytes(response_bytes)
        except TimeoutError as exc:
            observation["response_bytes"] = len(response_bytes)
            observation["timeout_type"] = "OVERALL"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("OVERALL", observation["elapsed_ms"]) from exc
        except httpx.ConnectTimeout as exc:
            observation["timeout_type"] = "CONNECT"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("CONNECT", observation["elapsed_ms"]) from exc
        except httpx.ReadTimeout as exc:
            observation["response_bytes"] = len(response_bytes)
            observation["timeout_type"] = "READ"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("READ", observation["elapsed_ms"]) from exc
        except httpx.HTTPError as exc:
            self._finish_observation(observation, started, status="HTTP_ERROR")
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

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
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": DEFAULT_KEEP_ALIVE,
            **({"think": self.think} if self.think is not None else {}),
            **({"options": {"num_ctx": self.num_ctx}} if self.num_ctx is not None else {}),
        }
        observation, started = self._begin_observation(body)
        response_bytes = bytearray()
        try:
            async with asyncio.timeout(self.overall_timeout):
                async with self._client.stream("POST", "/api/chat", json=body) as response:
                    observation["headers_received_at"] = self._now()
                    observation["connection_established_at"] = observation["headers_received_at"]
                    observation["status_code"] = response.status_code
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        raw_line = line.encode()
                        response_bytes.extend(raw_line)
                        if observation["first_body_byte_at"] is None:
                            observation["first_body_byte_at"] = self._now()
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
            observation["response_bytes"] = len(response_bytes)
            self._finish_observation(observation, started, status="COMPLETE")
        except TimeoutError as exc:
            observation["response_bytes"] = len(response_bytes)
            observation["timeout_type"] = "OVERALL"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("OVERALL", observation["elapsed_ms"]) from exc
        except httpx.ConnectTimeout as exc:
            observation["timeout_type"] = "CONNECT"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("CONNECT", observation["elapsed_ms"]) from exc
        except httpx.ReadTimeout as exc:
            observation["response_bytes"] = len(response_bytes)
            observation["timeout_type"] = "READ"
            self._finish_observation(observation, started, status="TIMEOUT")
            raise OllamaRequestTimeout("READ", observation["elapsed_ms"]) from exc
        except httpx.HTTPError as exc:
            self._finish_observation(observation, started, status="HTTP_ERROR")
            raise OllamaUnreachableError(f"Could not reach Ollama: {exc}") from exc

    async def chat_json(
        self,
        messages: list[dict],
        model: str,
        *,
        think: bool = False,
        temperature: float = 0.0,
        schema: dict | None = None,
        num_ctx: int | None = None,
        seed: int | None = None,
        num_predict: int | None = None,
    ) -> str:
        """Run a non-streaming structured JSON call, separate from generation."""
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": schema or "json",
            "options": {
                "temperature": temperature,
                **({"num_ctx": num_ctx} if num_ctx is not None else {}),
                **({"seed": seed} if seed is not None else {}),
                **({"num_predict": num_predict} if num_predict is not None else {}),
            },
            "think": think,
            "keep_alive": DEFAULT_KEEP_ALIVE,
        }
        data, _ = await self._chat_response(body)
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            self.last_call_observation["status"] = "INVALID_RESPONSE"
            raise ValueError("Ollama JSON chat response has no message content") from exc
        if not isinstance(content, str):
            self.last_call_observation["status"] = "INVALID_RESPONSE"
            raise ValueError("Ollama JSON chat returned non-string message content")
        return content

    async def chat_text(
        self,
        messages: list[dict],
        model: str,
        *,
        think: bool = False,
        temperature: float = 0.0,
        num_ctx: int | None = None,
        seed: int | None = None,
    ) -> str:
        """Run a plain non-streaming chat call for provider diagnostics."""
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                **({"num_ctx": num_ctx} if num_ctx is not None else {}),
                **({"seed": seed} if seed is not None else {}),
            },
            "think": think,
            "keep_alive": DEFAULT_KEEP_ALIVE,
        }
        data, _ = await self._chat_response(body)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            self.last_call_observation["status"] = "INVALID_RESPONSE"
            raise ValueError("Ollama chat response has no message content") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
