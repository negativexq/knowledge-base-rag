import numpy as np

from scripts.calibrate_answerability import (
    ABSTAIN_REASONS,
    ALL_FEATURES,
    LEAKAGE_FIELDS,
    _apply_safety_override,
    _finite_thresholds,
    _policy_status,
    _ranking_metrics,
    family_metrics,
    target,
)


def _record(family: str, label: str, reason: str = "FEATURES_AVAILABLE") -> dict:
    return {
        "case_family": family,
        "answerability_label": label,
        "deterministic_reason": reason,
    }


def test_binary_mapping_is_explicit_and_deterministic():
    assert target(_record("a", "answerable")) == 0
    assert target(_record("b", "unanswerable")) == 1
    assert target(_record("c", "ambiguous")) == 1


def test_classifier_inputs_are_retrieval_features_only():
    assert not set(ALL_FEATURES) & set(LEAKAGE_FIELDS)


def test_deterministic_safety_reasons_override_statistical_prediction():
    records = [
        _record("a", "unanswerable", ABSTAIN_REASONS[0]),
        _record("b", "answerable"),
    ]
    predictions = _apply_safety_override(records, np.array([0, 0]))
    assert predictions.tolist() == [1, 0]


def test_family_metrics_macro_average_query_outcomes_inside_family():
    records = [
        _record("family-a", "answerable"),
        _record("family-a", "answerable"),
        _record("family-b", "unanswerable"),
    ]
    metrics = family_metrics(records, np.array([0, 1, 1]))
    assert metrics["family_count"] == 2
    assert metrics["answerable_coverage"] == 0.5
    assert metrics["false_answer_rate"] == 0.0


def test_threshold_candidates_are_sorted_and_include_outer_bounds():
    thresholds = _finite_thresholds(np.array([0.2, 0.4, 0.4]))
    assert thresholds == sorted(thresholds)
    assert thresholds[0] < 0.2
    assert thresholds[-1] > 0.4


def test_ranking_metrics_use_abstain_target_and_include_both_classes():
    records = [
        _record("a", "unanswerable"),
        _record("b", "answerable"),
        _record("c", "ambiguous"),
        _record("d", "answerable"),
    ]
    metrics = _ranking_metrics(records, np.array([0.9, 0.1, 0.8, 0.2]))
    assert metrics["auroc"] == 1.0
    assert metrics["auprc"] == 1.0


def test_policy_status_does_not_lock_when_critical_slice_has_zero_coverage():
    result = {
        "metrics": {"false_answer": 0, "correct_answer": 1},
        "slices": {
            "category": {
                "multi_document": {
                    "answerable_count": 2,
                    "answerable_coverage": 0.0,
                }
            }
        },
    }
    status, reason = _policy_status(result)
    assert status == "INCONCLUSIVE"
    assert "multi_document" in reason
