from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.shared.config import Settings
from app.wiring import build_connectors


def test_build_connectors_always_includes_filesystem():
    connectors = build_connectors(Settings(notion_api_key=None))

    assert set(connectors) == {"filesystem"}
    assert isinstance(connectors["filesystem"], LocalFilesystemConnector)


def test_build_connectors_includes_notion_only_when_api_key_is_set():
    connectors = build_connectors(Settings(notion_api_key="secret-token"))

    assert set(connectors) == {"filesystem", "notion"}
    assert isinstance(connectors["notion"], NotionConnector)
