import uuid

import pytest
from qdrant_client import QdrantClient, models

from app.evidence.documents import DocumentRead, DocumentReader, DocumentRef
from app.security.models import RetrievalContext


@pytest.fixture
def reader():
    client = QdrantClient(":memory:")
    client.create_collection("docs", vectors_config=models.VectorParams(size=1, distance="Cosine"))
    points = []
    for tenant, version in [("a", "v1"), ("b", "v1"), ("a", "v2")]:
        for i, text in enumerate(["Overview", "Linux supports TLS", "Windows instructions"]):
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=[1.0],
                    payload={
                        "tenant_id": tenant,
                        "source_type": "filesystem",
                        "source_id": "manual",
                        "document_version": version,
                        "page_number": i + 1,
                        "paragraph_index": 0,
                        "heading_path": ["Intro" if i == 0 else "Setup"],
                        "text": text,
                    },
                )
            )
    client.upsert("docs", points)
    yield DocumentReader(client, "docs", RetrievalContext("a"), ["manual"])
    client.close()


def request(action="outline", **kwargs):
    return DocumentRead(
        document=DocumentRef(source_type="filesystem", source_id="manual", document_version="v1"),
        action=action,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_outline_and_section_keep_version_and_tenant(reader):
    result = await reader.read(request())
    assert len(result.outline) == 2
    assert result.outline[1]["chunk_count"] == 2
    section = await reader.read(request("section", section_id=result.outline[1]["section_id"]))
    assert [b.payload["text"] for b in section.blocks] == [
        "Linux supports TLS",
        "Windows instructions",
    ]
    assert all(
        b.payload["tenant_id"] == "a" and b.payload["document_version"] == "v1"
        for b in section.blocks
    )


@pytest.mark.asyncio
async def test_search_neighbors_and_page_require_no_embeddings(reader):
    result = await reader.read(request("search", query="linux TLS"))
    assert len(result.blocks) == 1
    neighbors = await reader.read(request("neighbors", chunk_id=result.blocks[0].id))
    assert len(neighbors.blocks) == 3
    page = await reader.read(request("page", page=3))
    assert page.blocks[0].payload["text"] == "Windows instructions"


@pytest.mark.asyncio
async def test_scope_cannot_be_widened(reader):
    reader.source_ids = frozenset({"another"})
    assert (await reader.read(request())).outline == []
    reader.context = RetrievalContext(None)
    with pytest.raises(Exception, match="no tenant_id"):
        await reader.read(request())


@pytest.mark.asyncio
async def test_pagination_and_missing_documents_are_explicit(reader):
    first = await reader.read(request(limit=1))
    assert first.has_more and first.next_offset == 1
    second = await reader.read(request(offset=1))
    assert not second.has_more
    missing = request()
    missing.document.document_version = "missing"
    assert (await reader.read(missing)).outline == []
