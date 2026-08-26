import json

from app.evaluation.generation_sanity import (
    aggregate_generation_sanity,
    validate_generation_sanity_record,
)
from app.evaluation.reranker_timing import (
    balanced_config_order,
    candidate_text_fingerprint,
    summarize_latencies,
    timed_call,
)


def _record(**overrides):
    record = {
        "query_id": "q1",
        "language_pair": "en→en",
        "expected_behavior": "supported_answer",
        "citation_integrity": True,
        "not_found_result": {"expected": False, "expected_phrase_present": False},
        "strict_validation": {
            "output_policy_passed": True,
            "unsafe_tokens_released": False,
        },
        "generation_success": True,
        "pass": True,
    }
    record.update(overrides)
    return record


def test_generation_sanity_schema_and_aggregation():
    records = [
        _record(),
        _record(
            query_id="nf",
            language_pair="tr→unknown",
            expected_behavior="not_found",
            not_found_result={"expected": True, "expected_phrase_present": True},
        ),
        _record(
            query_id="attack",
            language_pair="security",
            expected_behavior="security_control",
            strict_validation={
                "output_policy_passed": False,
                "blocked_before_release": True,
                "unsafe_tokens_released": False,
            },
        ),
    ]
    for record in records:
        validate_generation_sanity_record(record)
    summary = aggregate_generation_sanity(records)
    assert summary["record_count"] == 3
    assert summary["not_found_accuracy"] == 1.0
    assert summary["security_control_pass_rate"] == 1.0
    json.dumps(records)


def test_candidate_text_fingerprint_is_stable_and_sensitive_to_input():
    first = candidate_text_fingerprint("q", ["a", "b"])
    second = candidate_text_fingerprint("q", ["a", "b"])
    changed = candidate_text_fingerprint("q", ["a", "c"])
    assert first == second
    assert first["sha256"] != changed["sha256"]
    assert first["candidate_count"] == 2


def test_balanced_benchmark_order_is_deterministic_and_balanced():
    configs = ("baseline", "256", "512")
    order = balanced_config_order(configs, repetitions=5, seed=2701)
    assert order == balanced_config_order(configs, repetitions=5, seed=2701)
    assert all(order.count(config) == 5 for config in configs)


def test_timing_helper_excludes_unrelated_work():
    state = {"unrelated": 0}

    def measured():
        return "prediction"

    result, elapsed = timed_call(measured)
    state["unrelated"] += 1
    assert result == "prediction"
    assert elapsed >= 0
    assert state["unrelated"] == 1


def test_latency_aggregation_reports_required_statistics():
    result = summarize_latencies([1.0, 2.0, 3.0, 4.0, 5.0])
    assert result["count"] == 5
    assert result["mean_ms"] == 3.0
    assert result["median_ms"] == result["p50_ms"] == 3.0
    assert result["p95_ms"] == 5.0
    assert result["stddev_ms"] > 0
