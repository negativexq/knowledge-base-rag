from scripts.measurement_lock_m0 import IDENTITY, run_key


def test_run_key_binds_query_seed_snapshot_and_pipeline():
    snapshot = {"context_hash": "ctx-a"}
    first = run_key("q-1", 42, snapshot, "pipeline_v2_2_evidence_backed")
    assert first == run_key("q-1", 42, snapshot, "pipeline_v2_2_evidence_backed")
    assert first != run_key("q-1", 43, snapshot, "pipeline_v2_2_evidence_backed")
    assert first != run_key("q-1", 42, {"context_hash": "ctx-b"}, "pipeline_v2_2_evidence_backed")


def test_measurement_identity_keeps_locked_generation_settings():
    assert IDENTITY["generator"] == "qwen3.5:4b"
    assert IDENTITY["prompt"] == "v3"
    assert IDENTITY["num_ctx"] == 4096
    assert IDENTITY["think"] is False
    assert IDENTITY["temperature"] == 0.0
