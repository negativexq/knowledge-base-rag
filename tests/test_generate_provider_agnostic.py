"""Proves app/llm/generate.py::stream_answer and grounding/citation checking
work identically no matter which ChatProvider produced the answer — the
whole point of Sprint 1's abstraction. Both a fake Ollama-shaped provider
and a fake Claude-shaped provider (the real ClaudeProvider class, wired to
a mocked transport) are exercised through the exact same stream_answer call,
and both must produce the same grounding/citation result for the same
answer text.
"""

import json

import httpx
import pytest

from app.llm.claude_provider import ClaudeProvider
from app.llm.generate import stream_answer
from app.retrieval.hybrid_search import SearchResult

ANSWER_SENTENCE = "Refunds take 30 days"
TAG = "[s.pdf:handbook/2/0]"


def _chunk() -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": 2,
            "paragraph_index": 0,
            "text": "Refunds are processed within 30 days.",
            "source_type": "pdf",
            "source_id": "handbook",
        },
    )


class _FakeOllamaProvider:
    async def stream_chat(self, messages, model):
        for token in [ANSWER_SENTENCE, " ", TAG, "."]:
            yield token


def _claude_provider_yielding(tokens: list[str]) -> ClaudeProvider:
    message = {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "content": [],
        "model": "claude-test",
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
    block_start = {"type": "text", "text": ""}
    events = [
        ("message_start", {"type": "message_start", "message": message}),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": block_start},
        ),
    ]
    for t in tokens:
        delta = {"type": "text_delta", "text": t}
        events.append(
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta})
        )
    events.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
    events.append(
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": len(tokens)},
            },
        )
    )
    events.append(("message_stop", {"type": "message_stop"}))
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClaudeProvider(api_key="test-key", http_client=http_client)


@pytest.mark.asyncio
async def test_ollama_and_claude_providers_produce_identical_grounding_result():
    chunks = [_chunk()]

    ollama_events = [
        e
        async for e in stream_answer(
            "How long?", chunks, _FakeOllamaProvider(), model="fake-ollama", prompt_version="v1"
        )
    ]
    claude_provider = _claude_provider_yielding([ANSWER_SENTENCE, " ", TAG, "."])
    claude_events = [
        e
        async for e in stream_answer(
            "How long?", chunks, claude_provider, model="claude-test", prompt_version="v1"
        )
    ]

    ollama_tokens = "".join(e["content"] for e in ollama_events if e["type"] == "token")
    claude_tokens = "".join(e["content"] for e in claude_events if e["type"] == "token")
    assert ollama_tokens == claude_tokens  # same answer text from both

    ollama_grounding = next(e for e in ollama_events if e["type"] == "grounding")
    claude_grounding = next(e for e in claude_events if e["type"] == "grounding")

    assert ollama_grounding["grounded"] is True
    assert claude_grounding["grounded"] is True
    assert ollama_grounding["citations_found"] == claude_grounding["citations_found"]
    assert ollama_grounding["citations_found"] == [("pdf", "handbook", "2/0")]


@pytest.mark.asyncio
async def test_ollama_and_claude_providers_both_flag_the_same_fabricated_citation():
    chunks = [_chunk()]
    fabricated_tag = "[s.pdf:handbook/99/0]"

    class _FakeOllamaFabricated:
        async def stream_chat(self, messages, model):
            for token in [ANSWER_SENTENCE, " ", fabricated_tag, "."]:
                yield token

    claude_provider = _claude_provider_yielding([ANSWER_SENTENCE, " ", fabricated_tag, "."])

    ollama_events = [
        e
        async for e in stream_answer(
            "How long?", chunks, _FakeOllamaFabricated(), model="fake-ollama", prompt_version="v1"
        )
    ]
    claude_events = [
        e
        async for e in stream_answer(
            "How long?", chunks, claude_provider, model="claude-test", prompt_version="v1"
        )
    ]

    ollama_grounding = next(e for e in ollama_events if e["type"] == "grounding")
    claude_grounding = next(e for e in claude_events if e["type"] == "grounding")

    assert ollama_grounding["grounded"] is False
    assert claude_grounding["grounded"] is False
    assert ollama_grounding["ungrounded_citations"] == claude_grounding["ungrounded_citations"]
    assert ollama_grounding["ungrounded_citations"] == [("pdf", "handbook", "99/0")]
