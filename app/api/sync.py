from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.sync.manager import UnknownConnectorError
from app.sync.models import STATUS_REJECTED, TRIGGER_MANUAL

router = APIRouter(prefix="/sync", tags=["sync"])


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
async def trigger_sync(source_type: str, request: Request) -> dict:
    """Runs synchronously — waits for the sync to finish and returns the
    final result. See docs/sprint-07-plan.md for why this isn't a
    background task (yet): real data-size/UI needs aren't proven, and
    background-job lifecycle management would be speculative this sprint.
    """
    manager = request.app.state.sync_manager
    try:
        result = await manager.trigger_sync(source_type, TRIGGER_MANUAL)
    except UnknownConnectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if result.status == STATUS_REJECTED:
        raise HTTPException(status_code=409, detail=_result_body(result))

    return _result_body(result)


@router.get("/{source_type}/history")
async def sync_history(source_type: str, request: Request, limit: int = 50) -> list[dict]:
    history = request.app.state.sync_history
    return [_run_body(run) for run in history.list_runs(source_type=source_type, limit=limit)]
