"""NotionConnector tests against httpx.MockTransport simulating REAL Notion
API JSON shapes (per Notion's official API reference: POST /v1/search,
GET /v1/blocks/{id}/children, both cursor-paginated with
next_cursor/has_more) — no real network call. This machine has no
NOTION_API_KEY / .env, so these are NOT run against the real API; see
docs/sprint-06-plan.md and tests/test_notion_e2e.py for the honest
real-vs-mocked breakdown.
"""

import hashlib

import httpx
import pytest

from app.connectors.base import Connector, ConnectorDocument
from app.connectors.notion import NotionConnector, NotionUnreachableError


def _search_response(results: list[dict], has_more: bool = False, next_cursor: str | None = None):
    return {"object": "list", "results": results, "has_more": has_more, "next_cursor": next_cursor}


def _page(page_id: str, last_edited_time: str) -> dict:
    return {"object": "page", "id": page_id, "last_edited_time": last_edited_time}


def _rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text}, "plain_text": text}]


def _heading_block(level: int, text: str) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rich_text(text)}}


def _paragraph_block(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _connector(handler) -> NotionConnector:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.notion.com/v1"
    )
    return NotionConnector(api_key="secret_test_key", http_client=http_client)


@pytest.mark.asyncio
async def test_list_documents_parses_search_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search"
        return httpx.Response(
            200,
            json=_search_response([_page("page-1", "2024-01-01T00:00:00.000Z")]),
        )

    documents = await _connector(handler).list_documents()

    assert documents == [
        ConnectorDocument(
            source_id="page-1", content_type="notion", etag="2024-01-01T00:00:00.000Z"
        )
    ]


@pytest.mark.asyncio
async def test_list_documents_sends_authorization_and_notion_version_headers():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["notion_version"] = request.headers.get("notion-version")
        return httpx.Response(200, json=_search_response([]))

    await _connector(handler).list_documents()

    assert captured["authorization"] == "Bearer secret_test_key"
    assert captured["notion_version"] == "2022-06-28"


@pytest.mark.asyncio
async def test_list_documents_filters_search_to_pages_only():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json=_search_response([]))

    await _connector(handler).list_documents()

    assert captured_body["filter"] == {"property": "object", "value": "page"}


@pytest.mark.asyncio
async def test_list_documents_follows_cursor_pagination():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                200,
                json=_search_response(
                    [_page("page-1", "2024-01-01T00:00:00.000Z")],
                    has_more=True,
                    next_cursor="cursor-abc",
                ),
            )
        return httpx.Response(
            200, json=_search_response([_page("page-2", "2024-01-02T00:00:00.000Z")])
        )

    documents = await _connector(handler).list_documents()

    assert call_count == 2
    assert {d.source_id for d in documents} == {"page-1", "page-2"}


@pytest.mark.asyncio
async def test_fetch_content_renders_headings_and_paragraphs_as_markdown():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/blocks/page-1/children"
        return httpx.Response(
            200,
            json=_search_response(
                [_heading_block(1, "Kurulum"), _paragraph_block("Install steps here.")]
            ),
        )

    document = ConnectorDocument(source_id="page-1", content_type="notion", etag="e1")
    content = await _connector(handler).fetch_content(document)

    assert content.decode("utf-8") == "# Kurulum\n\nInstall steps here."


@pytest.mark.asyncio
async def test_fetch_content_skips_unsupported_block_types():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_search_response(
                [
                    {"object": "block", "type": "divider", "divider": {}},
                    {"object": "block", "type": "image", "image": {}},
                    _paragraph_block("Real content."),
                ]
            ),
        )

    document = ConnectorDocument(source_id="page-1", content_type="notion", etag="e1")
    content = await _connector(handler).fetch_content(document)

    assert content.decode("utf-8") == "Real content."


@pytest.mark.asyncio
async def test_fetch_content_follows_cursor_pagination():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                200,
                json=_search_response(
                    [_paragraph_block("First block.")], has_more=True, next_cursor="cursor-xyz"
                ),
            )
        return httpx.Response(200, json=_search_response([_paragraph_block("Second block.")]))

    document = ConnectorDocument(source_id="page-1", content_type="notion", etag="e1")
    content = await _connector(handler).fetch_content(document)

    assert call_count == 2
    assert content.decode("utf-8") == "First block.\n\nSecond block."


@pytest.mark.asyncio
async def test_get_content_hash_is_sha256_of_etag():
    document = ConnectorDocument(
        source_id="page-1", content_type="notion", etag="2024-01-01T00:00:00.000Z"
    )
    connector = NotionConnector(api_key="k", http_client=httpx.AsyncClient())

    result = await connector.get_content_hash(document)

    assert result == hashlib.sha256(b"2024-01-01T00:00:00.000Z").hexdigest()


@pytest.mark.asyncio
async def test_get_content_hash_does_not_call_the_api():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("get_content_hash must not make any HTTP request")

    document = ConnectorDocument(source_id="page-1", content_type="notion", etag="e1")
    await _connector(handler).get_content_hash(document)  # must not raise


@pytest.mark.asyncio
async def test_get_content_hash_changes_when_etag_changes():
    connector = NotionConnector(api_key="k", http_client=httpx.AsyncClient())
    doc_v1 = ConnectorDocument(source_id="page-1", content_type="notion", etag="v1")
    doc_v2 = ConnectorDocument(source_id="page-1", content_type="notion", etag="v2")

    assert await connector.get_content_hash(doc_v1) != await connector.get_content_hash(doc_v2)


@pytest.mark.asyncio
async def test_retries_on_429_honoring_retry_after_header():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                429, headers={"Retry-After": "0"}, json={"message": "rate limited"}
            )
        return httpx.Response(200, json=_search_response([]))

    documents = await _connector(handler).list_documents()

    assert call_count == 2
    assert documents == []


@pytest.mark.asyncio
async def test_raises_after_exhausting_retries_on_persistent_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "rate limited"})

    with pytest.raises(NotionUnreachableError):
        await _connector(handler).list_documents()


@pytest.mark.asyncio
async def test_raises_notion_unreachable_error_on_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    with pytest.raises(NotionUnreachableError):
        await _connector(handler).list_documents()


@pytest.mark.asyncio
async def test_raises_notion_unreachable_error_on_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(NotionUnreachableError):
        await _connector(handler).list_documents()


def test_source_type_is_notion():
    assert NotionConnector(api_key="k", http_client=httpx.AsyncClient()).source_type == "notion"


def test_satisfies_the_connector_protocol():
    assert isinstance(NotionConnector(api_key="k", http_client=httpx.AsyncClient()), Connector)
