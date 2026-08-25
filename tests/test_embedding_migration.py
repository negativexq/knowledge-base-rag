"""Sprint 22: hermetic tests for the migration engine — no real Ollama,
:memory: Qdrant, real markdown fixture files through LocalFilesystemConnector
+ ingest_connector (unchanged, real chunking/parsing), a fake deterministic
embed_fn. Covers planning, collection lifecycle/naming, indexing
idempotency/resume, structural validation gates, atomic activation,
rollback (including symmetry), and failure handling — see
docs/sprint-22-plan.md section 33 for the required coverage this maps to.
"""

import json

import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import get_embedding_model_config
from app.migration import embedding_migration as engine
from app.migration.models import MigrationStatus
from app.migration.naming import collection_name_for
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.shared.config import Settings

DIMENSION = 32


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))

    def embed_query(self, text: str) -> SparseVector:
        return self.embed_document(text)


async def _fake_embed_fn(text: str) -> list[float]:
    vector = [0.01] * DIMENSION
    vector[hash(text.lower()[:20]) % DIMENSION] = 1.0
    return vector


def _write_docs(tmp_path) -> LocalFilesystemConnector:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.\n")
    (docs_dir / "two.md").write_text("# Two\n\nContent about oranges.\n")
    return LocalFilesystemConnector(str(docs_dir))


def _target_config(settings: Settings):
    return get_embedding_model_config(
        settings.embedding_model_key, settings, output_dimension=DIMENSION
    )


async def _index(
    qdrant_client, target_registry, connector, manifest, manifest_path, target_config
):
    fingerprint = build_pipeline_fingerprint(target_config)
    return await engine.run_indexing(
        manifest, qdrant_client, target_registry, {"filesystem": connector}, _fake_embed_fn,
        _FakeSparseEncoder(), target_config, fingerprint, manifest_path,
    )


# ---------------------------------------------------------------- planning


def test_no_migration_required_when_fingerprints_match(tmp_path):
    settings = Settings(embedding_model_key="nomic", embedding_output_dimension=None)
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    # Bootstrapping: mark the (nomic) source as already "active" at the
    # SAME config the plan will compute as target — the only way source
    # and target can genuinely match given resolve_source_state's default
    # nomic-fallback assumption.
    plan = engine.plan_migration(client, registry, settings)

    assert plan.no_migration_required is True


def test_migration_required_when_target_model_differs_from_default_source(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=1024)
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")

    plan = engine.plan_migration(client, registry, settings)

    assert plan.no_migration_required is False
    assert plan.target_model != plan.source_model


def test_migration_required_when_only_dimension_differs(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=1024)
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    # Pin the active state to the SAME model at native dimension, so only
    # the output_dimension differs between source and target.
    native = get_embedding_model_config("qwen3-4b", settings)
    registry.set_metadata(
        engine.ACTIVE_STATE_KEY,
        json.dumps({
            "embedding_model_key": "qwen3-4b", "output_dimension": None,
            "fingerprint_digest": build_pipeline_fingerprint(native).digest(),
            "collection": "kb_qwen3_4b_native_x", "migration_id": None,
        }),
    )

    plan = engine.plan_migration(client, registry, settings)

    assert plan.no_migration_required is False
    assert plan.target_dimension == 1024


def test_migration_required_when_query_instruction_differs(tmp_path):
    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qwen3_query_instruction="a different instruction",
    )
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    registry.set_metadata(
        engine.ACTIVE_STATE_KEY,
        json.dumps({
            "embedding_model_key": "qwen3-4b", "output_dimension": 1024,
            "fingerprint_digest": "stale-digest-from-before-instruction-changed",
            "collection": "kb_qwen3_4b_1024_x", "migration_id": None,
        }),
    )

    plan = engine.plan_migration(client, registry, settings)

    assert plan.no_migration_required is False


# --------------------------------------------------- collection lifecycle


@pytest.mark.asyncio
async def test_target_collection_name_matches_naming_module(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)

    plan = engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=0, expected_chunk_count=0,
    )
    manifest = engine.new_manifest(plan)

    assert manifest.target_collection == collection_name_for(target_config, fingerprint)


@pytest.mark.asyncio
async def test_old_collection_is_never_touched_by_indexing(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    client = QdrantClient(":memory:")
    client.create_collection(
        "kb_chunks",
        vectors_config={"dense": __import__("qdrant_client").http.models.VectorParams(
            size=768, distance=__import__("qdrant_client").http.models.Distance.COSINE
        )},
    )
    old_count_before = client.count("kb_chunks").count

    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)
    connector = _write_docs(tmp_path)
    target_registry = DocumentRegistry(tmp_path / "target_registry.db")
    manifest = engine.new_manifest(engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=2, expected_chunk_count=2,
    ))

    await _index(client, target_registry, connector, manifest, tmp_path / "m.json", target_config)

    assert client.count("kb_chunks").count == old_count_before
    assert manifest.target_collection != "kb_chunks"


# ------------------------------------------------------------- migration


@pytest.mark.asyncio
async def test_full_migration_indexes_all_documents(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    client = QdrantClient(":memory:")
    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)
    connector = _write_docs(tmp_path)
    target_registry = DocumentRegistry(tmp_path / "target_registry.db")
    manifest = engine.new_manifest(engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=2, expected_chunk_count=2,
    ))

    stats = await _index(
        client, target_registry, connector, manifest, tmp_path / "m.json", target_config
    )

    assert stats.files_processed == 2
    assert manifest.status == MigrationStatus.INDEXING
    result = engine.validate_structural(client, target_registry, manifest, target_config)
    assert result.passed, result.findings


@pytest.mark.asyncio
async def test_idempotent_rerun_does_not_duplicate_points(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    client = QdrantClient(":memory:")
    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)
    connector = _write_docs(tmp_path)
    target_registry = DocumentRegistry(tmp_path / "target_registry.db")
    manifest = engine.new_manifest(engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=2, expected_chunk_count=2,
    ))

    await _index(client, target_registry, connector, manifest, tmp_path / "m.json", target_config)
    count_after_first = client.count(manifest.target_collection).count

    # Simulates a crash-then-rerun: same manifest, same isolated registry,
    # same target collection, run again.
    second_stats = await _index(
        client, target_registry, connector, manifest, tmp_path / "m.json", target_config
    )

    assert second_stats.chunks_upserted == 0  # nothing re-embedded — already complete
    assert client.count(manifest.target_collection).count == count_after_first


@pytest.mark.asyncio
async def test_resume_after_partial_run_only_completes_remaining_work(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    client = QdrantClient(":memory:")
    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)
    target_registry = DocumentRegistry(tmp_path / "target_registry.db")
    manifest = engine.new_manifest(engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=1, expected_chunk_count=1,
    ))

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.\n")
    partial_connector = LocalFilesystemConnector(str(docs_dir))
    await _index(
        client, target_registry, partial_connector, manifest, tmp_path / "m.json", target_config
    )

    # "Crash recovery": a second document shows up (or was always there —
    # same code path) and the SAME manifest/registry/collection resumes.
    (docs_dir / "two.md").write_text("# Two\n\nContent about oranges.\n")
    full_connector = LocalFilesystemConnector(str(docs_dir))
    second_stats = await _index(
        client, target_registry, full_connector, manifest, tmp_path / "m.json", target_config
    )

    assert second_stats.files_processed == 1  # only the new document
    assert len(target_registry.list_documents()) == 2


# ------------------------------------------------------------- validation


@pytest.mark.asyncio
async def _indexed_migration(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=DIMENSION)
    client = QdrantClient(":memory:")
    target_config = _target_config(settings)
    fingerprint = build_pipeline_fingerprint(target_config)
    connector = _write_docs(tmp_path)
    target_registry = DocumentRegistry(tmp_path / "target_registry.db")
    manifest = engine.new_manifest(engine.MigrationPlan(
        no_migration_required=False, source_model="nomic-embed-text", source_dimension=768,
        source_fingerprint="src", source_collection="kb_chunks",
        target_model=target_config.ollama_model, target_dimension=DIMENSION,
        target_fingerprint=fingerprint.digest(),
        target_collection=collection_name_for(target_config, fingerprint),
        expected_document_count=2, expected_chunk_count=2,
    ))
    await _index(client, target_registry, connector, manifest, tmp_path / "m.json", target_config)
    return client, target_registry, manifest, target_config


@pytest.mark.asyncio
async def test_validate_structural_passes_for_a_correct_target(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)

    result = engine.validate_structural(client, target_registry, manifest, target_config)

    assert result.passed
    assert result.duplicate_points == 0


@pytest.mark.asyncio
async def test_validate_structural_fails_on_document_count_mismatch(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    manifest.expected_document_count = 99

    result = engine.validate_structural(client, target_registry, manifest, target_config)

    assert not result.passed
    assert any("document count" in f for f in result.findings)


@pytest.mark.asyncio
async def test_validate_structural_fails_on_chunk_count_mismatch(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    store = QdrantStore(
        client=client, collection_name=manifest.target_collection,
        dense_dimension=target_config.dimension,
    )
    doc = target_registry.list_documents()[0]
    point_ids = store.list_point_ids_for_version(
        doc.tenant_id, doc.source_type, doc.source_id, doc.content_hash
    )
    store.delete_points(list(point_ids))

    result = engine.validate_structural(client, target_registry, manifest, target_config)

    assert not result.passed


@pytest.mark.asyncio
async def test_validate_structural_fails_on_fingerprint_mismatch(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    manifest.target_fingerprint = "a-different-fingerprint"

    result = engine.validate_structural(client, target_registry, manifest, target_config)

    assert not result.passed
    assert any("pipeline_fingerprint" in f for f in result.findings)


@pytest.mark.asyncio
async def test_validate_structural_fails_when_target_collection_missing(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    manifest.target_collection = "does_not_exist"

    result = engine.validate_structural(client, target_registry, manifest, target_config)

    assert not result.passed
    assert any("does not exist" in f for f in result.findings)


# -------------------------------------------------------------- activation


@pytest.mark.asyncio
async def test_activate_atomically_switches_the_alias(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    manifest.status = MigrationStatus.READY_TO_SWITCH

    await engine.activate(manifest, client, registry, settings, target_config)

    from app.migration.aliasing import get_alias_target

    assert get_alias_target(client, "kb_active") == manifest.target_collection
    assert manifest.status == MigrationStatus.ACTIVE


@pytest.mark.asyncio
async def test_activate_records_active_and_previous_state(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")

    await engine.activate(manifest, client, registry, settings, target_config)

    status = engine.get_status(client, registry, settings)
    assert status.active_state["collection"] == manifest.target_collection
    assert status.rollback_available is True
    assert status.previous_state["collection"] == manifest.source_collection


@pytest.mark.asyncio
async def test_activate_with_failing_smoke_check_rolls_back_automatically(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    # Pre-existing source collection, so there's something to roll back to.
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"

    async def failing_smoke():
        class _R:
            passed = False

        return _R()

    with pytest.raises(engine.MigrationActivationFailedError):
        await engine.activate(
            manifest, client, registry, settings, target_config, smoke_check=failing_smoke
        )

    from app.migration.aliasing import get_alias_target

    assert get_alias_target(client, "kb_active") == "kb_chunks"
    assert manifest.status == MigrationStatus.FAILED


# --------------------------------------------------------------- rollback


@pytest.mark.asyncio
async def test_rollback_raises_when_nothing_to_roll_back_to(tmp_path):
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    settings = Settings()

    with pytest.raises(engine.NoRollbackTargetError):
        engine.rollback(client, registry, settings)


@pytest.mark.asyncio
async def test_rollback_points_alias_back_to_previous_collection(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"
    await engine.activate(manifest, client, registry, settings, target_config)

    previous = engine.rollback(client, registry, settings)

    from app.migration.aliasing import get_alias_target

    assert previous.collection == "kb_chunks"
    assert get_alias_target(client, "kb_active") == "kb_chunks"


@pytest.mark.asyncio
async def test_rollback_preserves_the_target_collection(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"
    await engine.activate(manifest, client, registry, settings, target_config)

    engine.rollback(client, registry, settings)

    assert client.collection_exists(manifest.target_collection)


@pytest.mark.asyncio
async def test_rollback_twice_is_symmetric_reactivation(tmp_path):
    """Section 31's rollback drill: Qwen active -> rollback -> Nomic
    active -> rollback again (= re-activate Qwen) -> back to the
    post-activation state, both collections intact throughout.
    """
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"
    await engine.activate(manifest, client, registry, settings, target_config)

    engine.rollback(client, registry, settings)
    engine.rollback(client, registry, settings)

    from app.migration.aliasing import get_alias_target

    assert get_alias_target(client, "kb_active") == manifest.target_collection


# --------------------------------------------------------------- cleanup


@pytest.mark.asyncio
async def test_cleanup_old_collection_refuses_to_delete_the_active_one(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"
    await engine.activate(manifest, client, registry, settings, target_config)
    # Force the previous slot to (incorrectly) point at the currently
    # active collection, to prove cleanup refuses regardless.
    registry.set_metadata(
        engine.PREVIOUS_STATE_KEY,
        json.dumps({
            "embedding_model_key": "qwen3-4b", "output_dimension": DIMENSION,
            "fingerprint_digest": manifest.target_fingerprint,
            "collection": manifest.target_collection, "migration_id": manifest.migration_id,
        }),
    )

    with pytest.raises(ValueError, match="ACTIVE"):
        engine.cleanup_old_collection(client, registry, settings)


@pytest.mark.asyncio
async def test_cleanup_old_collection_deletes_previous_and_clears_rollback(tmp_path):
    client, target_registry, manifest, target_config = await _indexed_migration(tmp_path)
    settings = Settings(qdrant_active_alias="kb_active")
    registry = DocumentRegistry(tmp_path / "prod_registry.db")
    from qdrant_client.http import models as qmodels

    client.create_collection(
        "kb_chunks", vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
    )
    manifest.source_collection = "kb_chunks"
    await engine.activate(manifest, client, registry, settings, target_config)

    deleted = engine.cleanup_old_collection(client, registry, settings)

    assert deleted == "kb_chunks"
    assert not client.collection_exists("kb_chunks")
    status = engine.get_status(client, registry, settings)
    assert status.rollback_available is False


# ------------------------------------------------------------- idempotent manifest


def test_load_or_create_manifest_resumes_a_matching_in_progress_manifest(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=1024)
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    plan = engine.plan_migration(client, registry, settings)
    manifest_path = tmp_path / "m.json"
    first = engine.load_or_create_manifest(plan, manifest_path)
    first.status = MigrationStatus.INDEXING
    first.save(manifest_path)

    second = engine.load_or_create_manifest(plan, manifest_path)

    assert second.migration_id == first.migration_id


def test_load_or_create_manifest_starts_fresh_after_a_terminal_status(tmp_path):
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=1024)
    client = QdrantClient(":memory:")
    registry = DocumentRegistry(tmp_path / "registry.db")
    plan = engine.plan_migration(client, registry, settings)
    manifest_path = tmp_path / "m.json"
    first = engine.load_or_create_manifest(plan, manifest_path)
    first.status = MigrationStatus.FAILED
    first.save(manifest_path)

    second = engine.load_or_create_manifest(plan, manifest_path)

    assert second.migration_id != first.migration_id
