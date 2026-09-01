import json

import pytest

from scripts.benchmarks.benchmark_semantic_models import (
    DEFAULT_MODELS,
    build_cache_metadata,
    evaluate_model,
    load_cache,
    partition_requested_models,
    select_model,
    select_smoke_questions,
    validate_cache,
)


def _question(question_id: str, category: str, language_pair: str = "en->en"):
    return {
        "id": question_id,
        "case_family": question_id,
        "category": category,
        "language_pair": language_pair,
    }


def test_smoke_query_selection_is_deterministic_and_covers_critical_categories():
    questions = [
        _question(f"{category}-1", category)
        for category in (
            "standard_answerable",
            "hard_answerable",
            "cross_lingual",
            "multi_document",
            "version_conflict",
            "injection_bearing",
            "acl_negative",
            "unanswerable",
            "ambiguous",
        )
    ]
    questions.extend(_question(f"fill-{i}", "standard_answerable") for i in range(20))
    questions.append(_question("tr-en", "standard_answerable", "tr->en"))
    questions.append(_question("en-tr", "standard_answerable", "en->tr"))

    first = select_smoke_questions(sorted(questions, key=lambda q: q["id"]), 25)
    second = select_smoke_questions(sorted(questions, key=lambda q: q["id"]), 25)

    assert [q["id"] for q in first] == [q["id"] for q in second]
    assert {q["category"] for q in first} >= {
        "standard_answerable",
        "hard_answerable",
        "cross_lingual",
        "multi_document",
        "version_conflict",
        "injection_bearing",
        "acl_negative",
        "unanswerable",
        "ambiguous",
    }
    assert {q["language_pair"] for q in first} >= {"tr->en", "en->tr"}


def test_cache_identity_fails_closed_on_fingerprint_or_config_mismatch(tmp_path):
    fingerprints = {"corpus_fingerprint": "corpus", "dataset_fingerprint": "dataset"}
    metadata = build_cache_metadata(fingerprints, "collection", ["q1"])
    validate_cache(metadata, fingerprints, "collection")

    with pytest.raises(ValueError, match="corpus_fingerprint"):
        validate_cache(metadata, {**fingerprints, "corpus_fingerprint": "other"}, "collection")
    with pytest.raises(ValueError, match="retrieval_config_fingerprint"):
        validate_cache(
            {**metadata, "retrieval_config_fingerprint": "other"}, fingerprints, "collection"
        )


def test_cache_loader_rejects_forbidden_score_or_unauthorized_metadata(tmp_path):
    fingerprints = {"corpus_fingerprint": "corpus", "dataset_fingerprint": "dataset"}
    metadata = build_cache_metadata(fingerprints, "collection", ["q1"])
    (tmp_path / "cache-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "fingerprints.json").write_text(json.dumps(fingerprints), encoding="utf-8")
    (tmp_path / "evaluator-inputs.jsonl").write_text(
        json.dumps(
            {
                "query_id": "q1",
                "authorized_top5": [
                    {
                        "chunk_id": "c1",
                        "source_id": "s1",
                        "content": "safe",
                        "score": 0.9,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden retrieval metadata"):
        load_cache(tmp_path, tmp_path / "fingerprints.json", "collection")


def test_model_availability_partition_is_deterministic_and_explicit():
    evaluated, skipped = partition_requested_models(
        ["qwen3.5:4b", "missing:1b", "gemma2:2b"], {"gemma2:2b", "qwen3.5:4b"}
    )
    assert evaluated == ["qwen3.5:4b", "gemma2:2b"]
    assert skipped == {"missing:1b": "not installed locally"}


def test_selection_is_safety_first_not_latency_first():
    def summary(model, false_answers, ambiguity_f1, total_p95):
        return {
            "model": model,
            "ambiguity": {"f1": ambiguity_f1},
            "sufficiency": {"f1": 1.0},
            "combined": {
                "false_answer_count": false_answers,
                "gold_present_answerable_coverage": 0.5,
            },
            "injection_robustness": {"status": "PASS"},
            "reliability": {"final_parse_failure_count": 0, "timeout_count": 0},
            "latency": {"total": {"p95": total_p95}},
        }

    result = select_model(
        [summary("fast-unsafe", 1, 1.0, 1.0), summary("safe", 0, 0.5, 10.0)]
    )
    assert result == {"status": "SELECT_MODEL", "model": "safe"}


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.responses.pop(0)


def _record(query_id: str, deterministic_reason=None):
    return {
        "query_id": query_id,
        "case_family": query_id,
        "category": "standard_answerable",
        "ground_truth_label": "answerable",
        "query_language": "en",
        "evidence_language": "en",
        "language_pair": "en->en",
        "gold_present": True,
        "all_required_present": True,
        "deterministic_reason": deterministic_reason,
        "query": "What is the policy?",
        "authorized_top5": [
            {"chunk_id": "c1", "source_id": "source", "content": "The policy is explicit."}
        ],
    }


@pytest.mark.asyncio
async def test_evaluator_only_runner_reuses_exact_input_order_and_skips_deterministic_record():
    records = [_record("q0", "NO_AUTHORIZED_EVIDENCE"), _record("q1")]
    responses = [
        '{"decision":"CLEAR","missing_constraints":[],"rationale":"Specific."}',
        '{"decision":"SUFFICIENT","supporting_chunk_ids":["c1"],"missing_information":[],"rationale":"Explicit."}',
    ]
    first_client = _FakeClient(responses)
    second_client = _FakeClient(responses)
    first, first_rows = await evaluate_model("model-a", records, first_client, retries=0)
    second, second_rows = await evaluate_model("model-b", records, second_client, retries=0)

    assert [r["query_id"] for r in first_rows] == ["q0", "q1"]
    assert [r["query_id"] for r in second_rows] == ["q0", "q1"]
    assert first_rows[0]["shadow_action"] == "ABSTAIN"
    assert len(first_client.calls) == 2
    assert len(second_client.calls) == 2
    assert first["model"] == "model-a"
    assert second["model"] == "model-b"
    assert DEFAULT_MODELS == ("qwen3.5:4b", "qwen2.5:3b-instruct", "gemma2:2b")
