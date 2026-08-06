import json

import httpx
import pytest

from app.llm.ollama_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_TIMEOUT_SECONDS,
    OllamaClient,
    OllamaUnreachableError,
)


def _mock_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="http://host.docker.internal:11434")


@pytest.mark.asyncio
async def test_list_models_parses_tags_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen2.5:3b-instruct"}, {"name": "nomic-embed-text"}]},
        )

    client = OllamaClient(http_client=_mock_client(handler))
    models = await client.list_models()

    assert models == ["qwen2.5:3b-instruct", "nomic-embed-text"]


@pytest.mark.asyncio
async def test_list_models_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient(http_client=_mock_client(handler))

    with pytest.raises(OllamaUnreachableError):
        await client.list_models()


@pytest.mark.asyncio
async def test_embed_sends_prefixed_prompt_and_parses_embedding():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    client = OllamaClient(http_client=_mock_client(handler))
    embedding = await client.embed(
        "hello world", model="nomic-embed-text", prefix="search_document: "
    )

    assert embedding == [0.1, 0.2, 0.3]
    assert captured_body["prompt"] == "search_document: hello world"
    assert captured_body["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_embed_sends_keep_alive_so_ollama_does_not_unload_the_model():
    """Ollama's default keep_alive is 5 minutes — a 7B model evicted between
    requests costs ~22s to reload from disk on the next call, vs ~4s when
    already warm.
    """
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={"embedding": [0.1]})

    client = OllamaClient(http_client=_mock_client(handler))
    await client.embed("hello world", model="nomic-embed-text")

    assert captured_body["keep_alive"] == DEFAULT_KEEP_ALIVE


@pytest.mark.asyncio
async def test_embed_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient(http_client=_mock_client(handler))

    with pytest.raises(OllamaUnreachableError):
        await client.embed("hello world", model="nomic-embed-text", prefix="search_document: ")


@pytest.mark.asyncio
async def test_stream_chat_yields_content_tokens_in_order():
    ndjson = "\n".join(
        [
            json.dumps({"message": {"role": "assistant", "content": "Hello"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": " there"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["model"] == "qwen2.5:3b-instruct"
        assert body["keep_alive"] == DEFAULT_KEEP_ALIVE
        return httpx.Response(200, content=ndjson)

    client = OllamaClient(http_client=_mock_client(handler))
    tokens = [
        token
        async for token in client.stream_chat(
            [{"role": "user", "content": "hi"}], model="qwen2.5:3b-instruct"
        )
    ]

    assert tokens == ["Hello", " there"]


@pytest.mark.asyncio
async def test_stream_chat_raises_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = OllamaClient(http_client=_mock_client(handler))

    with pytest.raises(OllamaUnreachableError):
        async for _ in client.stream_chat(
            [{"role": "user", "content": "hi"}], model="qwen2.5:3b-instruct"
        ):
            pass


def test_default_timeout_is_generous_enough_for_slow_local_generation():
    assert DEFAULT_TIMEOUT_SECONDS >= 120.0


def test_client_uses_default_timeout_when_none_given():
    client = OllamaClient(base_url="http://localhost:11434")
    assert client._client.timeout.read == DEFAULT_TIMEOUT_SECONDS


def test_client_accepts_custom_timeout():
    client = OllamaClient(base_url="http://localhost:11434", timeout=5.0)
    assert client._client.timeout.read == 5.0
