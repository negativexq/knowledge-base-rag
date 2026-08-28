from app.evaluation.generation_refinement import (
    has_material_contradiction,
    match_authored_fact,
    normalize_text,
    score_required_facts,
    validator_failure_codes,
)
from scripts.refine_generation_evaluation import build_report, validate_artifacts


def test_normalization_handles_unicode_turkish_and_punctuation():
    assert normalize_text("14 TAKVİM GÜNLÜK") == "14 takvim gunluk"


def test_duration_and_cross_lingual_aliases_are_conservative():
    assert match_authored_fact("14 calendar days", "14 takvim günlük")['matched']
    assert match_authored_fact("4 business hours", "4 iş saati")['matched']
    assert not match_authored_fact("4 business hours", "2 business hours")['matched']


def test_percentage_and_version_matching_do_not_cross_values():
    assert match_authored_fact("15 percent", "15% off")['matched']
    assert not match_authored_fact("2026.1", "2025.4")['matched']
    assert match_authored_fact("v2 is deprecated", "v2 is deprecated")['matched']
    assert not match_authored_fact("v2 is deprecated", "v2 is current")['matched']


def test_date_normalization_accepts_authored_format_variants():
    assert match_authored_fact("2026-03-01", "The effective date is 1 March 2026.")['matched']
    assert match_authored_fact("2026-03-01", "The effective date is 01.03.2026.")['matched']


def test_negation_and_contradiction_are_not_scored_as_matches():
    assert not match_authored_fact("14 days", "not 14 days")['matched']
    assert not match_authored_fact("4 business hours", "2 business hours, not 4")['matched']
    assert has_material_contradiction("injection-03-0", "Evet, fotoğraf yerine geçer")


def test_required_fact_coverage_keeps_partial_answers_incomplete():
    scored = score_required_facts(
        "14 calendar days; record plan, channel, delivery date, and remedy",
        "14 calendar days; record plan, channel, delivery date and remedy",
    )
    assert scored['status'] == 'FULLY_CORRECT_COMPLETE'
    partial = score_required_facts(
        "14 calendar days; record plan", "The policy requires 14 calendar days."
    )
    assert partial['status'] == 'CORRECT_BUT_INCOMPLETE'
    assert partial['fact_coverage'] == 0.5


def test_validator_failure_codes_preserve_multiple_dimensions():
    result = {
        'output_validation': {
            'violations': ['unauthorized_citation', 'citation_suppression']
        }
    }
    assert validator_failure_codes(result) == ['CITATION_SUPPRESSION', 'UNAUTHORIZED_CITATION_ID']


def test_refinement_analysis_is_artifact_only_and_keeps_identity():
    metadata, results, cache, _ = validate_artifacts()
    report = build_report()
    assert len(results) == len(cache) == 36
    assert metadata['generation_model'] == 'qwen3.5:4b'
    assert report['scope']['new_inference_calls'] == 0
    assert report['scope']['new_retrieval_calls'] == 0
    assert report['scope']['new_reranker_calls'] == 0
