"""Sprint 22: the production embedding migration engine — turns the
Sprint 18-21 embedding-model DECISION into a safe, validated, rollback-
tested Qdrant index lifecycle operation.

Architecture (blue/green via Qdrant alias indirection — see
app/migration/aliasing.py):

    old serving index (still serving traffic)
            |
    build new TARGET collection (isolated, own registry — see below)
            |
    structural validation  (counts, dimension, schema, no duplicates)
            |
    retrieval quality gate (frozen Sprint 21 golden set vs. baseline)
            |
    atomic alias activation (kb_active -> target, one Qdrant call)
            |
    post-switch smoke verification
            |
    rollback capability (kb_active -> previous, same atomic mechanism)

Indexing reuses app/ingestion/ingest.py::ingest_connector UNCHANGED — no
second ingestion implementation — but points it at an ISOLATED SQLite
registry file (one per migration_id, under work_dir), never the shared
production registry.db. This is deliberate, not incidental:
ingest_connector's own registry.upsert_document() call would otherwise
overwrite the PRODUCTION registry's pipeline_fingerprint/chunk_count for
every document as soon as the (still unvalidated, not yet activated)
target collection is indexed — silently telling production reconciliation
logic (app/ingestion/ingest.py's "index_present_and_complete" check) that
the NEW fingerprint is already correct while production is still SERVING
the OLD collection. An isolated, empty-at-first registry means every
document looks "new" to ingest_connector on the first indexing pass
(a real, correct full re-embed under the target model) and "already
present, matching fingerprint" on any RE-RUN against the same target
collection (real idempotency/resume — Sprint 22 sections 9-10 — for
free, from ingest_connector's own existing incremental-sync semantics).

Production's registry/alias state is only ever touched in activate()/
rollback(), and only via DocumentRegistry.set_metadata (Sprint 22
extends the SAME registry_metadata table Sprint 17.1 already uses for
index_schema_version).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from opentelemetry import trace
from qdrant_client import QdrantClient

from app.connectors.base import Connector
from app.ingestion.fingerprint import PipelineFingerprint, build_pipeline_fingerprint
from app.ingestion.ingest import EmbedFn, IngestStats, SparseEncoderProtocol, ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import (
    EmbeddingModelConfig,
    active_embedding_config,
    get_embedding_model_config,
    nomic_config,
)
from app.migration.aliasing import (
    atomic_switch_alias,
    get_alias_target,
    resolve_active_collection_name,
)
from app.migration.models import MigrationManifest, MigrationStatus, utcnow_iso
from app.migration.naming import collection_name_for
from app.registry.store import DocumentRegistry
from app.shared.config import Settings
from app.shared.tracing import get_tracer

logger = logging.getLogger(__name__)

ACTIVE_STATE_KEY = "migration_active_state"
PREVIOUS_STATE_KEY = "migration_previous_state"


class NoRollbackTargetError(Exception):
    """Raised by rollback() when there is no previous state recorded —
    either no migration has ever activated, or a previous rollback
    already consumed the only recorded previous state without a
    subsequent activation to re-establish one."""


class MigrationActivationFailedError(Exception):
    """Raised by activate() when post-switch smoke verification fails —
    the alias has already been switched back to the pre-switch
    collection (automatic rollback, Sprint 22 section 17) before this is
    raised, so production is never left pointed at an unverified target.
    """


class StructuralValidationError(Exception):
    """Raised by validate_structural() findings being non-empty and the
    caller choosing to treat that as fatal (the migrate_embedding_index
    CLI's `validate` command does; `migrate` does not raise directly —
    it records the failure in the manifest and stops before activation).
    """


@dataclass(frozen=True)
class ActiveState:
    embedding_model_key: str
    output_dimension: int | None
    fingerprint_digest: str
    collection: str
    migration_id: str | None

    def as_dict(self) -> dict:
        return {
            "embedding_model_key": self.embedding_model_key,
            "output_dimension": self.output_dimension,
            "fingerprint_digest": self.fingerprint_digest,
            "collection": self.collection,
            "migration_id": self.migration_id,
        }


def _load_state(registry: DocumentRegistry, key: str) -> ActiveState | None:
    raw = registry.get_metadata(key)
    if raw is None:
        return None
    return ActiveState(**json.loads(raw))


def _save_state(registry: DocumentRegistry, key: str, state: ActiveState) -> None:
    registry.set_metadata(key, json.dumps(state.as_dict()))


def resolve_source_state(
    qdrant_client: QdrantClient, registry: DocumentRegistry, settings: Settings
) -> tuple[EmbeddingModelConfig, str, str]:
    """What's ACTUALLY serving production right now — (display config,
    fingerprint DIGEST, collection). If a Sprint 22 migration has
    activated at least once, the fingerprint digest is the one RECORDED
    at that activation (state.fingerprint_digest), not recomputed from
    current settings — recomputing would use whatever
    qwen3_query_instruction/etc. happens to be configured NOW, which
    could have changed since activation and would then make an actual
    instruction drift invisible (source and target would both compute
    the same "current" instruction and appear to match). The display
    config (model/dimension) is still reconstructed from settings for
    human-readable output only.

    Otherwise this is a deployment that predates Sprint 22 entirely —
    the only embedding config this codebase has ever hardcoded as its
    production default is nomic-embed-text@768
    (app/ingestion/ingest.py::SEARCH_DOCUMENT_PREFIX,
    app/retrieval/search.py::SEARCH_QUERY_PREFIX, app/ingestion/
    qdrant_store.py::EMBEDDING_DIM), so that's the honest fallback
    assumption — recomputed fresh from current settings since there is
    no earlier recorded digest to defer to.
    """
    state = _load_state(registry, ACTIVE_STATE_KEY)
    if state is not None:
        config = get_embedding_model_config(
            state.embedding_model_key, settings, output_dimension=state.output_dimension
        )
        return config, state.fingerprint_digest, state.collection

    config = nomic_config(settings)
    fingerprint_digest = build_pipeline_fingerprint(config).digest()
    collection = resolve_active_collection_name(qdrant_client, settings)
    return config, fingerprint_digest, collection


@dataclass(frozen=True)
class MigrationPlan:
    no_migration_required: bool
    source_model: str
    source_dimension: int
    source_fingerprint: str
    source_collection: str
    target_model: str
    target_dimension: int
    target_fingerprint: str
    target_collection: str
    expected_document_count: int
    expected_chunk_count: int

    def as_dict(self) -> dict:
        return {
            "no_migration_required": self.no_migration_required,
            "source": {
                "model": self.source_model,
                "dimension": self.source_dimension,
                "fingerprint": self.source_fingerprint,
                "collection": self.source_collection,
            },
            "target": {
                "model": self.target_model,
                "dimension": self.target_dimension,
                "fingerprint": self.target_fingerprint,
                "collection": self.target_collection,
            },
            "expected_document_count": self.expected_document_count,
            "expected_chunk_count": self.expected_chunk_count,
        }


def plan_migration(
    qdrant_client: QdrantClient, registry: DocumentRegistry, settings: Settings
) -> MigrationPlan:
    source_config, source_fingerprint_digest, source_collection = resolve_source_state(
        qdrant_client, registry, settings
    )
    target_config = active_embedding_config(settings)
    target_fp = build_pipeline_fingerprint(target_config)
    target_collection = collection_name_for(target_config, target_fp)

    # Expected counts are estimated from what's currently recorded as
    # successfully indexed (the corpus indexing will re-embed) — a live
    # connector re-scan happens for real during run_indexing() itself;
    # this is a planning-time ESTIMATE, not a guarantee, and is labeled
    # as such in the CLI output.
    all_docs = registry.list_documents()
    expected_document_count = len(all_docs)
    expected_chunk_count = sum(d.chunk_count or 0 for d in all_docs)

    return MigrationPlan(
        no_migration_required=source_fingerprint_digest == target_fp.digest(),
        source_model=source_config.ollama_model,
        source_dimension=source_config.dimension,
        source_fingerprint=source_fingerprint_digest,
        source_collection=source_collection,
        target_model=target_config.ollama_model,
        target_dimension=target_config.dimension,
        target_fingerprint=target_fp.digest(),
        target_collection=target_collection,
        expected_document_count=expected_document_count,
        expected_chunk_count=expected_chunk_count,
    )


def load_or_create_manifest(plan: MigrationPlan, manifest_path: str | Path) -> MigrationManifest:
    """Resume-aware: if a manifest already exists at manifest_path AND
    targets the exact same fingerprint AND hasn't reached a terminal
    state (ACTIVE/ROLLED_BACK/FAILED), it's reused as-is — this is what
    makes re-running `migrate` after a crash/Ctrl+C continue the SAME
    migration_id/target_collection instead of starting a brand new one
    (Sprint 22 sections 9-10). A terminal-state or fingerprint-mismatched
    manifest is never silently reused — a fresh one is created instead.
    """
    path = Path(manifest_path)
    if path.exists():
        existing = MigrationManifest.load(path)
        resumable_statuses = {
            MigrationStatus.PLANNED,
            MigrationStatus.INDEXING,
            MigrationStatus.VALIDATING,
            MigrationStatus.READY_TO_SWITCH,
        }
        fingerprint_matches = existing.target_fingerprint == plan.target_fingerprint
        if fingerprint_matches and existing.status in resumable_statuses:
            return existing
    return new_manifest(plan)


def new_manifest(plan: MigrationPlan) -> MigrationManifest:
    return MigrationManifest(
        migration_id=f"mig-{uuid.uuid4().hex[:12]}",
        started_at=utcnow_iso(),
        source_collection=plan.source_collection,
        source_fingerprint=plan.source_fingerprint,
        target_collection=plan.target_collection,
        target_fingerprint=plan.target_fingerprint,
        target_model=plan.target_model,
        target_dimension=plan.target_dimension,
        expected_document_count=plan.expected_document_count,
        expected_chunk_count=plan.expected_chunk_count,
    )


async def run_indexing(
    manifest: MigrationManifest,
    qdrant_client: QdrantClient,
    target_registry: DocumentRegistry,
    connectors: dict[str, Connector],
    embed_fn: EmbedFn,
    sparse_encoder: SparseEncoderProtocol,
    target_config: EmbeddingModelConfig,
    target_fingerprint: PipelineFingerprint,
    manifest_path: str | Path,
    embedding_concurrency: int = 4,
    tracer: trace.Tracer | None = None,
) -> IngestStats:
    """Indexes every connector's current documents into
    manifest.target_collection via the UNCHANGED ingest_connector — see
    module docstring for why target_registry must be isolated. Safe to
    call again after a crash/Ctrl+C: ingest_connector's own reconciliation
    (count_for_document_version vs. the isolated registry's chunk_count)
    means already-completed documents are skipped, not re-embedded.
    """
    tracer = tracer or get_tracer(__name__)
    manifest.status = MigrationStatus.INDEXING
    manifest.touch()
    manifest.save(manifest_path)

    store = QdrantStore(
        client=qdrant_client, collection_name=manifest.target_collection,
        dense_dimension=target_config.dimension,
    )

    total = IngestStats(files_processed=0, chunks_upserted=0)
    with tracer.start_as_current_span("embedding_migration.index") as span:
        span.set_attribute("migration.id", manifest.migration_id)
        span.set_attribute("migration.target_collection", manifest.target_collection)
        for source_type, connector in connectors.items():
            stats = await ingest_connector(
                connector, store, target_registry, embed_fn, sparse_encoder,
                embedding_concurrency=embedding_concurrency, tracer=tracer,
                pipeline_fingerprint=target_fingerprint,
            )
            total.files_processed += stats.files_processed
            total.chunks_upserted += stats.chunks_upserted
            manifest.documents_completed = sum(
                1 for _ in target_registry.list_documents()
            )
            manifest.chunks_completed += stats.chunks_upserted
            manifest.touch()
            manifest.save(manifest_path)
        span.set_attribute("migration.documents_completed", manifest.documents_completed)
        span.set_attribute("migration.chunks_completed", manifest.chunks_completed)

    return total


@dataclass(frozen=True)
class StructuralValidationResult:
    passed: bool
    findings: list[str]
    document_count: int
    chunk_count: int
    dense_dimension: int | None
    duplicate_points: int

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": self.findings,
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "dense_dimension": self.dense_dimension,
            "duplicate_points": self.duplicate_points,
        }


def validate_structural(
    qdrant_client: QdrantClient,
    target_registry: DocumentRegistry,
    manifest: MigrationManifest,
    target_config: EmbeddingModelConfig,
) -> StructuralValidationResult:
    findings: list[str] = []

    if not qdrant_client.collection_exists(manifest.target_collection):
        return StructuralValidationResult(
            passed=False,
            findings=[f"target collection {manifest.target_collection!r} does not exist"],
            document_count=0,
            chunk_count=0,
            dense_dimension=None,
            duplicate_points=0,
        )

    store = QdrantStore(
        client=qdrant_client, collection_name=manifest.target_collection,
        dense_dimension=target_config.dimension,
    )

    docs = target_registry.list_documents()
    document_count = len(docs)
    if document_count != manifest.expected_document_count:
        findings.append(
            f"document count {document_count} != expected {manifest.expected_document_count}"
        )

    actual_chunk_total = 0
    duplicate_points = 0
    for doc in docs:
        expected = doc.chunk_count or 0
        actual = store.count_for_document_version(
            doc.tenant_id, doc.source_type, doc.source_id, doc.content_hash
        )
        actual_chunk_total += actual
        if actual != expected:
            findings.append(
                f"{doc.source_type}:{doc.source_id} has {actual} points, expected {expected}"
            )
        if doc.pipeline_fingerprint != manifest.target_fingerprint:
            findings.append(
                f"{doc.source_type}:{doc.source_id} pipeline_fingerprint "
                f"{doc.pipeline_fingerprint!r} != target {manifest.target_fingerprint!r}"
            )

    total_points = store.count()
    if total_points != actual_chunk_total:
        duplicate_points = total_points - actual_chunk_total
        findings.append(
            f"collection has {total_points} total points but only {actual_chunk_total} are "
            f"accounted for by known documents — {duplicate_points} unexpected/duplicate point(s)"
        )

    info = qdrant_client.get_collection(manifest.target_collection)
    dense_vectors = info.config.params.vectors or {}
    has_dense = isinstance(dense_vectors, dict) and "dense" in dense_vectors
    dense_dimension = dense_vectors["dense"].size if has_dense else None
    if dense_dimension != target_config.dimension:
        findings.append(
            f"collection dense dimension {dense_dimension} != target {target_config.dimension}"
        )

    return StructuralValidationResult(
        passed=not findings,
        findings=findings,
        document_count=document_count,
        chunk_count=actual_chunk_total,
        dense_dimension=dense_dimension,
        duplicate_points=duplicate_points,
    )


async def activate(
    manifest: MigrationManifest,
    qdrant_client: QdrantClient,
    registry: DocumentRegistry,
    settings: Settings,
    target_config: EmbeddingModelConfig,
    smoke_check: Callable[[], Awaitable] | None = None,
    tracer: trace.Tracer | None = None,
) -> None:
    """Atomically repoints settings.qdrant_active_alias at
    manifest.target_collection, runs an optional post-switch smoke
    check, and records the new/previous active state — see module
    docstring and app/migration/aliasing.py::atomic_switch_alias.

    smoke_check, if given, is a zero-arg ASYNC callable returning
    something truthy/falsy (typically a
    app/migration/quality_gate.py::SmokeResult) — kept as a plain
    injected callable rather than importing quality_gate directly, so
    this module (and its tests) never need a real Ollama/Qdrant just to
    exercise the alias-switch/rollback-on-failure control flow.
    """
    tracer = tracer or get_tracer(__name__)
    with tracer.start_as_current_span("embedding_migration.activate") as span:
        span.set_attribute("migration.id", manifest.migration_id)
        previous_state = _load_state(registry, ACTIVE_STATE_KEY)
        previous_collection = (
            previous_state.collection if previous_state is not None else manifest.source_collection
        )

        manifest.status = MigrationStatus.SWITCHING
        manifest.touch()

        alias = settings.qdrant_active_alias
        atomic_switch_alias(qdrant_client, alias, manifest.target_collection)
        span.set_attribute("migration.switched_to", manifest.target_collection)

        if smoke_check is not None:
            result = await smoke_check()
            passed = getattr(result, "passed", bool(result))
            span.set_attribute("migration.post_switch_smoke_passed", bool(passed))
            if not passed:
                atomic_switch_alias(qdrant_client, alias, previous_collection)
                manifest.status = MigrationStatus.FAILED
                manifest.error = f"post-switch smoke failed, rolled back to {previous_collection}"
                manifest.notes.append(manifest.error)
                manifest.touch()
                logger.error(
                    "post-switch smoke failed for migration %s — automatically rolled back "
                    "alias %r to %r",
                    manifest.migration_id, settings.qdrant_active_alias, previous_collection,
                )
                raise MigrationActivationFailedError(manifest.error)

        new_state = ActiveState(
            embedding_model_key=settings.embedding_model_key,
            output_dimension=settings.embedding_output_dimension,
            fingerprint_digest=manifest.target_fingerprint,
            collection=manifest.target_collection,
            migration_id=manifest.migration_id,
        )
        old_state = previous_state or ActiveState(
            embedding_model_key="nomic",
            output_dimension=None,
            fingerprint_digest=manifest.source_fingerprint,
            collection=previous_collection,
            migration_id=None,
        )
        _save_state(registry, PREVIOUS_STATE_KEY, old_state)
        _save_state(registry, ACTIVE_STATE_KEY, new_state)

        manifest.status = MigrationStatus.ACTIVE
        manifest.activated_at = utcnow_iso()
        manifest.touch()


def rollback(
    qdrant_client: QdrantClient, registry: DocumentRegistry, settings: Settings
) -> ActiveState:
    """Repoints the alias back to whatever's recorded as PREVIOUS_STATE_KEY
    and SWAPS the two state slots (previous <-> active) — this is what
    makes rollback symmetric: running rollback() again after a rollback
    re-activates the collection that was rolled back FROM, without ever
    deleting either collection (Sprint 22 sections 18-19: old index
    retention, no automatic cleanup).
    """
    previous = _load_state(registry, PREVIOUS_STATE_KEY)
    if previous is None:
        raise NoRollbackTargetError(
            "No previous active state recorded — either no migration has ever activated, or "
            "there is nothing left to roll back to."
        )
    current = _load_state(registry, ACTIVE_STATE_KEY)

    atomic_switch_alias(qdrant_client, settings.qdrant_active_alias, previous.collection)

    _save_state(registry, ACTIVE_STATE_KEY, previous)
    if current is not None:
        _save_state(registry, PREVIOUS_STATE_KEY, current)
    return previous


@dataclass(frozen=True)
class MigrationStatusReport:
    active_collection: str | None
    active_alias: str
    active_state: dict | None
    previous_state: dict | None
    rollback_available: bool

    def as_dict(self) -> dict:
        return {
            "active_alias": self.active_alias,
            "active_collection": self.active_collection,
            "active_state": self.active_state,
            "previous_state": self.previous_state,
            "rollback_available": self.rollback_available,
        }


def get_status(
    qdrant_client: QdrantClient, registry: DocumentRegistry, settings: Settings
) -> MigrationStatusReport:
    active_state = _load_state(registry, ACTIVE_STATE_KEY)
    previous_state = _load_state(registry, PREVIOUS_STATE_KEY)
    alias_target = get_alias_target(qdrant_client, settings.qdrant_active_alias)
    active_collection = alias_target or (
        active_state.collection if active_state else settings.qdrant_collection_name
    )
    return MigrationStatusReport(
        active_collection=active_collection,
        active_alias=settings.qdrant_active_alias,
        active_state=active_state.as_dict() if active_state else None,
        previous_state=previous_state.as_dict() if previous_state else None,
        rollback_available=previous_state is not None,
    )


def cleanup_old_collection(
    qdrant_client: QdrantClient, registry: DocumentRegistry, settings: Settings
) -> str:
    """Explicit, human-invoked, NEVER auto-called (Sprint 22 section 19)
    — deletes the collection recorded as PREVIOUS_STATE_KEY and clears
    that slot (rollback is no longer possible after this). Refuses if
    that collection is somehow still the one the active alias points to
    (a caller ran this before ever activating, or state got corrupted) —
    cleanup must never delete a collection that's currently serving.
    """
    previous = _load_state(registry, PREVIOUS_STATE_KEY)
    if previous is None:
        raise NoRollbackTargetError("No previous collection recorded — nothing to clean up.")
    active_target = get_alias_target(qdrant_client, settings.qdrant_active_alias)
    if active_target == previous.collection:
        raise ValueError(
            f"Refusing to delete {previous.collection!r} — it is still the ACTIVE collection."
        )
    qdrant_client.delete_collection(previous.collection)
    registry.delete_metadata(PREVIOUS_STATE_KEY)
    return previous.collection
