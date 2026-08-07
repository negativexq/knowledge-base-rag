import httpx

from app.ui.sources_client import fetch_sources, fetch_sync_history, trigger_sync


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend.test")


def test_fetch_sources_returns_parsed_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/sources"
        return httpx.Response(
            200,
            json=[
                {"source_type": "filesystem", "document_count": 3, "is_running": False},
                {"source_type": "notion", "document_count": 0, "is_running": True},
            ],
        )

    result = fetch_sources(client=_client_for(handler))

    assert result == [
        {"source_type": "filesystem", "document_count": 3, "is_running": False},
        {"source_type": "notion", "document_count": 0, "is_running": True},
    ]


def test_trigger_sync_posts_to_the_right_source_type():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/sync/filesystem"
        return httpx.Response(200, json={"source_type": "filesystem", "status": "success"})

    result = trigger_sync("filesystem", client=_client_for(handler))

    assert result == {"source_type": "filesystem", "status": "success"}


def test_trigger_sync_returns_error_body_on_409_instead_of_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"status": "rejected_already_running"}})

    result = trigger_sync("filesystem", client=_client_for(handler))

    assert result == {"detail": {"status": "rejected_already_running"}}


def test_fetch_sync_history_gets_the_right_source_type():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/sync/notion/history"
        return httpx.Response(200, json=[{"id": 1, "status": "success"}])

    result = fetch_sync_history("notion", client=_client_for(handler))

    assert result == [{"id": 1, "status": "success"}]
