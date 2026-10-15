"""Generation tests against the REAL native Ollama and the production
generation model, on the production answer path (support-ID contract,
app/wiring.py's default stream_fn). Mocking isn't enough here: these prove
the real model follows the structured-output contract, cites the evidence
it was given, and abstains instead of answering from world knowledge.

The answer is buffered and validated before release by design, so there is
no token-by-token streaming assertion here.

Skipped automatically if Ollama or the configured model isn't available.
"""

import pytest

from app.llm.prompt import NOT_FOUND_PHRASE
from app.llm.provider import default_chat_model, get_chat_provider
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import settings
from tests.live_services import ollama_has

pytestmark = pytest.mark.ollama_e2e

requires_generation_model = pytest.mark.skipif(
    not (settings.generation_provider == "ollama" and ollama_has(settings.ollama_model)),
    reason="requires native Ollama and the configured generation model",
)


def _chunk(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9,
        id=f"handbook-{page}-{paragraph}",
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_type": "pdf",
            "source_id": "handbook",
            "authorized": True,
            "model_visible": True,
        },
    )


CONTEXT_CHUNKS = [
    _chunk(2, 0, "Defective products can be returned within 30 days for a full refund."),
]


async def _answer(question: str) -> tuple[str, dict]:
    provider = get_chat_provider(settings)
    try:
        answer_parts: list[str] = []
        validation: dict = {}
        async for event in stream_support_unit_answer(
            question,
            CONTEXT_CHUNKS,
            provider,
            model=default_chat_model(settings),
            prompt_version=settings.active_prompt_version,
            think=settings.ollama_thinking,
            num_ctx=settings.ollama_num_ctx,
            validator_version=settings.critical_validator_version,
        ):
            if event["type"] == "token":
                answer_parts.append(event["content"])
            elif event["type"] == "security_validation":
                validation = event
        return "".join(answer_parts), validation
    finally:
        await provider.aclose()


@requires_generation_model
@pytest.mark.asyncio
async def test_answer_cites_the_evidence_it_was_given():
    answer, validation = await _answer("What is the return policy for a defective product?")

    assert validation["passed"] is True, validation
    assert validation["abstain"] is False, answer
    assert "30" in answer
    assert "[E1." in answer, f"answer carries no support-ID citation: {answer!r}"


@requires_generation_model
@pytest.mark.asyncio
async def test_out_of_context_question_abstains_instead_of_hallucinating():
    answer, validation = await _answer("What is the capital of France?")

    assert validation["abstain"] is True, answer
    assert answer == NOT_FOUND_PHRASE
