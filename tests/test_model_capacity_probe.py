from scripts.benchmark_model_capacity import (
    MODEL,
    SELECTION,
    build_selection_artifact,
    validate_probe_cache,
)


def test_capacity_probe_selection_is_fixed_and_balanced():
    metadata, generation, _, questions = validate_probe_cache()
    selection = build_selection_artifact(metadata, generation, questions)

    assert selection["probe_count"] == 12
    assert selection["query_ids"] == [item[0] for item in SELECTION]
    assert selection["composition"] == {
        "multi_document": 3,
        "hard_answerable": 3,
        "cross_lingual": 2,
        "version_conflict": 2,
        "standard_answerable": 1,
        "injection_bearing": 1,
    }
    assert selection["models"]["probe"] == MODEL


def test_capacity_probe_uses_locked_cache_identity():
    metadata, generation, cache, _ = validate_probe_cache()

    assert metadata["candidate_k"] == 20
    assert metadata["top_n"] == 5
    assert len(generation) == len(cache) == 36
    assert metadata["generation_model"] == "qwen3.5:4b"
