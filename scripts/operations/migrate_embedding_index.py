"""Sprint 22: human-operated CLI for the production embedding migration —
turns the Sprint 18-21 ADOPT_QWEN3_4B_1024 decision into a real,
validated, rollback-tested Qdrant index lifecycle operation. See
docs/embedding-migration.md for the full operator walkthrough.

    python -m scripts.operations.migrate_embedding_index plan
    python -m scripts.operations.migrate_embedding_index migrate [--dry-run]
    python -m scripts.operations.migrate_embedding_index validate
    python -m scripts.operations.migrate_embedding_index activate
    python -m scripts.operations.migrate_embedding_index rollback
    python -m scripts.operations.migrate_embedding_index status
    python -m scripts.operations.migrate_embedding_index cleanup-old

Every command reads app.shared.config.settings (real .env) and talks to
the REAL Qdrant/Ollama configured there — there is no mock mode. `plan`
and `status` are read-only. `migrate` only ever writes to an isolated
target collection + isolated registry file (never touches the currently
active collection/alias). `activate`/`rollback` are the only commands
that ever change what's actually serving production traffic, and both
go through the same atomic alias mechanism
(app/migration/aliasing.py::atomic_switch_alias).
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient

from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.migration import embedding_migration as engine
from app.migration.models import MigrationStatus
from app.migration.naming import sanitize_label
from app.migration.quality_gate import run_quality_gate, run_smoke
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseEncoder
from app.shared.config import Settings, settings
from app.wiring import build_connectors

OUTPUT_DIR = Path("artifacts/embedding-migration-sprint22")
WORK_DIR = OUTPUT_DIR / "work"
MANIFEST_PATH = OUTPUT_DIR / "migration-result.json"
PLAN_PATH = OUTPUT_DIR / "plan.json"
VALIDATION_PATH = OUTPUT_DIR / "validation.json"

GOLDEN_SET_PATH = "tests/fixtures/embedding_benchmark_golden_v2.json"
SMOKE_SAMPLE_SIZE = 16


def _load_golden_questions() -> list[dict]:
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        return json.load(f)


SPRINT21_STABILITY_PATH = Path("artifacts/embedding-benchmark-sprint21/stability.json")


def _load_sprint21_baseline() -> dict | None:
    """Sprint 21's own accepted numbers for qwen3-4b@1024, read straight
    from its real artifact — never re-typed/hardcoded here, so a change
    to that artifact is the only way this baseline can change.

    Sprint 21's run_to_run_distributions (stability.json) only tracked
    cross_lingual_recall_at_5/cross_lingual_mrr/ndcg_at_5 per config (its
    own primary metric was cross-lingual recall@5) — it never recorded an
    absolute mono-lingual recall@5 figure per config, only the paired
    delta between the two configs (non_inferiority.json). Rather than
    reverse-engineer an approximate absolute number from that delta, this
    honestly returns an EMPTY mono_lingual baseline — the quality gate
    then skips the mono-lingual comparison instead of comparing against a
    fabricated number. See docs/embedding-migration.md's known
    limitations section.

    Returns None (not a fabricated baseline) if the file doesn't exist —
    callers must treat a missing baseline as a real limitation.
    """
    if not SPRINT21_STABILITY_PATH.exists():
        return None
    data = json.loads(SPRINT21_STABILITY_PATH.read_text())
    distributions = data.get("run_to_run_distributions", {}).get("qwen3-4b@1024")
    if distributions is None:
        return None
    return {
        "cross_lingual": {
            "recall_at_5": distributions.get("cross_lingual_recall_at_5", {}).get("mean"),
            "mrr": distributions.get("cross_lingual_mrr", {}).get("mean"),
        },
        "mono_lingual": {},
    }


def _registry_path_for(migration_id: str) -> Path:
    return WORK_DIR / f"registry_{sanitize_label(migration_id)}.db"


def _print_plan(plan: engine.MigrationPlan) -> None:
    print("Current:")
    print(f"  model={plan.source_model}")
    print(f"  dimension={plan.source_dimension}")
    print(f"  collection={plan.source_collection}")
    print(f"  fingerprint={plan.source_fingerprint}")
    print()
    print("Target:")
    print(f"  model={plan.target_model}")
    print(f"  dimension={plan.target_dimension}")
    print(f"  collection={plan.target_collection}")
    print(f"  fingerprint={plan.target_fingerprint}")
    print()
    print(f"Documents (currently tracked): {plan.expected_document_count}")
    print(f"Expected chunks (currently tracked): {plan.expected_chunk_count}")
    print()
    if plan.no_migration_required:
        print("Action:")
        print("  NO MIGRATION REQUIRED — source and target fingerprints already match.")
    else:
        print("Action:")
        print("  full re-index required")


def cmd_plan(settings_obj: Settings) -> int:
    client = QdrantClient(url=settings_obj.qdrant_url)
    registry = DocumentRegistry(settings_obj.registry_db_path)
    plan = engine.plan_migration(client, registry, settings_obj)
    _print_plan(plan)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(plan.as_dict(), indent=2))
    return 0


async def cmd_migrate(settings_obj: Settings, dry_run: bool) -> int:
    client = QdrantClient(url=settings_obj.qdrant_url)
    prod_registry = DocumentRegistry(settings_obj.registry_db_path)
    plan = engine.plan_migration(client, prod_registry, settings_obj)
    _print_plan(plan)

    if plan.no_migration_required:
        return 0

    manifest = engine.load_or_create_manifest(plan, MANIFEST_PATH)
    print(f"\nmigration_id={manifest.migration_id} status={manifest.status.value}")

    if dry_run:
        print("\n--dry-run: no indexing performed.")
        manifest.save(MANIFEST_PATH)
        return 0

    target_config = active_embedding_config(settings_obj)
    target_fingerprint = build_pipeline_fingerprint(target_config)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    target_registry = DocumentRegistry(_registry_path_for(manifest.migration_id))
    connectors = build_connectors(settings_obj)
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=target_config.ollama_model, prefix=target_config.document_prefix(),
            dimensions=target_config.output_dimension,
        )

    start = time.perf_counter()
    try:
        stats = await engine.run_indexing(
            manifest, client, target_registry, connectors, embed_fn, sparse_encoder,
            target_config, target_fingerprint, MANIFEST_PATH,
            embedding_concurrency=settings_obj.embedding_concurrency,
        )
        elapsed = time.perf_counter() - start
        print(
            f"\n[{manifest.documents_completed}/{plan.expected_document_count} documents] "
            f"[{manifest.chunks_completed} chunks] elapsed={elapsed:.1f}s"
        )
        print(f"files_processed={stats.files_processed} chunks_upserted={stats.chunks_upserted}")
        manifest.status = MigrationStatus.VALIDATING
        manifest.touch()
        manifest.save(MANIFEST_PATH)
        print(f"\nstatus={manifest.status.value} — run `validate` next.")
        return 0
    except Exception as exc:
        manifest.status = MigrationStatus.FAILED
        manifest.error = str(exc)
        manifest.touch()
        manifest.save(MANIFEST_PATH)
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise
    finally:
        await ollama.aclose()


async def cmd_validate(settings_obj: Settings) -> int:
    if not MANIFEST_PATH.exists():
        print("No migration in progress — run `migrate` first.", file=sys.stderr)
        return 1
    from app.migration.models import MigrationManifest

    manifest = MigrationManifest.load(MANIFEST_PATH)
    client = QdrantClient(url=settings_obj.qdrant_url)
    target_config = active_embedding_config(settings_obj)
    target_registry = DocumentRegistry(_registry_path_for(manifest.migration_id))

    structural = engine.validate_structural(client, target_registry, manifest, target_config)
    print("Structural validation:")
    print(f"  passed={structural.passed}")
    for finding in structural.findings:
        print(f"  - {finding}")

    validation_payload = {"structural": structural.as_dict()}

    if not structural.passed:
        manifest.status = MigrationStatus.FAILED
        manifest.error = "structural validation failed"
        manifest.validation = validation_payload
        manifest.touch()
        manifest.save(MANIFEST_PATH)
        VALIDATION_PATH.write_text(json.dumps(validation_payload, indent=2))
        print("\nDO NOT ACTIVATE.")
        return 1

    golden_questions = _load_golden_questions()
    baseline = _load_sprint21_baseline()
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()
    try:
        quality = await run_quality_gate(
            golden_questions, ollama, sparse_encoder, client, manifest.target_collection,
            target_config, baseline,
        )
    finally:
        await ollama.aclose()

    print("\nRetrieval quality gate:")
    print(f"  cross Recall@5={quality.cross_recall_at_5:.4f} "
          f"(baseline={quality.baseline_cross_recall_at_5})")
    print(f"  cross MRR={quality.cross_mrr:.4f} (baseline={quality.baseline_cross_mrr})")
    print(f"  mono Recall@5={quality.mono_recall_at_5:.4f} "
          f"(baseline={quality.baseline_mono_recall_at_5})")
    print(f"  nDCG@5={quality.ndcg_at_5:.4f}")
    print(f"  passed={quality.passed}")
    for reason in quality.failure_reasons:
        print(f"  - {reason}")

    validation_payload["quality_gate"] = quality.as_dict()
    manifest.validation = validation_payload

    if not quality.passed:
        manifest.status = MigrationStatus.FAILED
        manifest.error = "quality gate failed"
        manifest.touch()
        manifest.save(MANIFEST_PATH)
        VALIDATION_PATH.write_text(json.dumps(validation_payload, indent=2))
        print("\nDO NOT ACTIVATE.")
        return 1

    manifest.status = MigrationStatus.READY_TO_SWITCH
    manifest.touch()
    manifest.save(MANIFEST_PATH)
    VALIDATION_PATH.write_text(json.dumps(validation_payload, indent=2))
    print(f"\nstatus={manifest.status.value} — run `activate` next.")
    return 0


async def cmd_activate(settings_obj: Settings) -> int:
    if not MANIFEST_PATH.exists():
        print("No migration in progress — run `migrate` and `validate` first.", file=sys.stderr)
        return 1
    from app.migration.models import MigrationManifest

    manifest = MigrationManifest.load(MANIFEST_PATH)
    if manifest.status != MigrationStatus.READY_TO_SWITCH:
        print(
            f"Refusing to activate — manifest status is {manifest.status.value}, expected "
            f"{MigrationStatus.READY_TO_SWITCH.value}. Run `validate` first.",
            file=sys.stderr,
        )
        return 1

    client = QdrantClient(url=settings_obj.qdrant_url)
    registry = DocumentRegistry(settings_obj.registry_db_path)
    target_config = active_embedding_config(settings_obj)
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()
    smoke_questions = _load_golden_questions()[:SMOKE_SAMPLE_SIZE]

    async def smoke_check():
        return await run_smoke(
            smoke_questions, ollama, sparse_encoder, client, manifest.target_collection,
            target_config,
        )

    try:
        await engine.activate(manifest, client, registry, settings_obj, target_config, smoke_check)
        manifest.save(MANIFEST_PATH)
        print(f"ACTIVATED: {settings_obj.qdrant_active_alias} -> {manifest.target_collection}")
        return 0
    except engine.MigrationActivationFailedError as exc:
        manifest.save(MANIFEST_PATH)
        print(f"ACTIVATION FAILED, rolled back automatically: {exc}", file=sys.stderr)
        return 1
    finally:
        await ollama.aclose()


def cmd_rollback(settings_obj: Settings) -> int:
    client = QdrantClient(url=settings_obj.qdrant_url)
    registry = DocumentRegistry(settings_obj.registry_db_path)
    try:
        previous = engine.rollback(client, registry, settings_obj)
    except engine.NoRollbackTargetError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"ROLLED BACK: {settings_obj.qdrant_active_alias} -> {previous.collection}")
    return 0


def cmd_status(settings_obj: Settings) -> int:
    client = QdrantClient(url=settings_obj.qdrant_url)
    registry = DocumentRegistry(settings_obj.registry_db_path)
    report = engine.get_status(client, registry, settings_obj)
    print(json.dumps(report.as_dict(), indent=2))
    if MANIFEST_PATH.exists():
        from app.migration.models import MigrationManifest

        manifest = MigrationManifest.load(MANIFEST_PATH)
        print(f"\nLatest migration: {manifest.migration_id} status={manifest.status.value}")
    return 0


def cmd_cleanup_old(settings_obj: Settings) -> int:
    client = QdrantClient(url=settings_obj.qdrant_url)
    registry = DocumentRegistry(settings_obj.registry_db_path)
    try:
        deleted = engine.cleanup_old_collection(client, registry, settings_obj)
    except (engine.NoRollbackTargetError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Deleted old collection: {deleted}. Rollback is no longer available.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    migrate_parser = sub.add_parser("migrate")
    migrate_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("validate")
    sub.add_parser("activate")
    sub.add_parser("rollback")
    sub.add_parser("status")
    sub.add_parser("cleanup-old")
    return parser


async def main_async(args: argparse.Namespace) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.command == "plan":
        return cmd_plan(settings)
    if args.command == "migrate":
        return await cmd_migrate(settings, args.dry_run)
    if args.command == "validate":
        return await cmd_validate(settings)
    if args.command == "activate":
        return await cmd_activate(settings)
    if args.command == "rollback":
        return cmd_rollback(settings)
    if args.command == "status":
        return cmd_status(settings)
    if args.command == "cleanup-old":
        return cmd_cleanup_old(settings)
    raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
