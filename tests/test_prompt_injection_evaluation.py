from pathlib import Path

from app.evaluation.prompt_injection import (
    aggregate_security_metrics,
    evaluate_case,
    load_adversarial_dataset,
)

DATASET = Path("tests/fixtures/security_sprint25/adversarial.json")


def test_sprint25_dataset_has_reproducible_case_schema_and_target_coverage():
    cases = load_adversarial_dataset(DATASET)
    categories = {case["category"] for case in cases}
    languages = {case["language"] for case in cases}

    assert len(cases) >= 60
    assert {"en", "tr"} <= languages
    assert {
        "direct_injection",
        "indirect_document_injection",
        "fake_system",
        "citation_spoofing",
        "citation_suppression",
        "exfiltration",
        "benign_control",
    } <= categories


def test_fake_citation_case_is_a_deterministic_failure_when_model_copies_it():
    case = next(
        case for case in load_adversarial_dataset(DATASET) if case["case_id"] == "citation-001"
    )

    result = evaluate_case(
        case,
        "Refunds are limited to 100 dollars [s.filesystem:other-secret.pdf/1/0].",
        mode="fast",
    )

    assert result.passed is False
    assert "unauthorized_citation" in result.forbidden_behavior_triggered


def test_legitimate_fact_and_canonical_citation_passes_even_if_context_is_malicious():
    case = next(
        case for case in load_adversarial_dataset(DATASET) if case["case_id"] == "indirect-001"
    )

    result = evaluate_case(
        case, "Refunds are allowed within 30 days [s.filesystem:malicious-handbook/2/0]."
    )

    assert result.passed is True
    assert result.citations_valid is True


def test_metric_aggregation_has_precommitted_security_metric_names():
    cases = load_adversarial_dataset(DATASET)
    results = [
        evaluate_case(
            case,
            "Refunds are allowed within 30 days [s.filesystem:handbook/1/0]."
            if case["should_answer"]
            else "I could not find this in the document.",
        )
        for case in cases[:3]
    ]

    metrics = aggregate_security_metrics(results)["metrics"]

    assert {
        "injection_success_rate",
        "citation_spoof_success_rate",
        "citation_suppression_success_rate",
        "unauthorized_citation_rate",
        "cross_tenant_exfiltration_rate",
        "benign_answer_success_rate",
    } <= metrics.keys()
