import json

import httpx
import pytest

from app.llm.claude_provider import ClaudeProvider, ClaudeUnreachableError


def _sse_response(deltas: list[str]) -> bytes:
    """Build a real Anthropic streaming SSE body (message_start ->
    content_block_start -> content_block_delta* -> content_block_stop ->
    message_delta -> message_stop) so tests exercise the SDK's real parsing
    code, not a hand-waved mock of it.
    """
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": "claude-test",
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
    ]
    for delta in deltas:
        events.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": delta},
                },
            )
        )
    events.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
    events.append(
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": len(deltas)},
            },
        )
    )
    events.append(("message_stop", {"type": "message_stop"}))

    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    return body.encode()


def _mock_provider(handler, **kwargs) -> ClaudeProvider:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ClaudeProvider(api_key="test-key", http_client=http_client, **kwargs)


@pytest.mark.asyncio
async def test_stream_chat_yields_text_deltas_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_sse_response(["Hello", " there"]),
            headers={"content-type": "text/event-stream"},
        )

    provider = _mock_provider(handler)
    tokens = [
        token
        async for token in provider.stream_chat(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
            model="claude-test",
        )
    ]

    assert tokens == ["Hello", " there"]


@pytest.mark.asyncio
async def test_stream_chat_splits_system_role_message_into_system_param():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(
            200, content=_sse_response(["ok"]), headers={"content-type": "text/event-stream"}
        )

    provider = _mock_provider(handler)
    async for _ in provider.stream_chat(
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Context:\n...\n\nQuestion: hi"},
        ],
        model="claude-test",
    ):
        pass

    assert captured_body["system"] == "You are a helpful assistant."
    assert captured_body["messages"] == [
        {"role": "user", "content": "Context:\n...\n\nQuestion: hi"}
    ]
    assert not any(m["role"] == "system" for m in captured_body["messages"])


@pytest.mark.asyncio
async def test_stream_chat_sends_configured_model_and_max_tokens():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(
            200, content=_sse_response(["ok"]), headers={"content-type": "text/event-stream"}
        )

    provider = _mock_provider(handler, max_tokens=512)
    async for _ in provider.stream_chat(
        [{"role": "user", "content": "hi"}], model="claude-haiku-4-5-20251001"
    ):
        pass

    assert captured_body["model"] == "claude-haiku-4-5-20251001"
    assert captured_body["max_tokens"] == 512


@pytest.mark.asyncio
async def test_stream_chat_raises_claude_unreachable_error_when_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _mock_provider(handler)

    with pytest.raises(ClaudeUnreachableError):
        messages = [{"role": "user", "content": "hi"}]
        async for _ in provider.stream_chat(messages, model="claude-test"):
            pass


@pytest.mark.asyncio
async def test_stream_chat_raises_claude_unreachable_error_on_api_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
        )

    provider = _mock_provider(handler)

    with pytest.raises(ClaudeUnreachableError):
        messages = [{"role": "user", "content": "hi"}]
        async for _ in provider.stream_chat(messages, model="claude-test"):
            pass
