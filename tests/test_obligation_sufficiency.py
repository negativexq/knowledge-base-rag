import json

import pytest

from app.evaluation.semantic_answerability import (
    OBLIGATION_SUFFICIENCY_SYSTEM_PROMPT,
    ObligationSufficiencyEvaluation,
    OllamaSemanticEvaluator,
    SufficiencyObligation,
    _messages,
    aggregate_obligation_decision,
    authorized_context,
)
from app.retrieval.hybrid_search import SearchResult


def _chunk(chunk_id: str = "c1", text: str = "The policy explicitly states the rule."):
    return SearchResult(
        score=0.91,
        id=chunk_id,
        payload={"chunk_id": chunk_id, "source_id": "policy", "text": text},
    )


class _FakeOllama:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


def _evaluation(*obligations, decision="SUFFICIENT"):
    return json.dumps(
        {
            "obligations": list(obligations),
            "decision": decision,
            "missing_information": [],
            "rationale": "Explicit support.",
        }
    )


def _obligation(number: int, status: str, supporting_chunk_ids=None):
    return {
        "id": f"o{number}",
        "description": f"requested fact {number}",
        "status": status,
        "supporting_chunk_ids": supporting_chunk_ids or [],
    }


def test_obligation_models_represent_single_and_multi_part_requests():
    single = SufficiencyObligation(
        id="o1", description="return window", status="SUPPORTED", supporting_chunk_ids=["c1"]
    )
    multi = ObligationSufficiencyEvaluation(
        obligations=[
            single,
            SufficiencyObligation(
                id="o2", description="retry policy", status="SUPPORTED", supporting_chunk_ids=["c1"]
            ),
        ],
        decision="SUFFICIENT",
    )

    assert len(multi.obligations) == 2
    assert aggregate_obligation_decision(multi) == ("SUFFICIENT", 0)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["SUPPORTED", "SUPPORTED"], "SUFFICIENT"),
        (["SUPPORTED", "UNSUPPORTED"], "INSUFFICIENT"),
    ],
)
def test_all_obligations_must_be_supported(statuses, expected):
    obligations = [
        SufficiencyObligation(
            id=f"o{index}",
            description=f"requested fact {index}",
            status=status,
            supporting_chunk_ids=["c1"] if status == "SUPPORTED" else [],
        )
        for index, status in enumerate(statuses, start=1)
    ]
    evaluation = ObligationSufficiencyEvaluation(obligations=obligations, decision=expected)

    assert aggregate_obligation_decision(evaluation) == (expected, 0)


def test_contradictory_model_decision_is_normalized_from_obligations():
    evaluation = ObligationSufficiencyEvaluation(
        obligations=[
            SufficiencyObligation(
                id="o1", description="fact", status="SUPPORTED", supporting_chunk_ids=["c1"]
            )
        ],
        decision="INSUFFICIENT",
    )

    assert aggregate_obligation_decision(evaluation) == ("SUFFICIENT", 1)


def test_unsupported_obligation_cannot_cite_support():
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        SufficiencyObligation(
            id="o1", description="fact", status="UNSUPPORTED", supporting_chunk_ids=["c1"]
        )


@pytest.mark.asyncio
async def test_obligation_limit_is_bounded():
    obligations = [_obligation(i, "SUPPORTED", ["c1"]) for i in range(1, 8)]
    client = _FakeOllama(_evaluation(*obligations))

    # The parser rejects pathological decomposition rather than silently
    # accepting invented obligations.
    result = await OllamaSemanticEvaluator(
        client, "qwen3.5:4b", retries=0
    ).evaluate_obligation_sufficiency("What are the rules?", [_chunk()])
    assert result.parse_error is True
    assert result.shadow_action == "ABSTAIN"
    assert result.invalid_obligation_count == 1


@pytest.mark.asyncio
async def test_complete_and_partial_obligations_produce_deterministic_actions():
    complete_client = _FakeOllama(
        _evaluation(
            _obligation(1, "SUPPORTED", ["c1"]),
            _obligation(2, "SUPPORTED", ["c1"]),
        )
    )
    complete = await OllamaSemanticEvaluator(
        complete_client, "qwen3.5:4b"
    ).evaluate_obligation_sufficiency("What are the two requested rules?", [_chunk()])
    assert complete.decision == "SUFFICIENT"
    assert complete.shadow_action == "ANSWER"

    partial_client = _FakeOllama(
        _evaluation(
            _obligation(1, "SUPPORTED", ["c1"]),
            _obligation(2, "UNSUPPORTED"),
            decision="INSUFFICIENT",
        )
    )
    partial = await OllamaSemanticEvaluator(
        partial_client, "qwen3.5:4b"
    ).evaluate_obligation_sufficiency("What are the two requested rules?", [_chunk()])
    assert partial.decision == "INSUFFICIENT"
    assert partial.shadow_action == "ABSTAIN"


@pytest.mark.asyncio
async def test_unknown_obligation_support_id_fails_safe():
    client = _FakeOllama(
        _evaluation(_obligation(1, "SUPPORTED", ["not-authorized"]))
    )
    result = await OllamaSemanticEvaluator(client, "qwen3.5:4b").evaluate_obligation_sufficiency(
        "What is the rule?", [_chunk()]
    )

    assert result.parse_error is True
    assert result.shadow_action == "ABSTAIN"
    assert result.invalid_support_id_count == 1


def test_obligation_prompt_and_context_do_not_expose_scores():
    messages = _messages(
        OBLIGATION_SUFFICIENCY_SYSTEM_PROMPT,
        "What is the rule?",
        authorized_context([_chunk()]),
    )
    serialized = json.dumps(messages, ensure_ascii=False)

    assert "explicitly supports" in serialized
    assert "0.91" not in serialized
    assert "system overrides" in serialized
