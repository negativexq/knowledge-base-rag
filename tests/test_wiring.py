from types import SimpleNamespace

import pytest

from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.shared.config import Settings
from app.wiring import build_chat_dependencies, build_connectors


def test_build_connectors_always_includes_filesystem():
    connectors = build_connectors(Settings(notion_api_key=None))

    assert set(connectors) == {"filesystem"}
    assert isinstance(connectors["filesystem"], LocalFilesystemConnector)


def test_build_connectors_includes_notion_only_when_api_key_is_set():
    connectors = build_connectors(Settings(notion_api_key="secret-token"))

    assert set(connectors) == {"filesystem", "notion"}
    assert isinstance(connectors["notion"], NotionConnector)


@pytest.mark.asyncio
async def test_real_chat_wiring_uses_server_security_mode(monkeypatch):
    import app.wiring as wiring

    calls = {}

    async def fake_stream_answer(*args, **kwargs):
        calls.update(kwargs)
        if False:
            yield {}

    monkeypatch.setattr(wiring, "build_reranker", lambda settings: object())
    monkeypatch.setattr(wiring, "get_chat_provider", lambda settings: object())
    monkeypatch.setattr(
        wiring,
        "active_embedding_config",
        lambda settings: SimpleNamespace(query_prefix=lambda: "", output_dimension=1024),
    )
    monkeypatch.setattr(wiring, "stream_answer", fake_stream_answer)

    settings = Settings(
        _env_file=None,
        rag_pipeline_v2=False,
        support_ids_enabled=False,
    )
    dependencies, _ = build_chat_dependencies(
        settings,
        qdrant_client=object(),
        ollama=object(),
        sparse_encoder=object(),
        collection_name="test",
    )

    assert dependencies.security_validation_mode == "strict"
    [event async for event in dependencies.stream_fn("question", [])]
    assert calls["validation_mode"] == "strict"


@pytest.mark.asyncio
async def test_default_wiring_uses_support_unit_architecture_v2_path(monkeypatch):
    import app.wiring as wiring

    for name in (
        "RAG_PIPELINE_V2",
        "SUPPORT_IDS_ENABLED",
        "CRITICAL_VALIDATOR_VERSION",
        "CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    calls = {}

    async def fake_support_units(*args, **kwargs):
        calls["path"] = "support_units"
        calls["kwargs"] = kwargs
        yield {"type": "metadata"}

    async def unexpected_path(*args, **kwargs):
        raise AssertionError("default profile selected a non-support path")
        if False:
            yield {}

    monkeypatch.setattr(wiring, "build_reranker", lambda settings: object())
    monkeypatch.setattr(wiring, "get_chat_provider", lambda settings: object())
    monkeypatch.setattr(
        wiring,
        "active_embedding_config",
        lambda settings: SimpleNamespace(query_prefix=lambda: "", output_dimension=1024),
    )
    monkeypatch.setattr(wiring, "stream_support_unit_answer", fake_support_units)
    monkeypatch.setattr(wiring, "stream_evidence_backed_answer", unexpected_path)
    monkeypatch.setattr(wiring, "stream_answer", unexpected_path)

    settings = Settings(_env_file=None)
    assert settings.rag_pipeline_v2 is True
    assert settings.support_ids_enabled is True
    dependencies, _ = build_chat_dependencies(
        settings,
        qdrant_client=object(),
        ollama=object(),
        sparse_encoder=object(),
        collection_name="test",
    )

    [event async for event in dependencies.stream_fn("question", [])]

    assert calls["path"] == "support_units"
    assert calls["kwargs"]["validator_version"] == "architecture_v2"
    assert dependencies.pipeline_version == "pipeline_support_ids"
    assert dependencies.output_contract_version == "output_contract_support_ids"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rag_pipeline_v2", "support_ids_enabled", "expected_path"),
    [
        (False, False, "legacy"),
        (True, False, "evidence_backed"),
    ],
)
async def test_explicit_non_support_profiles_remain_available(
    monkeypatch, rag_pipeline_v2, support_ids_enabled, expected_path
):
    import app.wiring as wiring

    calls = {}

    async def fake_support_units(*args, **kwargs):
        calls["path"] = "support_units"
        yield {}

    async def fake_evidence_backed(*args, **kwargs):
        calls["path"] = "evidence_backed"
        yield {}

    async def fake_legacy(*args, **kwargs):
        calls["path"] = "legacy"
        yield {}

    monkeypatch.setattr(wiring, "build_reranker", lambda settings: object())
    monkeypatch.setattr(wiring, "get_chat_provider", lambda settings: object())
    monkeypatch.setattr(
        wiring,
        "active_embedding_config",
        lambda settings: SimpleNamespace(query_prefix=lambda: "", output_dimension=1024),
    )
    monkeypatch.setattr(wiring, "stream_support_unit_answer", fake_support_units)
    monkeypatch.setattr(wiring, "stream_evidence_backed_answer", fake_evidence_backed)
    monkeypatch.setattr(wiring, "stream_answer", fake_legacy)

    settings = Settings(
        _env_file=None,
        rag_pipeline_v2=rag_pipeline_v2,
        support_ids_enabled=support_ids_enabled,
    )
    dependencies, _ = build_chat_dependencies(
        settings,
        qdrant_client=object(),
        ollama=object(),
        sparse_encoder=object(),
        collection_name="test",
    )

    [event async for event in dependencies.stream_fn("question", [])]

    assert calls["path"] == expected_path


def test_real_chat_wiring_keeps_semantic_gate_disabled_by_default(monkeypatch):
    """Phase 6 research components must not enter the active path by default."""
    import app.wiring as wiring

    monkeypatch.setattr(wiring, "build_reranker", lambda settings: object())
    monkeypatch.setattr(wiring, "get_chat_provider", lambda settings: object())
    monkeypatch.setattr(
        wiring,
        "active_embedding_config",
        lambda settings: SimpleNamespace(query_prefix=lambda: "", output_dimension=1024),
    )

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("semantic evaluator is research-only and disabled by default")

    monkeypatch.setattr(wiring, "OllamaSemanticEvaluator", fail_if_constructed)

    dependencies, _ = build_chat_dependencies(
        Settings(_env_file=None),
        qdrant_client=object(),
        ollama=object(),
        sparse_encoder=object(),
        collection_name="test",
    )

    assert dependencies.semantic_evaluator is None
