"""Sprint 23 section 14/28: deterministic Qdrant point IDs must include
tenant_id in their canonical key — the same doc/chunk coordinates
(source_type, source_id, doc_id, page, paragraph, char_range) under two
different tenants must produce two DIFFERENT point UUIDs, never the
same one (which would mean the second tenant's upsert silently
overwrites the first tenant's point).
"""

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import QdrantStore


def _chunk(tenant_id: str) -> Chunk:
    return Chunk(
        doc_id="same-hash",
        source_type="filesystem",
        source_id="handbook.pdf",
        page_number=1,
        paragraph_index=0,
        char_range=(0, 10),
        text="identical text",
        tenant_id=tenant_id,
    )


def test_identical_coordinates_under_different_tenants_produce_different_point_ids():
    chunk_a = _chunk("tenant-a")
    chunk_b = _chunk("tenant-b")

    assert QdrantStore.point_id_for(chunk_a) != QdrantStore.point_id_for(chunk_b)


def test_identical_coordinates_under_the_same_tenant_produce_the_same_point_id():
    chunk_a = _chunk("tenant-a")
    chunk_a_again = _chunk("tenant-a")

    assert QdrantStore.point_id_for(chunk_a) == QdrantStore.point_id_for(chunk_a_again)


def test_default_tenant_chunk_has_a_different_point_id_than_an_explicit_tenant():
    """A chunk that never had tenant_id set (legacy default "default")
    must not accidentally collide with a real tenant named something
    else — the tenant segment is a real part of the key, not a no-op
    when left at its default.
    """
    default_chunk = Chunk(
        doc_id="same-hash", source_type="filesystem", source_id="handbook.pdf",
        page_number=1, paragraph_index=0, char_range=(0, 10), text="x",
    )
    tenant_a_chunk = _chunk("tenant-a")

    assert QdrantStore.point_id_for(default_chunk) != QdrantStore.point_id_for(tenant_a_chunk)
