from collections import Counter
from pathlib import Path

import pytest

from scripts.benchmark_balanced_semantic import (
    MODEL,
    _expected_action,
    _load_questions,
    behavioral_target,
    select_balanced_questions,
    validate_balanced_cache,
)


def _question(question_id: str, label: str, category: str, pair: str = "en->en"):
    return {
        "id": question_id,
        "case_family": question_id,
        "answerability": label,
        "category": category,
        "language_pair": pair,
    }


def test_balanced_selection_is_deterministic_and_group_safe():
    questions = _load_questions()
    first = select_balanced_questions(questions, count=48, prior_features=_missing_path())
    second = select_balanced_questions(questions, count=48, prior_features=_missing_path())

    assert [q["id"] for q in first] == [q["id"] for q in second]
    counts = Counter(q["answerability"] for q in first)
    assert counts == {"answerable": 20, "unanswerable": 16, "ambiguous": 12}
    assert max(counts.values()) < 24


def _missing_path():
    return Path("/tmp/phase-6c2-no-prior-features.jsonl")


def test_behavioral_target_mapping_is_explicit():
    answerable = _question("a", "answerable", "standard_answerable")
    ambiguous = _question("c", "ambiguous", "ambiguous")
    negative = _question("n", "unanswerable", "unanswerable")
    assert behavioral_target(answerable, True) == "SHOULD_ANSWER"
    assert behavioral_target(answerable, False) == "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL"
    assert behavioral_target(ambiguous, False) == "SHOULD_CLARIFY"
    assert behavioral_target(negative, False) == "SHOULD_ABSTAIN"
    assert _expected_action("SHOULD_ABSTAIN_DUE_TO_RETRIEVAL") == "ABSTAIN"


def test_balanced_cache_identity_fails_closed():
    fingerprints = {"corpus_fingerprint": "c", "dataset_fingerprint": "d"}
    metadata = {
        "corpus_fingerprint": "c",
        "dataset_fingerprint": "d",
        "collection": "collection",
        "retrieval_config_fingerprint": "wrong",
        "evaluator_model": MODEL,
        "authorized_only": True,
    }
    with pytest.raises(ValueError, match="retrieval_config_fingerprint"):
        validate_balanced_cache(metadata, fingerprints, "collection")


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = [
            '{"decision":"CLEAR","missing_constraints":[],"rationale":"specific"}',
            '{"decision":"SUFFICIENT","supporting_chunk_ids":["c1"],"missing_information":[],"rationale":"explicit"}',
        ]

    async def chat_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_balanced_evaluator_reads_cache_only_and_never_retrieves(monkeypatch):
    import scripts.benchmark_balanced_semantic as module
    from app.evaluation.semantic_answerability import AMBIGUITY_PROMPT_V2_VERSION

    monkeypatch.setattr(module, "search", lambda *args, **kwargs: pytest.fail("retrieval called"))
    records = [
        {
            "query_id": "deterministic",
            "case_family": "deterministic",
            "category": "acl_negative",
            "behavioral_target": "SHOULD_ABSTAIN",
            "ground_truth_label": "unanswerable",
            "query_language": "en",
            "evidence_language": None,
            "language_pair": "en->none",
            "gold_present": False,
            "all_required_present": False,
            "deterministic_reason": "NO_AUTHORIZED_EVIDENCE",
            "query": "What is the private limit?",
            "authorized_top5": [],
        },
        {
            "query_id": "semantic",
            "case_family": "semantic",
            "category": "standard_answerable",
            "behavioral_target": "SHOULD_ANSWER",
            "ground_truth_label": "answerable",
            "query_language": "en",
            "evidence_language": "en",
            "language_pair": "en->en",
            "gold_present": True,
            "all_required_present": True,
            "deterministic_reason": None,
            "query": "What is the policy?",
            "authorized_top5": [
                {"chunk_id": "c1", "source_id": "s1", "content": "The policy is explicit."}
            ],
        },
    ]
    summary, rows = await module.evaluate_model(
        MODEL,
        records,
        _FakeClient(),
        retries=0,
        ambiguity_prompt_version=AMBIGUITY_PROMPT_V2_VERSION,
    )
    assert summary["query_count"] == 2
    assert rows[0]["shadow_action"] == "ABSTAIN"
    assert summary["reliability"]["evaluator_calls"] == 2
