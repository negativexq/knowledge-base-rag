"""Generation tests against the REAL native Ollama (qwen2.5:7b-instruct) —
mocking isn't enough here: we need to prove real token-by-token streaming
latency and real model citation behavior, not just that our code calls an
API correctly.

Skipped automatically if Ollama isn't reachable, so it doesn't break
CI/offline runs.
"""

import json
import socket
import time
import urllib.request

import pytest

from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.llm.ollama_client import OllamaClient
from app.llm.prompt import NOT_FOUND_PHRASE
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import settings


def _ollama_up() -> bool:
    try:
        with socket.create_connection(("localhost", 11434), timeout=0.5):
            return True
    except OSError:
        return False


def _configured_model_available() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=0.5) as response:
            models = json.load(response).get("models", [])
        return any(model.get("name") == settings.ollama_model for model in models)
    except (OSError, ValueError):
        return False


def _chunk(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_type": "pdf",
            "source_id": "handbook",
        },
    )


CONTEXT_CHUNKS = [
    _chunk(2, 0, "Defective products can be returned within 30 days for a full refund."),
]


@pytest.mark.skipif(
    not (_ollama_up() and _configured_model_available()),
    reason="requires native Ollama and the configured generation model",
)
@pytest.mark.asyncio
async def test_answer_streams_as_multiple_incremental_events_not_one_blob():
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        arrival_times = []
        async for event in stream_answer(
            "What is the return policy for a defective product?",
            CONTEXT_CHUNKS,
            ollama,
            model=settings.ollama_model,
            prompt_version=settings.active_prompt_version,
            # This test verifies the explicit low-latency FAST path. The
            # production/default path is STRICT and intentionally buffers.
            validation_mode="fast",
        ):
            if event["type"] == "token":
                arrival_times.append(time.monotonic())

        assert len(arrival_times) > 3  # real streaming produces several separate tokens
        # genuine streaming spreads token arrivals over time; a buffered
        # "fake stream" would deliver everything at ~the same instant
        spread = arrival_times[-1] - arrival_times[0]
        assert spread > 0.05
    finally:
        await ollama.aclose()


@pytest.mark.skipif(
    not (_ollama_up() and _configured_model_available()),
    reason="requires native Ollama and the configured generation model",
)
@pytest.mark.asyncio
async def test_answer_citations_are_grounded_in_real_context():
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        answer_parts = []
        grounding_event = None
        async for event in stream_answer(
            "What is the return policy for a defective product?",
            CONTEXT_CHUNKS,
            ollama,
            model=settings.ollama_model,
            prompt_version=settings.active_prompt_version,
        ):
            if event["type"] == "token":
                answer_parts.append(event["content"])
            elif event["type"] == "grounding":
                grounding_event = event

        answer = "".join(answer_parts)
        assert grounding_event is not None
        assert grounding_event["citations_found"], f"model produced no citations: {answer!r}"
        assert grounding_event["grounded"] is True
        # cross-check with the standalone function too, not just the event
        assert check_grounding(answer, CONTEXT_CHUNKS).grounded is True
    finally:
        await ollama.aclose()


@pytest.mark.skipif(
    not (_ollama_up() and _configured_model_available()),
    reason="requires native Ollama and the configured generation model",
)
@pytest.mark.asyncio
async def test_out_of_context_question_gets_not_found_reply_not_a_hallucination():
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    try:
        answer_parts = []
        async for event in stream_answer(
            "What is the capital of France?",  # unrelated to CONTEXT_CHUNKS
            CONTEXT_CHUNKS,
            ollama,
            model=settings.ollama_model,
            prompt_version=settings.active_prompt_version,
        ):
            if event["type"] == "token":
                answer_parts.append(event["content"])

        answer = "".join(answer_parts)
        assert NOT_FOUND_PHRASE in answer
    finally:
        await ollama.aclose()
