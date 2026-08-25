from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_role
from app.security.audit import SYNC_DENIED, log_audit_event
from app.security.models import Role, UserContext
from app.sync.manager import UnknownConnectorError
from app.sync.models import STATUS_REJECTED, TRIGGER_MANUAL

router = APIRouter(prefix="/sync", tags=["sync"])


def _require_owned_source_type(request: Request, source_type: str, user: UserContext) -> None:
    """Sprint 23: refuses (403) a sync/history request for a source_type
    that isn't owned by the caller's own tenant — server-side
    configuration (app.state.tenant_ids), never the request. A
    source_type this app doesn't know about at all still 404s (see
    UnknownConnectorError handling below), matching this app's existing
    "unknown vs. forbidden" distinction rather than leaking which
    source_types exist to an unauthorized caller as a 403.
    """
    tenant_ids: dict[str, str] = getattr(request.app.state, "tenant_ids", {})
    owner = tenant_ids.get(source_type)
    if owner is not None and owner != user.tenant_id:
        log_audit_event(
            SYNC_DENIED,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            endpoint=request.url.path,
            source_type=source_type,
            owning_tenant=owner,
        )
        raise HTTPException(
            status_code=403,
            detail=f"source_type {source_type!r} does not belong to your tenant",
        )


def _result_body(result) -> dict:
    return {
        "source_type": result.source_type,
        "status": result.status,
        "run_id": result.run_id,
        "error": result.error,
        "stats": asdict(result.stats) if result.stats is not None else None,
        "trace_id": result.trace_id,
    }


def _run_body(run) -> dict:
    return {
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


@router.post("/{source_type}")
async def trigger_sync(
    source_type: str,
    request: Request,
    user: UserContext = Depends(require_role(Role.OPERATOR)),
) -> dict:
    """Runs synchronously — waits for the sync to finish and returns the
    final result. See docs/sprint-07-plan.md for why this isn't a
    background task (yet): real data-size/UI needs aren't proven, and
    background-job lifecycle management would be speculative this sprint.

    Sprint 23: requires OPERATOR+ (mutation endpoint — a plain USER can
    never trigger a sync) AND ownership of source_type by the caller's
    own tenant — an operator for tenant A can never trigger a sync for a
    source_type belonging to tenant B, even if both happen to use the
    same source_type name (e.g. both configured "filesystem").
    """
    _require_owned_source_type(request, source_type, user)
    manager = request.app.state.sync_manager
    try:
        result = await manager.trigger_sync(source_type, TRIGGER_MANUAL)
    except UnknownConnectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if result.status == STATUS_REJECTED:
        raise HTTPException(status_code=409, detail=_result_body(result))

    return _result_body(result)


@router.get("/{source_type}/history")
async def sync_history(
    source_type: str,
    request: Request,
    limit: int = 50,
    user: UserContext = Depends(require_role(Role.OPERATOR)),
) -> list[dict]:
    """Sprint 23: OPERATOR+ and tenant-owned, same as trigger_sync above
    — sync history (file counts, error messages) is operational detail
    that shouldn't leak across tenants either.
    """
    _require_owned_source_type(request, source_type, user)
    history = request.app.state.sync_history
    return [_run_body(run) for run in history.list_runs(source_type=source_type, limit=limit)]
