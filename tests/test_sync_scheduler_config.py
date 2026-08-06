from app.shared.config import Settings
from app.sync.scheduler import sync_intervals_from_settings


def test_includes_filesystem_by_default():
    intervals = sync_intervals_from_settings(Settings())

    assert intervals["filesystem"] == 300.0


def test_excludes_notion_when_no_api_key_configured():
    intervals = sync_intervals_from_settings(Settings(notion_api_key=None))

    assert "notion" not in intervals


def test_includes_notion_when_api_key_is_configured():
    intervals = sync_intervals_from_settings(Settings(notion_api_key="secret"))

    assert intervals["notion"] == 1800.0


def test_uses_configured_interval_values():
    settings = Settings(
        filesystem_sync_interval_seconds=60.0,
        notion_api_key="secret",
        notion_sync_interval_seconds=120.0,
    )

    intervals = sync_intervals_from_settings(settings)

    assert intervals == {"filesystem": 60.0, "notion": 120.0}
