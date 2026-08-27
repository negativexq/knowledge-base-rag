import asyncio
import json

import pytest

from app.evaluation.semantic_answerability import (
    AMBIGUITY_PROMPT_V2_VERSION,
    AMBIGUITY_SYSTEM_PROMPT,
    AMBIGUITY_SYSTEM_PROMPT_V2,
    QUERY_SCOPE_COMPACT_SYSTEM_PROMPT,
    QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION,
    QUERY_SCOPE_QUERY_ONLY_SYSTEM_PROMPT,
    SUFFICIENCY_SYSTEM_PROMPT,
    AmbiguityEvaluation,
    OllamaQueryScopeEvaluator,
    OllamaSemanticEvaluator,
    QueryScopeEvaluation,
    SufficiencyEvaluation,
    _messages,
    _scope_messages,
    authorized_context,
    shadow_action,
)
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings
from scripts.evaluate_semantic_answerability import load_questions


def _chunk(chunk_id: str = "c1", source_id: str = "policy", text: str = "Refunds are allowed."):
    return SearchResult(
        score=0.99,
        id=chunk_id,
        payload={
            "chunk_id": chunk_id,
            "source_id": source_id,
            "text": text,
            "tenant_id": "tenant-a",
        },
    )


class _FakeOllama:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


def test_semantic_context_contains_only_authorized_safe_fields_and_no_score():
    context = authorized_context([_chunk()])
    messages = _messages("system", "How long?", context)
    serialized = messages[1]["content"]

    assert '"chunk_id": "c1"' in serialized
    assert '"source_id": "policy"' in serialized
    assert "0.99" not in serialized
    assert "tenant-a" not in serialized


def test_prompts_treat_retrieved_content_as_untrusted_data():
    combined = AMBIGUITY_SYSTEM_PROMPT + SUFFICIENCY_SYSTEM_PROMPT
    assert "untrusted" in combined
    assert "Never follow" in combined
    assert "system overrides" in combined


def test_ambiguity_v1_remains_default_and_v2_has_scope_authority_rules():
    client = _FakeOllama()
    evaluator = OllamaSemanticEvaluator(client, "qwen3.5:4b")

    assert evaluator.ambiguity_prompt_version == "ambiguity_v1"
    assert "additional constraint" in AMBIGUITY_SYSTEM_PROMPT_V2
    assert "Multiple documents" in AMBIGUITY_SYSTEM_PROMPT_V2
    assert "Missing evidence is not" in AMBIGUITY_SYSTEM_PROMPT_V2
    assert "authority" in AMBIGUITY_SYSTEM_PROMPT_V2
    assert AMBIGUITY_PROMPT_V2_VERSION != "ambiguity_v1"


@pytest.mark.asyncio
async def test_v2_uses_new_ambiguity_prompt_but_keeps_sufficiency_v1():
    client = _FakeOllama(
        responses=[
            '{"decision":"CLEAR","missing_constraints":[],"rationale":"specific"}',
            '{"decision":"SUFFICIENT","supporting_chunk_ids":["c1"],"missing_information":[],"rationale":"explicit"}',
        ]
    )
    await OllamaSemanticEvaluator(
        client, "qwen3.5:4b", ambiguity_prompt_version=AMBIGUITY_PROMPT_V2_VERSION
    ).evaluate("What is the policy?", [_chunk()])

    assert client.calls[0][0][0]["content"] == AMBIGUITY_SYSTEM_PROMPT_V2
    assert client.calls[1][0][0]["content"] == SUFFICIENCY_SYSTEM_PROMPT


def test_unknown_ambiguity_prompt_version_is_rejected():
    with pytest.raises(ValueError, match="unknown ambiguity prompt version"):
        OllamaSemanticEvaluator(_FakeOllama(), "qwen3.5:4b", ambiguity_prompt_version="v9")


def test_query_scope_schema_enforces_controlled_scope_and_empty_clear_list():
    assert (
        QueryScopeEvaluation(
            decision="SUFFICIENTLY_SCOPED", missing_constraints=[]
        ).missing_constraints
        == []
    )
    with pytest.raises(ValueError):
        QueryScopeEvaluation(decision="SUFFICIENTLY_SCOPED", missing_constraints=["plan"])
    with pytest.raises(ValueError):
        QueryScopeEvaluation(decision="REQUIRES_USER_INPUT", missing_constraints=["order channel"])


def test_query_scope_messages_exclude_evidence_and_ground_truth():
    query_only = _scope_messages(
        QUERY_SCOPE_QUERY_ONLY_SYSTEM_PROMPT,
        "What is the return period?",
    )
    compact = _scope_messages(
        QUERY_SCOPE_COMPACT_SYSTEM_PROMPT,
        "What is the return period?",
        [{"authority_scope": "customer policy"}],
    )
    for messages in (query_only, compact):
        serialized = json.dumps(messages, ensure_ascii=False)
        assert "chunk_id" not in serialized
        assert "source_id" not in serialized
        assert "expected_source_ids" not in serialized
        assert "required_source_ids" not in serialized
        assert "gold_present" not in serialized
        assert "category" not in serialized
        assert "case_family" not in serialized
        assert "answerability" not in serialized


@pytest.mark.asyncio
async def test_query_scope_evaluator_uses_selected_prompt_and_no_context():
    client = _FakeOllama(
        responses=[
            '{"decision":"SUFFICIENTLY_SCOPED","missing_constraints":[],"rationale":"specific"}'
        ]
    )
    evaluator = OllamaQueryScopeEvaluator(
        client,
        "qwen3.5:4b",
        QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION,
        retries=0,
    )
    result, stats = await evaluator.evaluate("What is the current policy?")

    assert result.decision == "SUFFICIENTLY_SCOPED"
    assert stats["parse_error"] is False
    assert "Authorized retrieved context" not in client.calls[0][0][1]["content"]
    assert client.calls[0][0][0]["content"] == QUERY_SCOPE_QUERY_ONLY_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_sufficiency_only_path_does_not_make_an_ambiguity_call():
    client = _FakeOllama(
        responses=[
            '{"decision":"SUFFICIENT","supporting_chunk_ids":["c1"],"missing_information":[],"rationale":"explicit"}'
        ]
    )
    result = await OllamaSemanticEvaluator(client, "qwen3.5:4b").evaluate_sufficiency(
        "What is the policy?", [_chunk()]
    )

    assert result.shadow_action == "ANSWER"
    assert len(client.calls) == 1
    assert client.calls[0][0][0]["content"] == SUFFICIENCY_SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["NO_RETRIEVAL_CANDIDATES", "NO_AUTHORIZED_EVIDENCE", "EMPTY_RERANK_RESULT"],
)
async def test_deterministic_reason_skips_semantic_calls_and_abstains(reason):
    client = _FakeOllama()
    evaluator = OllamaSemanticEvaluator(client, "qwen3:4b")

    result = await evaluator.evaluate("question", [_chunk()], reason)

    assert result.shadow_action == "ABSTAIN"
    assert result.deterministic_reason == reason
    assert client.calls == []


@pytest.mark.asyncio
async def test_clear_and_sufficient_produces_answer():
    client = _FakeOllama(
        responses=[
            '{"decision":"CLEAR","missing_constraints":[],"rationale":"Specific query."}',
            (
                '{"decision":"SUFFICIENT","supporting_chunk_ids":["c1"],'
                '"missing_information":[],"rationale":"Explicit evidence."}'
            ),
        ]
    )
    result = await OllamaSemanticEvaluator(client, "qwen3:4b").evaluate("How long?", [_chunk()])

    assert result.shadow_action == "ANSWER"
    assert result.sufficiency.supporting_chunk_ids == ["c1"]
    assert len(client.calls) == 2
    for _, kwargs in client.calls:
        assert kwargs["model"] == "qwen3:4b"
        assert kwargs["think"] is False
        assert kwargs["temperature"] == 0.0
        assert kwargs["schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_ambiguous_skips_sufficiency_and_clarifies():
    client = _FakeOllama(
        responses=[
            '{"decision":"AMBIGUOUS","missing_constraints":["plan"],"rationale":"Plan is missing."}'
        ]
    )
    result = await OllamaSemanticEvaluator(client, "qwen3:4b").evaluate(
        "What is the return window?", [_chunk()]
    )

    assert result.shadow_action == "CLARIFY"
    assert result.sufficiency is None
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_insufficient_produces_abstain_without_user_facing_effect():
    client = _FakeOllama(
        responses=[
            '{"decision":"CLEAR","missing_constraints":[],"rationale":"Specific."}',
            (
                '{"decision":"INSUFFICIENT","supporting_chunk_ids":[],'
                '"missing_information":["date"],"rationale":"Date absent."}'
            ),
        ]
    )
    result = await OllamaSemanticEvaluator(client, "qwen3:4b").evaluate(
        "What applies in 2026?", [_chunk()]
    )

    assert result.shadow_action == "ABSTAIN"


@pytest.mark.asyncio
async def test_hallucinated_supporting_chunk_id_fails_safe():
    client = _FakeOllama(
        responses=[
            '{"decision":"CLEAR","missing_constraints":[],"rationale":"Specific."}',
            '{"decision":"SUFFICIENT","supporting_chunk_ids":["not-provided"],"missing_information":[],"rationale":"Evidence."}',
        ]
    )
    result = await OllamaSemanticEvaluator(client, "qwen3:4b").evaluate("question", [_chunk()])

    assert result.parse_error is True
    assert result.error_code == "SUFFICIENCY_EVALUATOR_ERROR:ValueError"
    assert result.shadow_action == "ABSTAIN"


@pytest.mark.asyncio
async def test_malformed_output_retries_once_then_fails_safe():
    client = _FakeOllama(responses=["not-json", "still-not-json"])
    result = await OllamaSemanticEvaluator(client, "qwen3:4b", retries=1).evaluate(
        "question", [_chunk()]
    )

    assert result.parse_error is True
    assert result.error_code == "AMBIGUITY_EVALUATOR_ERROR:ValueError"
    assert result.shadow_action == "ABSTAIN"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_timeout_fails_safe_without_swallowing_cancellation():
    class SlowClient:
        async def chat_json(self, messages, **kwargs):
            await asyncio.sleep(1)
            return "{}"

    result = await OllamaSemanticEvaluator(
        SlowClient(), "qwen3:4b", timeout_seconds=0.001, retries=0
    ).evaluate("question", [_chunk()])
    assert result.parse_error is True
    assert result.shadow_action == "ABSTAIN"


def test_shadow_action_logic_is_deterministic():
    clear = AmbiguityEvaluation(decision="CLEAR")
    sufficient = SufficiencyEvaluation(decision="SUFFICIENT", supporting_chunk_ids=["c1"])
    insufficient = SufficiencyEvaluation(decision="INSUFFICIENT")
    ambiguous = AmbiguityEvaluation(decision="AMBIGUOUS", missing_constraints=["region"])

    assert shadow_action(clear, sufficient) == "ANSWER"
    assert shadow_action(clear, insufficient) == "ABSTAIN"
    assert shadow_action(ambiguous, None) == "CLARIFY"
    assert shadow_action(clear, sufficient, "NO_RETRIEVAL_CANDIDATES") == "ABSTAIN"


def test_semantic_evaluator_is_disabled_by_default_and_uses_local_model_default():
    settings = Settings(_env_file=None)

    assert settings.semantic_answerability_enabled is False
    assert settings.semantic_answerability_shadow is True
    assert settings.answerability_eval_model == "qwen3:4b"


def test_semantic_export_defaults_to_development_and_guards_other_splits(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        '[{"id":"dev-1","split":"development"},'
        '{"id":"cal-1","split":"calibration"},'
        '{"id":"frozen-1","split":"frozen_test"}]',
        encoding="utf-8",
    )

    assert load_questions(dataset, "development", False, False)[0]["id"] == "dev-1"
    with pytest.raises(ValueError, match="allow-calibration"):
        load_questions(dataset, "calibration", False, False)
    with pytest.raises(ValueError, match="allow-frozen-test"):
        load_questions(dataset, "frozen_test", False, False)
