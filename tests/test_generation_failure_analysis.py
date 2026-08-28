from scripts.analyze_generation_failures import build_analysis, validate_inputs


def test_phase7_failure_analysis_validates_existing_identity_without_inference():
    metadata, results, cache = validate_inputs()

    assert metadata["generation_model"] == "qwen3.5:4b"
    assert len(results) == 36
    assert len(cache) == 36


def test_phase7_failure_analysis_keeps_gold_present_and_reviewed_counts_separate():
    analysis = build_analysis()

    assert analysis["scope"]["new_inference_calls"] == 0
    assert analysis["scope"]["new_retrieval_calls"] == 0
    assert analysis["reviewed_correctness"]["deterministic_correct"] == 3
    assert analysis["reviewed_correctness"]["gold_present_answerable"] == 22
    assert analysis["reviewed_correctness"]["deterministic_evaluator_false_negatives"] == 7


def test_phase7_failure_analysis_reports_validator_rejections_separately():
    analysis = build_analysis()

    assert analysis["validator"]["failure_count"] == 7
    assert analysis["validator"]["potentially_correct_but_rejected_count"] == 7
    assert analysis["injection_control"]["control_failures"] == 0
