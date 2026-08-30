"""Real Ollama vs real Claude API comparison — the Sprint 1 DoD proof: the
SAME question, answered by BOTH providers via a config-driven ChatProvider
swap, with both real answers captured for comparison. No mocking on either
side.

Each half skips independently and automatically:
- the Ollama half needs a native Ollama on :11434 (same as Sprint 0's e2e
  tests)
- the Claude half needs ANTHROPIC_API_KEY set (in the environment or .env)

If ANTHROPIC_API_KEY is not set, this whole test is skipped and Sprint 1's
closing note says so explicitly rather than claiming a real comparison
happened.
"""

import socket

import pytest

from app.llm.claude_provider import ClaudeProvider
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.llm.ollama_provider import OllamaProvider
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import settings

pytestmark = pytest.mark.ollama_e2e


def _ollama_up() -> bool:
    try:
        with socket.create_connection(("localhost", 11434), timeout=0.5):
            return True
    except OSError:
        return False


_services_ready = _ollama_up() and bool(settings.claude_api_key)

CONTEXT_CHUNKS = [
    SearchResult(
        score=0.9,
        payload={
            "page_number": 2,
            "paragraph_index": 0,
            "text": "Defective products can be returned within 30 days for a full refund.",
            "source_type": "pdf",
            "source_id": "handbook",
        },
    )
]

QUESTION = "What is the return policy for a defective product?"


async def _answer_with(provider, model: str) -> tuple[str, dict]:
    answer_parts = []
    grounding_event = None
    async for event in stream_answer(
        QUESTION, CONTEXT_CHUNKS, provider, model=model, prompt_version="v1"
    ):
        if event["type"] == "token":
            answer_parts.append(event["content"])
        elif event["type"] == "grounding":
            grounding_event = event
    return "".join(answer_parts), grounding_event


@pytest.mark.skipif(
    not _services_ready,
    reason="requires native Ollama on :11434 AND ANTHROPIC_API_KEY set",
)
@pytest.mark.asyncio
async def test_same_question_answered_by_both_real_providers():
    ollama = OllamaProvider(base_url=settings.ollama_base_url)
    claude = ClaudeProvider(api_key=settings.claude_api_key, max_tokens=settings.claude_max_tokens)
    try:
        ollama_answer, ollama_grounding = await _answer_with(ollama, settings.ollama_model)
        claude_answer, claude_grounding = await _answer_with(claude, settings.claude_model)

        assert ollama_answer.strip(), "Ollama produced no answer"
        assert claude_answer.strip(), "Claude produced no answer"

        # Both must follow the same citation format and both must be
        # grounded — the format doesn't depend on which model produced it.
        assert ollama_grounding["citations_found"], (
            f"Ollama produced no citations: {ollama_answer!r}"
        )
        assert claude_grounding["citations_found"], (
            f"Claude produced no citations: {claude_answer!r}"
        )
        assert ollama_grounding["grounded"] is True
        assert claude_grounding["grounded"] is True

        # Cross-check with the standalone function too, not just the events.
        assert check_grounding(ollama_answer, CONTEXT_CHUNKS).grounded is True
        assert check_grounding(claude_answer, CONTEXT_CHUNKS).grounded is True

        print(f"\n--- Ollama ({settings.ollama_model}) ---\n{ollama_answer}")
        print(f"\n--- Claude ({settings.claude_model}) ---\n{claude_answer}")
    finally:
        await ollama.aclose()
        await claude.aclose()
