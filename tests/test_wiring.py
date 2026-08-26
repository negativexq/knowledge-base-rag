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

    settings = Settings(_env_file=None)
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
