import asyncio
import hashlib

import httpx

from app.connectors.base import ConnectorDocument

NOTION_API_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
_PAGE_SIZE = 100

# heading_1/2/3 build the heading_path stack (rendered as "#"/"##"/"###",
# reusing app/parsing/markdown_parser.py's own heading syntax); these block
# types carry citable text. Everything else (image, table, divider, embed,
# ...) is skipped — no text content, or out of MVP scope. Deliberately not
# recursive into nested children — same restraint as
# LocalFilesystemConnector's non-recursive folder scan.
_HEADING_LEVEL = {"heading_1": 1, "heading_2": 2, "heading_3": 3}
_TEXT_BLOCK_TYPES = {
    "paragraph",
    "bulleted_list_item",
    "numbered_list_item",
    "quote",
    "to_do",
    "code",
}


class NotionUnreachableError(Exception):
    """Raised when the Notion API cannot be reached, or returns an error
    that isn't a rate limit (rate limits are retried automatically)."""


def _plain_text(rich_text: list[dict]) -> str:
    return "".join(segment.get("plain_text", "") for segment in rich_text)


def _render_block(block: dict) -> str | None:
    block_type = block.get("type")
    if block_type in _HEADING_LEVEL:
        text = _plain_text(block.get(block_type, {}).get("rich_text", []))
        if not text:
            return None
        return f"{'#' * _HEADING_LEVEL[block_type]} {text}"
    if block_type in _TEXT_BLOCK_TYPES:
        text = _plain_text(block.get(block_type, {}).get("rich_text", []))
        return text or None
    return None


class NotionConnector:
    """source_id is the Notion page's own UUID — already citation-tag-safe
    (hex digits and hyphens only), no slugify needed.

    get_content_hash() hashes etag (the page's last_edited_time, captured
    during list_documents()) rather than fetching full block content —
    Sprint 4's has_changed() runs this on every sync, and a full block
    fetch just to answer "did anything change" would defeat incremental
    sync's whole point for a network-bound connector. See
    docs/sprint-06-plan.md.
    """

    source_type = "notion"

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=NOTION_API_BASE_URL, timeout=timeout
        )
        # Attached per-request (not as client-level defaults) so auth still
        # applies even when a caller injects their own http_client (as
        # tests do, to point requests at a mock transport).
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self._max_retries = max_retries

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise NotionUnreachableError(f"Could not reach Notion API: {exc}") from exc

            if response.status_code == 429 and attempt < self._max_retries:
                retry_after = float(
                    response.headers.get("Retry-After", DEFAULT_BACKOFF_SECONDS * (2**attempt))
                )
                await asyncio.sleep(retry_after)
                attempt += 1
                continue

            if response.status_code >= 400:
                raise NotionUnreachableError(
                    f"Notion API returned {response.status_code}: {response.text}"
                )
            return response

    async def list_documents(self) -> list[ConnectorDocument]:
        documents: list[ConnectorDocument] = []
        cursor: str | None = None
        while True:
            body = {"filter": {"property": "object", "value": "page"}, "page_size": _PAGE_SIZE}
            if cursor:
                body["start_cursor"] = cursor

            data = (await self._request("POST", "/search", json=body)).json()
            for page in data.get("results", []):
                documents.append(
                    ConnectorDocument(
                        source_id=page["id"],
                        content_type="notion",
                        etag=page["last_edited_time"],
                    )
                )
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return documents

    async def fetch_content(self, document: ConnectorDocument) -> bytes:
        rendered_blocks: list[str] = []
        cursor: str | None = None
        while True:
            params = {"page_size": _PAGE_SIZE}
            if cursor:
                params["start_cursor"] = cursor

            data = (
                await self._request(
                    "GET", f"/blocks/{document.source_id}/children", params=params
                )
            ).json()
            for block in data.get("results", []):
                rendered = _render_block(block)
                if rendered is not None:
                    rendered_blocks.append(rendered)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return "\n\n".join(rendered_blocks).encode("utf-8")

    async def get_content_hash(self, document: ConnectorDocument) -> str:
        return hashlib.sha256((document.etag or "").encode()).hexdigest()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
