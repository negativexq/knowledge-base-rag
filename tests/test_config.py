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
