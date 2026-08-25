from app.shared.config import Settings


def test_active_prompt_version_defaults_to_v1():
    assert Settings().active_prompt_version == "v1"


def test_active_prompt_version_overridable_via_env(monkeypatch):
    monkeypatch.setenv("ACTIVE_PROMPT_VERSION", "v2")

    assert Settings().active_prompt_version == "v2"


def test_generation_provider_defaults_to_ollama_local_first():
    assert Settings().generation_provider == "ollama"


def test_embedding_provider_defaults_to_ollama():
    assert Settings().embedding_provider == "ollama"


def test_generation_provider_overridable_to_claude(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "claude")

    assert Settings().generation_provider == "claude"


def test_generation_provider_rejects_unknown_value(monkeypatch):
    import pytest

    monkeypatch.setenv("GENERATION_PROVIDER", "openai")

    with pytest.raises(Exception):
        Settings()


def test_claude_api_key_defaults_to_none():
    assert Settings().claude_api_key is None


def test_claude_model_has_a_default():
    assert Settings().claude_model


def test_registry_db_path_has_a_default():
    assert Settings().registry_db_path == "data/registry.db"


def test_filesystem_sync_interval_defaults_to_five_minutes():
    assert Settings().filesystem_sync_interval_seconds == 300.0


def test_notion_sync_interval_defaults_to_thirty_minutes():
    assert Settings().notion_sync_interval_seconds == 1800.0


def test_filesystem_root_path_has_a_default():
    assert Settings().filesystem_root_path == "data/documents"


def test_embedding_concurrency_has_a_default(monkeypatch):
    monkeypatch.delenv("EMBEDDING_CONCURRENCY", raising=False)
    assert Settings().embedding_concurrency > 0


def test_embedding_concurrency_overridable_via_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_CONCURRENCY", "8")

    assert Settings().embedding_concurrency == 8


def test_embedding_concurrency_of_zero_is_rejected_at_startup(monkeypatch):
    """A real bug class this closes: asyncio.Semaphore(0) never lets any
    embed call through, so EMBEDDING_CONCURRENCY=0 used to pass Settings()
    silently and only deadlock later, the first time a real sync ran.
    """
    import pytest

    monkeypatch.setenv("EMBEDDING_CONCURRENCY", "0")

    with pytest.raises(Exception):
        Settings()


def test_embedding_concurrency_negative_is_rejected_at_startup(monkeypatch):
    import pytest

    monkeypatch.setenv("EMBEDDING_CONCURRENCY", "-1")

    with pytest.raises(Exception):
        Settings()


def test_filesystem_sync_interval_of_zero_is_rejected_at_startup(monkeypatch):
    import pytest

    monkeypatch.setenv("FILESYSTEM_SYNC_INTERVAL_SECONDS", "0")

    with pytest.raises(Exception):
        Settings()


def test_notion_sync_interval_negative_is_rejected_at_startup(monkeypatch):
    import pytest

    monkeypatch.setenv("NOTION_SYNC_INTERVAL_SECONDS", "-30")

    with pytest.raises(Exception):
        Settings()


# --------------------------------- Sprint 22: production embedding default


def test_embedding_model_key_defaults_to_qwen3_4b():
    """Sprint 22: the migration this default represents is executed via
    app/migration — a matching real Qdrant collection must exist and be
    activated for this to actually serve traffic; see
    app/migration/startup_guard.py's fail-fast guard.
    """
    assert Settings().embedding_model_key == "qwen3-4b"


def test_embedding_output_dimension_defaults_to_1024():
    assert Settings().embedding_output_dimension == 1024


def test_embedding_model_key_overridable_via_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL_KEY", "nomic")

    assert Settings().embedding_model_key == "nomic"


def test_embedding_model_key_rejects_unknown_value(monkeypatch):
    import pytest

    monkeypatch.setenv("EMBEDDING_MODEL_KEY", "made-up-model")

    with pytest.raises(Exception):
        Settings()


def test_qdrant_active_alias_defaults_to_kb_active():
    assert Settings().qdrant_active_alias == "kb_active"


def test_qdrant_active_alias_overridable_via_env(monkeypatch):
    monkeypatch.setenv("QDRANT_ACTIVE_ALIAS", "kb_prod")

    assert Settings().qdrant_active_alias == "kb_prod"
