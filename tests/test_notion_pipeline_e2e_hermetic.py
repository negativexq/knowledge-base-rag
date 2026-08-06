"""Sprint 6 DoD: NotionConnector proven through the FULL pipeline (real
ingest_connector -> real Qdrant (:memory:) -> real SQLite registry), and
proof that Sprint 4's incremental sync (skip/update/delete) works for
Notion completely unchanged — same ingest_connector code, same
DocumentRegistry, only a different Connector implementation.

The Notion side is a small stateful fake HTTP server (a dict of pages this
test mutates between ingest_connector calls to simulate real edits/
deletions), driven through httpx.MockTransport — no real network call. See
docs/sprint-06-plan.md and tests/test_notion_e2e.py for why: no
NOTION_API_KEY / .env on this machine.
"""

import httpx
import pytest
from qdrant_client import QdrantClient

from app.connectors.notion import NotionConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector

COLLECTION = "test_notion_pipeline_e2e_hermetic"


class _CountingStore(QdrantStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upsert_calls = 0
        self.delete_calls = 0

    def upsert_chunks(self, *args, **kwargs):
        self.upsert_calls += 1
        return super().upsert_chunks(*args, **kwargs)

    def delete_by_source(self, *args, **kwargs):
        self.delete_calls += 1
        return super().delete_by_source(*args, **kwargs)


class _FakeNotionWorkspace:
    """In-memory Notion workspace: {page_id: {"last_edited_time": ..., "blocks": [...]}}.
    Mutating self.pages between ingest_connector() calls simulates real
    edits/deletions a real workspace would show up with on the next sync.
    """

    def __init__(self):
        self.pages: dict[str, dict] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/search":
            results = [
                {"object": "page", "id": page_id, "last_edited_time": page["last_edited_time"]}
                for page_id, page in self.pages.items()
            ]
            return httpx.Response(
                200, json={"object": "list", "results": results, "has_more": False}
            )

        if request.url.path.startswith("/v1/blocks/") and request.url.path.endswith("/children"):
            page_id = request.url.path.removeprefix("/v1/blocks/").removesuffix("/children")
            blocks = self.pages[page_id]["blocks"]
            return httpx.Response(
                200, json={"object": "list", "results": blocks, "has_more": False}
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")


def _rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text}, "plain_text": text}]


def _heading(text: str) -> dict:
    return {"object": "block", "type": "heading_1", "heading_1": {"rich_text": _rich_text(text)}}


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


async def _fake_embed(text: str) -> list[float]:
    vector = [0.01] * EMBEDDING_DIM
    vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
    return vector


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def _connector(workspace: _FakeNotionWorkspace) -> NotionConnector:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(workspace.handler), base_url="https://api.notion.com/v1"
    )
    return NotionConnector(api_key="test-key", http_client=http_client)


def _store() -> _CountingStore:
    return _CountingStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


@pytest.mark.asyncio
async def test_notion_pages_ingest_with_source_type_notion_and_heading_citations(tmp_path):
    workspace = _FakeNotionWorkspace()
    workspace.pages["page-kurulum"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("Kurulum"), _paragraph("Install steps go here.")],
    }

    store = _store()
    registry = _registry(tmp_path)
    stats = await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    assert stats.files_processed == 1
    points, _ = store._client.scroll(COLLECTION, limit=10)
    assert points
    point = points[0]
    assert point.payload["source_type"] == "notion"
    assert point.payload["source_id"] == "page-kurulum"
    assert point.payload["heading_path"] == ["Kurulum"]
    assert "Install steps" in point.payload["text"]

    record = registry.get_document("notion", "page-kurulum")
    assert record is not None
    assert record.source_type == "notion"


@pytest.mark.asyncio
async def test_notion_sync_skips_unchanged_pages_with_zero_qdrant_writes(tmp_path):
    workspace = _FakeNotionWorkspace()
    workspace.pages["page-a"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("A"), _paragraph("Content A.")],
    }

    store = _store()
    registry = _registry(tmp_path)
    first = await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )
    assert first.files_processed == 1
    assert store.upsert_calls > 0

    store.upsert_calls = 0
    store.delete_calls = 0
    second = await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    assert second.files_skipped == 1
    assert second.files_processed == 0
    assert store.upsert_calls == 0
    assert store.delete_calls == 0


@pytest.mark.asyncio
async def test_notion_sync_updates_only_the_edited_page(tmp_path):
    workspace = _FakeNotionWorkspace()
    workspace.pages["page-a"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("A"), _paragraph("Original content A.")],
    }
    workspace.pages["page-b"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("B"), _paragraph("Content B unrelated.")],
    }

    store = _store()
    registry = _registry(tmp_path)
    await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    b_points_before = {
        p.id: p.payload
        for p in store._client.scroll(COLLECTION, limit=100)[0]
        if p.payload["source_id"] == "page-b"
    }

    # simulate a real edit: content AND last_edited_time change
    workspace.pages["page-a"] = {
        "last_edited_time": "2024-02-01T00:00:00.000Z",
        "blocks": [_heading("A"), _paragraph("Completely rewritten content A.")],
    }
    stats = await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    assert stats.files_processed == 1
    assert stats.files_skipped == 1  # page-b untouched

    all_points, _ = store._client.scroll(COLLECTION, limit=100)
    a_points = [p for p in all_points if p.payload["source_id"] == "page-a"]
    b_points_after = {p.id: p.payload for p in all_points if p.payload["source_id"] == "page-b"}

    assert any("rewritten" in p.payload["text"] for p in a_points)
    assert not any("Original" in p.payload["text"] for p in a_points)
    assert b_points_after == b_points_before


@pytest.mark.asyncio
async def test_notion_sync_deletes_pages_removed_from_the_workspace(tmp_path):
    workspace = _FakeNotionWorkspace()
    workspace.pages["page-a"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("A"), _paragraph("Content A.")],
    }
    workspace.pages["page-b"] = {
        "last_edited_time": "2024-01-01T00:00:00.000Z",
        "blocks": [_heading("B"), _paragraph("Content B.")],
    }

    store = _store()
    registry = _registry(tmp_path)
    await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    del workspace.pages["page-a"]  # simulates the page being deleted in Notion
    stats = await ingest_connector(
        _connector(workspace), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    assert stats.files_deleted == 1
    all_points, _ = store._client.scroll(COLLECTION, limit=100)
    assert not any(p.payload["source_id"] == "page-a" for p in all_points)
    assert any(p.payload["source_id"] == "page-b" for p in all_points)
    assert registry.get_document("notion", "page-a") is None
    assert registry.get_document("notion", "page-b") is not None
