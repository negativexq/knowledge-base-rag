"""Sprint 23 section 13/28: registry document identity must include
tenant_id — two tenants using the identical (source_type, source_id)
pair (a real scenario: both configure a "filesystem" source, and a user
on each side happens to name a file "handbook.pdf") must never collide
on one registry row.
"""

from app.registry.store import DocumentRegistry


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


def test_same_source_id_across_two_tenants_does_not_collide(tmp_path):
    registry = _registry(tmp_path)

    registry.upsert_document("tenant-a", "filesystem", "handbook.pdf", "hash-a")
    registry.upsert_document("tenant-b", "filesystem", "handbook.pdf", "hash-b")

    record_a = registry.get_document("tenant-a", "filesystem", "handbook.pdf")
    record_b = registry.get_document("tenant-b", "filesystem", "handbook.pdf")

    assert record_a.content_hash == "hash-a"
    assert record_b.content_hash == "hash-b"


def test_updating_tenant_as_document_does_not_affect_tenant_bs_row(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("tenant-a", "filesystem", "handbook.pdf", "hash-a-v1")
    registry.upsert_document("tenant-b", "filesystem", "handbook.pdf", "hash-b-v1")

    registry.upsert_document("tenant-a", "filesystem", "handbook.pdf", "hash-a-v2")

    assert registry.get_document("tenant-a", "filesystem", "handbook.pdf").content_hash == (
        "hash-a-v2"
    )
    assert registry.get_document("tenant-b", "filesystem", "handbook.pdf").content_hash == (
        "hash-b-v1"
    )


def test_deleting_tenant_as_document_does_not_delete_tenant_bs(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("tenant-a", "filesystem", "handbook.pdf", "hash-a")
    registry.upsert_document("tenant-b", "filesystem", "handbook.pdf", "hash-b")

    registry.delete_document("tenant-a", "filesystem", "handbook.pdf")

    assert registry.get_document("tenant-a", "filesystem", "handbook.pdf") is None
    assert registry.get_document("tenant-b", "filesystem", "handbook.pdf") is not None


def test_list_documents_filtered_by_tenant_excludes_other_tenants(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("tenant-a", "filesystem", "a.pdf", "hash-a")
    registry.upsert_document("tenant-b", "filesystem", "b.pdf", "hash-b")

    records = registry.list_documents(tenant_id="tenant-a")

    assert {(r.tenant_id, r.source_id) for r in records} == {("tenant-a", "a.pdf")}


def test_list_documents_with_no_tenant_filter_returns_all_tenants_admin_only(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("tenant-a", "filesystem", "a.pdf", "hash-a")
    registry.upsert_document("tenant-b", "filesystem", "b.pdf", "hash-b")

    records = registry.list_documents()

    assert {r.tenant_id for r in records} == {"tenant-a", "tenant-b"}


def test_has_changed_is_evaluated_per_tenant_not_globally(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("tenant-a", "filesystem", "handbook.pdf", "hash-a")

    # tenant-b has never registered this (source_type, source_id) pair —
    # must report changed=True even though tenant-a's row has the same
    # source_type/source_id.
    assert registry.has_changed("tenant-b", "filesystem", "handbook.pdf", "anything") is True
