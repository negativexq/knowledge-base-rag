import json

import pytest

from app.evaluation.semantic_answerability import (
    FIXED_OBLIGATION_SUPPORT_SYSTEM_PROMPT,
    ObligationExtraction,
    OllamaFixedObligationEvaluator,
    QueryObligation,
    SupportEvaluation,
    _fixed_support_messages,
    _query_obligation_messages,
    aggregate_fixed_obligation_support,
    authorized_context,
)
from app.retrieval.hybrid_search import SearchResult
from scripts.benchmarks.benchmark_fixed_obligation_support import _evaluate_candidate


def _chunk(chunk_id: str = "c1", text: str = "The policy explicitly states the rule."):
    return SearchResult(
        score=0.91,
        id=chunk_id,
        payload={"chunk_id": chunk_id, "source_id": "policy", "text": text},
    )


class _FakeOllama:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.responses.pop(0)


def _extraction(*descriptions: str) -> str:
    return json.dumps(
        {
            "obligations": [
                {"id": f"o{index}", "description": description}
                for index, description in enumerate(descriptions, start=1)
            ]
        }
    )


def _support(*items: tuple[str, str, list[str]]) -> str:
    return json.dumps(
        {
            "results": [
                {
                    "obligation_id": obligation_id,
                    "status": status,
                    "supporting_chunk_ids": chunk_ids,
                    "rationale": "Explicit support.",
                }
                for obligation_id, status, chunk_ids in items
            ]
        }
    )


@pytest.mark.asyncio
async def test_extractor_receives_query_only_and_returns_fixed_obligations():
    client = _FakeOllama(_extraction("activation evidence", "retry policy"))
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)

    result = await evaluator.extract("What evidence is required and what is the retry policy?")

    assert result.extraction is not None
    assert [item.id for item in result.extraction.obligations] == ["o1", "o2"]
    user_message = client.calls[0][0][1]["content"]
    assert "What evidence is required" in user_message
    assert "Authorized retrieved context" not in user_message
    assert "source_id" not in user_message
    assert "expected_source_ids" not in user_message


def test_extraction_schema_bounds_and_deduplicates_ids():
    with pytest.raises(ValueError, match="unique"):
        ObligationExtraction(
            obligations=[
                QueryObligation(id="o1", description="same"),
                QueryObligation(id="o1", description="same"),
            ]
        )

    with pytest.raises(ValueError):
        ObligationExtraction(
            obligations=[QueryObligation(id=f"o{i}", description="fact") for i in range(1, 8)]
        )


def test_support_prompt_keeps_fixed_obligations_and_omits_scores():
    obligations = [QueryObligation(id="o1", description="return window")]
    messages = _fixed_support_messages(
        FIXED_OBLIGATION_SUPPORT_SYSTEM_PROMPT,
        "What is the return window?",
        obligations,
        authorized_context([_chunk()]),
    )
    serialized = json.dumps(messages, ensure_ascii=False)

    assert "return window" in serialized
    assert "c1" in serialized
    assert "0.91" not in serialized
    assert "do not add, delete, rewrite" in serialized
    assert "expected_source_ids" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected_decision", "expected_action"),
    [
        (["SUPPORTED", "SUPPORTED"], "SUFFICIENT", "ANSWER"),
        (["SUPPORTED", "UNSUPPORTED"], "INSUFFICIENT", "ABSTAIN"),
    ],
)
async def test_support_is_aggregated_deterministically(
    statuses, expected_decision, expected_action
):
    response = _support(
        ("o1", statuses[0], ["c1"] if statuses[0] == "SUPPORTED" else []),
        ("o2", statuses[1], ["c1"] if statuses[1] == "SUPPORTED" else []),
    )
    client = _FakeOllama(response)
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)
    obligations = [
        QueryObligation(id="o1", description="first fact"),
        QueryObligation(id="o2", description="second fact"),
    ]

    result = await evaluator.verify("What are the two facts?", obligations, [_chunk()])

    assert result.decision == expected_decision
    assert result.shadow_action == expected_action
    assert result.parse_error is False


def test_support_aggregation_requires_exact_fixed_obligation_ids():
    obligations = [QueryObligation(id="o1", description="fact")]
    evaluation = SupportEvaluation(
        results=[
            {"obligation_id": "o2", "status": "SUPPORTED", "supporting_chunk_ids": ["c1"]}
        ]
    )

    with pytest.raises(ValueError, match="exactly match"):
        aggregate_fixed_obligation_support(obligations, evaluation)


@pytest.mark.asyncio
async def test_unknown_support_chunk_id_fails_safe():
    client = _FakeOllama(_support(("o1", "SUPPORTED", ["not-authorized"])))
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)
    obligations = [QueryObligation(id="o1", description="requested fact")]

    result = await evaluator.verify("What is the fact?", obligations, [_chunk()])

    assert result.parse_error is True
    assert result.shadow_action == "ABSTAIN"
    assert result.invalid_chunk_id_count == 1


@pytest.mark.asyncio
async def test_invalid_support_status_combination_fails_safe():
    client = _FakeOllama(_support(("o1", "UNSUPPORTED", ["c1"])))
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)
    obligations = [QueryObligation(id="o1", description="requested fact")]

    result = await evaluator.verify("What is the fact?", obligations, [_chunk()])

    assert result.parse_error is True
    assert result.invalid_support_status_count == 1


@pytest.mark.asyncio
async def test_extraction_errors_are_bounded_and_fail_safe():
    client = _FakeOllama(json.dumps({"obligations": []}))
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)

    result = await evaluator.extract("What is requested?")

    assert result.parse_error is True
    assert result.zero_obligation_count == 1


@pytest.mark.asyncio
async def test_support_evaluator_receives_fixed_obligations_unchanged():
    client = _FakeOllama(_support(("o1", "SUPPORTED", ["c1"])))
    evaluator = OllamaFixedObligationEvaluator(client, "qwen3.5:4b", retries=0)
    obligations = [QueryObligation(id="o1", description="exact requested component")]

    await evaluator.verify("What is the component?", obligations, [_chunk()])

    user_message = client.calls[0][0][1]["content"]
    assert "exact requested component" in user_message
    assert '"id": "o1"' in user_message
    assert "0.91" not in user_message


def test_query_only_helper_does_not_include_context_or_ground_truth():
    messages = _query_obligation_messages("system", "What is the answer?")
    serialized = json.dumps(messages)
    assert "What is the answer?" in serialized
    assert "chunk" not in serialized
    assert "ground_truth" not in serialized


@pytest.mark.asyncio
async def test_candidate_runner_short_circuits_without_retrieval_or_generation_calls():
    class _NoCallClient:
        async def chat_json(self, *args, **kwargs):
            raise AssertionError("semantic call should be skipped")

    base = {
        "query_id": "q1",
        "case_family": "f1",
        "category": "acl_negative",
        "behavioral_target": "SHOULD_ABSTAIN",
        "ground_truth_label": "unanswerable",
        "query_language": "en",
        "evidence_language": None,
        "language_pair": "en->none",
        "gold_present": False,
        "all_required_present": False,
        "deterministic_reason": "ACL_NEGATIVE_OFFLINE_SAFETY_SLICE",
        "query": "Which private fact is available?",
    }
    scope = {
        key: base[key]
        for key in (
            "query_id",
            "case_family",
            "category",
            "behavioral_target",
            "ground_truth_label",
            "query_language",
            "evidence_language",
            "language_pair",
            "gold_present",
            "all_required_present",
            "deterministic_reason",
        )
    }
    scope.update({"query_scope": None})

    rows, reliability = await _evaluate_candidate(
        [base], [scope], _NoCallClient(), timeout_seconds=1, retries=0
    )

    assert rows[0]["shadow_action"] == "ABSTAIN"
    assert rows[0]["failure_attribution"] == "DETERMINISTIC_SAFETY"
    assert reliability["extraction_calls"] == 0
    assert reliability["support_calls"] == 0
