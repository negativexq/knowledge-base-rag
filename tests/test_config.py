from app.shared.config import Settings


def test_active_prompt_version_defaults_to_v1():
    assert Settings().active_prompt_version == "v1"


def test_active_prompt_version_overridable_via_env(monkeypatch):
    monkeypatch.setenv("ACTIVE_PROMPT_VERSION", "v2")

    assert Settings().active_prompt_version == "v2"
