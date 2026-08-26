"""Read-only aggregation endpoints for the RAG Operations
Console (frontend/).

Strictly aggregation over EXISTING domain logic — this module owns no
business rules of its own. Every endpoint is:

  * read-only (no mutation lives here — `/sync` remains the only
    mutation surface, with its own OPERATOR+ gate),
  * behind the same `get_current_user` boundary as every other
    authenticated endpoint, and
  * tenant-scoped wherever it touches tenant-owned data — these
    endpoints must not become a way to read across the ACL that
    app/retrieval/filters.py enforces for retrieval.

Nothing here fabricates a value. Where the platform genuinely doesn't
track something (a chunk count Qdrant was never asked for, an
evaluation artifact that isn't on disk), the response says so
explicitly (`null` / `available: false`) so the UI can render "—"
rather than a plausible-looking number.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.llm.embedding_models import active_embedding_config
from app.llm.provider import default_chat_model
from app.migration.embedding_migration import get_status as migration_status
from app.retrieval.sparse import MODEL_NAME as SPARSE_MODEL_NAME
from app.security.models import Role, UserContext

router = APIRouter(prefix="/ui", tags=["ui"])

# Real benchmark/migration artifacts, read server-side.
# The browser never touches the repo filesystem — it asks for this
# endpoint, and the server reads only these known, explicitly-listed
# paths (never a client-supplied one).
EVALUATION_ARTIFACT_ROOT = Path("artifacts")

# The embedding decision history the Evaluations page renders as a
# timeline. Each entry names the REAL artifact directory its numbers
# come from; an entry whose artifact is missing from disk is reported
# as unavailable rather than rendered from these hardcoded labels.
EMBEDDING_DECISION_TIMELINE = [
    {
        "sprint": 18,
        "title": "Nomic vs Qwen3-Embedding-4B",
        "question": "Does a larger multilingual model close the cross-lingual gap?",
        "artifact_dir": "embedding-benchmark",
    },
    {
        "sprint": 19,
        "title": "Size / dimension trade-off",
        "question": "Which Qwen3 size and output dimension is worth its cost?",
        "artifact_dir": "embedding-benchmark-sprint19",
    },
    {
        "sprint": 20,
        "title": "Stability & production decision",
        "question": "Is the measured gap real, or run-to-run noise?",
        "artifact_dir": "embedding-benchmark-sprint20",
    },
    {
        "sprint": 21,
        "title": "Non-inferiority decision",
        "question": "Is the smaller model non-inferior within a pre-committed margin?",
        "artifact_dir": "embedding-benchmark-sprint21",
    },
    {
        "sprint": 22,
        "title": "Production migration",
        "question": "Can the decision be migrated safely, with rollback?",
        "artifact_dir": "embedding-migration-sprint22",
    },
    {
        "sprint": 23,
        "title": "Tenant-aware retrieval security",
        "question": "Can a tenant ever retrieve another tenant's content?",
        "artifact_dir": "security-sprint23",
    },
    {
        "sprint": 25,
        "title": "Prompt injection resistance",
        "question": "Does authorized document content stay untrusted during generation?",
        "artifact_dir": "security-sprint25",
    },
    {
        "sprint": 27,
        "title": "Token-aware chunking",
        "question": "Does real tokenizer-aware chunking improve retrieval without wasting context?",
        "artifact_dir": "chunking-benchmark-sprint27",
    },
]


def _read_artifact(relative_path: str) -> dict | None:
    """Reads one known artifact JSON. Returns None (never raises) when
    the file is absent — a repo checkout without a benchmark run is a
    legitimate state the UI must render honestly, not an error.
    """
    path = EVALUATION_ARTIFACT_ROOT / relative_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _runtime_settings(request: Request):
    return request.app.state.settings


@router.get("/identity")
async def identity(
    request: Request, user: UserContext = Depends(get_current_user)
) -> dict:
    """Server-owned identity for the console header. The UI renders
    whatever this returns — it never derives tenant/role from anything
    it holds locally, and it can never send a tenant_id of its own
    choosing anywhere (see docs/security.md).
    """
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "roles": sorted(r.value for r in user.roles),
        "can_sync": user.has_role(Role.OPERATOR),
        "is_admin": user.has_role(Role.ADMIN),
        "auth_enabled": _runtime_settings(request).auth_enabled,
    }


def _active_index_payload(request: Request) -> dict:
    """Current migration/alias state, read through the same
    functions the migration CLI uses. `previous`/`rollback_available`
    come from the registry's recorded state, not from config.
    """
    settings = _runtime_settings(request)
    config = active_embedding_config(settings)
    chunking = settings.chunking_config()
    fingerprint = build_pipeline_fingerprint(config, chunking)

    payload = {
        "model": config.ollama_model,
        "model_key": config.key,
        "dimension": config.dimension,
        "output_dimension": config.output_dimension,
        "backend": config.backend,
        "fingerprint": fingerprint.digest(),
        "alias": settings.qdrant_active_alias,
        "active_collection": None,
        "previous": None,
        "rollback_available": False,
        "migration_id": None,
        "available": False,
        "chunking": chunking.as_dict(),
    }

    qdrant_client = getattr(request.app.state, "qdrant_client", None)
    registry = getattr(request.app.state, "registry", None)
    if qdrant_client is None or registry is None:
        return payload

    try:
        status = migration_status(qdrant_client, registry, settings)
    except Exception:  # noqa: BLE001 - Qdrant unreachable is a real, renderable state
        return payload

    payload["available"] = True
    payload["active_collection"] = status.active_collection
    payload["rollback_available"] = status.rollback_available
    if status.active_state:
        payload["migration_id"] = status.active_state.get("migration_id")
    if status.previous_state:
        payload["previous"] = {
            "model_key": status.previous_state.get("embedding_model_key"),
            "output_dimension": status.previous_state.get("output_dimension"),
            "collection": status.previous_state.get("collection"),
            "fingerprint": status.previous_state.get("fingerprint_digest"),
        }
    return payload


@router.get("/active-index")
async def active_index(request: Request, user: UserContext = Depends(get_current_user)) -> dict:
    return _active_index_payload(request)


@router.get("/overview")
async def overview(request: Request, user: UserContext = Depends(get_current_user)) -> dict:
    """Operational summary, tenant-scoped. `chunk_count` is summed from
    the registry's own per-document chunk_count — which is None for a
    document that has never been re-ingested since chunk tracking was
    introduced, so `chunk_count_complete` reports whether every document
    actually contributed a real number. The UI must not present a
    partial sum as a total.
    """
    registry = request.app.state.registry
    manager = request.app.state.sync_manager
    history = request.app.state.sync_history
    tenant_ids: dict[str, str] = getattr(request.app.state, "tenant_ids", {})

    documents = registry.list_documents(tenant_id=user.tenant_id)
    tracked = [d.chunk_count for d in documents if d.chunk_count is not None]

    owned_source_types = [
        source_type
        for source_type in manager.known_source_types
        if tenant_ids.get(source_type) == user.tenant_id
    ]

    sources = []
    for source_type in owned_source_types:
        docs = [d for d in documents if d.source_type == source_type]
        runs = history.list_runs(source_type=source_type, limit=1)
        last_run = runs[0] if runs else None
        sources.append(
            {
                "source_type": source_type,
                "document_count": len(docs),
                "is_running": manager.is_running(source_type),
                "last_sync_at": last_run.started_at.isoformat() if last_run else None,
                "last_sync_status": last_run.status if last_run else None,
            }
        )

    recent_runs = [
        {
            "id": run.id,
            "source_type": run.source_type,
            "status": run.status,
            "trigger": run.trigger,
            "started_at": run.started_at.isoformat(),
            "files_processed": run.files_processed,
            "chunks_upserted": run.chunks_upserted,
        }
        for source_type in owned_source_types
        for run in history.list_runs(source_type=source_type, limit=5)
    ]
    recent_runs.sort(key=lambda r: r["started_at"], reverse=True)

    return {
        "tenant_id": user.tenant_id,
        "document_count": len(documents),
        "chunk_count": sum(tracked) if tracked else None,
        "chunk_count_complete": len(tracked) == len(documents),
        "source_count": len(owned_source_types),
        "sources": sources,
        "recent_runs": recent_runs[:10],
        "active_index": _active_index_payload(request),
        "security": {
            "auth_enabled": _runtime_settings(request).auth_enabled,
            "tenant_isolation": True,
            "mandatory_acl": True,
            "tenant_id": user.tenant_id,
            "roles": sorted(r.value for r in user.roles),
        },
    }


@router.get("/documents")
async def documents(
    request: Request,
    source_type: str | None = None,
    user: UserContext = Depends(get_current_user),
) -> list[dict]:
    """Tenant-scoped document list. `tenant_id` is taken from the
    resolved UserContext — a caller cannot pass one, so this endpoint
    can never enumerate another tenant's documents.
    """
    registry = request.app.state.registry
    records = registry.list_documents(tenant_id=user.tenant_id, source_type=source_type)
    return [
        {
            "tenant_id": record.tenant_id,
            "source_type": record.source_type,
            "source_id": record.source_id,
            "content_hash": record.content_hash,
            "version": record.version,
            "status": record.status,
            "chunk_count": record.chunk_count,
            "pipeline_fingerprint": record.pipeline_fingerprint,
            "last_synced_at": record.last_synced_at.isoformat(),
        }
        for record in records
    ]


@router.get("/settings")
async def ui_settings(request: Request, user: UserContext = Depends(get_current_user)) -> dict:
    """Read-only view of the real active configuration. Deliberately no
    write counterpart — the browser must never be able to mutate
    server config (docs/security.md).
    """
    settings = _runtime_settings(request)
    return {
        "active_pipeline": _active_index_payload(request),
        "retrieval": {
            "rerank_candidate_k": settings.reranker_candidate_k,
            "rerank_top_n": settings.reranker_top_n,
            "reranker_enabled": settings.reranker_enabled,
            "reranker_backend": settings.reranker_backend,
            "sparse_model": SPARSE_MODEL_NAME,
            "reranker_model": settings.reranker_model if settings.reranker_enabled else None,
            "fusion": "RRF",
            "chunking": settings.chunking_config().as_dict(),
        },
        "authentication": {
            "enabled": settings.auth_enabled,
            "scheme": "bearer",
            "roles": [r.value for r in Role],
        },
        "security": {
            "prompt_policy_version": settings.active_prompt_version,
            "untrusted_context_enabled": settings.active_prompt_version == "v3",
            "validation_mode": settings.security_validation_mode,
        },
        "integrations": {
            "qdrant_url": settings.qdrant_url,
            "ollama_base_url": settings.ollama_base_url,
            "otel_endpoint": settings.otel_exporter_otlp_endpoint,
            "generation_provider": settings.generation_provider,
            "generation_model": default_chat_model(settings),
        },
    }


@router.get("/evaluations")
async def evaluations(user: UserContext = Depends(get_current_user)) -> dict:
    """Measured artifacts, read from disk server-side. An
    artifact that isn't present is reported `available: false` — never
    substituted with example numbers.
    """
    sprint21 = _read_artifact("embedding-benchmark-sprint21/stability.json")
    sprint22 = _read_artifact("embedding-migration-sprint22/migration-result.json")
    security = _read_artifact("security-sprint23/security-validation.json")
    prompt_injection = _read_artifact("security-sprint25/adversarial-results.json")
    reranker_benchmark = _read_artifact("reranker-benchmark-sprint26/results.json")
    chunking_benchmark = _read_artifact("chunking-benchmark-sprint27/results.json")

    baseline = None
    if sprint21:
        distributions = sprint21.get("run_to_run_distributions", {}).get("qwen3-4b@1024", {})
        if distributions:
            baseline = {
                "config": "qwen3-4b@1024",
                "source": "artifacts/embedding-benchmark-sprint21/stability.json",
                "metrics": [
                    {
                        "key": key,
                        "label": label,
                        "value": distributions.get(key, {}).get("mean"),
                        "stddev": distributions.get(key, {}).get("stddev"),
                        "runs": distributions.get(key, {}).get("n_runs"),
                    }
                    for key, label in (
                        ("cross_lingual_recall_at_5", "Cross-lingual Recall@5"),
                        ("cross_lingual_mrr", "Cross-lingual MRR"),
                        ("ndcg_at_5", "nDCG@5"),
                    )
                    if key in distributions
                ],
            }

    # The migration's own quality gate re-measured these against the
    # real production collection — a second, independent real number.
    migration_gate = None
    if sprint22 and sprint22.get("validation", {}).get("quality_gate"):
        gate = sprint22["validation"]["quality_gate"]
        migration_gate = {
            "passed": gate.get("passed"),
            "question_count": gate.get("question_count"),
            "dataset_fingerprint": gate.get("dataset_fingerprint"),
            "cross_recall_at_5": gate.get("cross_recall_at_5"),
            "cross_mrr": gate.get("cross_mrr"),
            "mono_recall_at_5": gate.get("mono_recall_at_5"),
            "ndcg_at_5": gate.get("ndcg_at_5"),
            "tolerance": gate.get("tolerance"),
        }

    timeline = []
    for entry in EMBEDDING_DECISION_TIMELINE:
        artifact_dir = EVALUATION_ARTIFACT_ROOT / entry["artifact_dir"]
        timeline.append({**entry, "available": artifact_dir.exists()})

    reranker_decision = None
    if reranker_benchmark:
        reranker_decision = {
            "source": "artifacts/reranker-benchmark-sprint26/results.json",
            "dataset": reranker_benchmark.get("dataset"),
            "question_count": reranker_benchmark.get("question_count"),
            "recommendation": reranker_benchmark.get("production_decision", {}).get(
                "recommendation", "NEED_MORE_DATA"
            ),
            "rule": reranker_benchmark.get("production_decision", {}).get("rule"),
            "configs": [
                {
                    "config": name,
                    "model": result.get("model"),
                    "overall": result.get("overall"),
                    "cross_lingual": result.get("cross_lingual"),
                    "mono_lingual": result.get("mono_lingual"),
                    "latency": result.get("latency"),
                    "rescue_drop": result.get("rescue_drop"),
                }
                for name, result in reranker_benchmark.get("results", {}).items()
            ],
            "available": True,
        }

    chunking_decision = None
    if chunking_benchmark:
        chunking_decision = {
            "source": "artifacts/chunking-benchmark-sprint27/results.json",
            "dataset": chunking_benchmark.get("dataset"),
            "question_count": chunking_benchmark.get("question_count"),
            "recommendation": chunking_benchmark.get("production_decision", {}).get(
                "recommendation", "NEED_MORE_DATA"
            ),
            "rule": chunking_benchmark.get("production_decision", {}).get("rule"),
            "configs": [
                {
                    "config": name,
                    "overall": result.get("overall"),
                    "cross_lingual": result.get("cross_lingual"),
                    "chunk_stats": result.get("chunk_stats"),
                    "context_efficiency": result.get("context_efficiency"),
                    "latency": result.get("latency"),
                }
                for name, result in chunking_benchmark.get("results", {}).items()
            ],
            "available": True,
        }

    return {
        "baseline": baseline,
        "migration_quality_gate": migration_gate,
        "security_validation": security,
        "prompt_injection": (
            {
                "source": "artifacts/security-sprint25/adversarial-results.json",
                "prompt_version": prompt_injection.get("prompt_version"),
                "mode": prompt_injection.get("mode"),
                "case_count": prompt_injection.get("case_count", 0),
                "metrics": prompt_injection.get("metrics", {}),
                "breakdown": prompt_injection.get("breakdown", {}),
                "available": True,
            }
            if prompt_injection
            else None
        ),
        "reranker_decision": reranker_decision,
        "chunking_decision": chunking_decision,
        "timeline": timeline,
        "available": (
            baseline is not None
            or migration_gate is not None
            or prompt_injection is not None
            or reranker_decision is not None
            or chunking_decision is not None
        ),
    }


@router.get("/traces/{trace_id}")
async def trace_detail(
    trace_id: str, request: Request, user: UserContext = Depends(get_current_user)
) -> dict:
    """Real span timings for one trace, fetched from Jaeger with the
    same client app/ui/trace_client.py already uses. Returns
    `available: false` (not a 500) when Jaeger is unreachable or the
    trace isn't indexed yet — both are ordinary, renderable states.

    Only span NAMES and timings are returned; span attributes (which can
    carry question text) are deliberately not forwarded to the browser.
    """
    from app.ui.trace_client import fetch_trace_spans

    settings = _runtime_settings(request)
    jaeger_url = settings.otel_exporter_otlp_endpoint.replace(":4317", ":16686")
    if not jaeger_url.startswith("http"):
        jaeger_url = "http://localhost:16686"

    try:
        spans = await asyncio.to_thread(
            fetch_trace_spans, trace_id, jaeger_url=jaeger_url, max_attempts=2
        )
    except Exception:  # noqa: BLE001 - Jaeger down is a renderable state, not a 500
        return {"trace_id": trace_id, "available": False, "spans": [], "jaeger_url": jaeger_url}

    if not spans:
        return {"trace_id": trace_id, "available": False, "spans": [], "jaeger_url": jaeger_url}

    origin = min(s.start_time_us for s in spans)
    return {
        "trace_id": trace_id,
        "available": True,
        "jaeger_url": jaeger_url,
        "spans": [
            {
                "name": s.name,
                "duration_ms": s.duration_ms,
                "offset_ms": (s.start_time_us - origin) / 1000,
            }
            for s in spans
        ],
    }


@router.get("/sync-runs")
async def sync_runs(
    request: Request,
    source_type: str | None = None,
    limit: int = 50,
    user: UserContext = Depends(get_current_user),
) -> list[dict]:
    """Sync run history across the caller's OWN tenant's source types.
    A source_type owned by another tenant is refused (403) rather than
    silently returning an empty list, matching /sync's own semantics.
    """
    manager = request.app.state.sync_manager
    history = request.app.state.sync_history
    tenant_ids: dict[str, str] = getattr(request.app.state, "tenant_ids", {})

    if source_type is not None:
        owner = tenant_ids.get(source_type)
        if owner is not None and owner != user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail=f"source_type {source_type!r} does not belong to your tenant",
            )
        requested = [source_type]
    else:
        requested = [
            st for st in manager.known_source_types if tenant_ids.get(st) == user.tenant_id
        ]

    runs = [
        {
            "id": run.id,
            "source_type": run.source_type,
            "trigger": run.trigger,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "files_processed": run.files_processed,
            "files_skipped": run.files_skipped,
            "files_deleted": run.files_deleted,
            "chunks_upserted": run.chunks_upserted,
            "error_message": run.error_message,
            "trace_id": run.trace_id,
        }
        for st in requested
        for run in history.list_runs(source_type=st, limit=limit)
    ]
    runs.sort(key=lambda r: r["started_at"], reverse=True)
    return runs[:limit]
