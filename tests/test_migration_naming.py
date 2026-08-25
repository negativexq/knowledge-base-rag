from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.llm.embedding_models import get_embedding_model_config, nomic_config
from app.migration.naming import collection_name_for, sanitize_label
from app.shared.config import Settings


def test_sanitize_label_replaces_at_dot_and_dash():
    assert sanitize_label("qwen3-0.6b@768") == "qwen3_0_6b_768"


def test_collection_name_for_is_human_readable_and_includes_fingerprint_prefix():
    settings = Settings()
    config = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)
    fingerprint = build_pipeline_fingerprint(config)

    name = collection_name_for(config, fingerprint)

    assert name.startswith("kb_qwen3_4b_1024_")
    assert name.endswith(fingerprint.digest()[:8])


def test_collection_name_for_differs_for_different_fingerprints():
    settings = Settings()
    config = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)
    fp_a = build_pipeline_fingerprint(config)

    # A different index schema version would change the fingerprint even
    # though the model/dimension label stays identical — collection names
    # must differ too, since the underlying data would be incompatible.
    from dataclasses import replace

    fp_b = replace(fp_a, index_schema_version=fp_a.index_schema_version + 1)

    assert collection_name_for(config, fp_a) != collection_name_for(config, fp_b)


def test_collection_name_for_nomic_reads_as_nomic():
    settings = Settings()
    config = nomic_config(settings)
    fingerprint = build_pipeline_fingerprint(config)

    name = collection_name_for(config, fingerprint)

    assert name.startswith("kb_nomic_native_")
