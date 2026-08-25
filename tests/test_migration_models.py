from app.migration.models import MigrationManifest, MigrationStatus


def _manifest(**overrides) -> MigrationManifest:
    base = dict(
        migration_id="mig-test",
        started_at="2026-01-01T00:00:00+00:00",
        source_collection="kb_chunks",
        source_fingerprint="abc",
        target_collection="kb_qwen3_4b_1024_def",
        target_fingerprint="def",
        target_model="qwen3-embedding:4b",
        target_dimension=1024,
        expected_document_count=3,
        expected_chunk_count=42,
    )
    base.update(overrides)
    return MigrationManifest(**base)


def test_default_status_is_planned():
    assert _manifest().status == MigrationStatus.PLANNED


def test_save_and_load_round_trips_all_fields(tmp_path):
    manifest = _manifest(documents_completed=2, chunks_completed=10)
    manifest.status = MigrationStatus.INDEXING
    path = tmp_path / "migration-result.json"

    manifest.save(path)
    loaded = MigrationManifest.load(path)

    assert loaded.migration_id == manifest.migration_id
    assert loaded.status == MigrationStatus.INDEXING
    assert loaded.documents_completed == 2
    assert loaded.chunks_completed == 10


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "migration-result.json"

    _manifest().save(path)

    assert path.exists()


def test_touch_updates_updated_at():
    manifest = _manifest()
    original = manifest.updated_at

    manifest.touch()

    assert manifest.updated_at >= original


def test_status_enum_has_exactly_the_eight_specified_states():
    assert {s.value for s in MigrationStatus} == {
        "PLANNED", "INDEXING", "VALIDATING", "READY_TO_SWITCH", "SWITCHING",
        "ACTIVE", "ROLLED_BACK", "FAILED",
    }


def test_as_dict_serializes_status_as_plain_string():
    manifest = _manifest()

    assert manifest.as_dict()["status"] == "PLANNED"
