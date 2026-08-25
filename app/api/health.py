from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

ListModelsFn = Callable[[], Awaitable[list[str]]]
# Sprint 22: returns a JSON-able dict with at least a "ready" bool — see
# app/migration/readiness.py::check_readiness. Kept as an injected
# callable (same pattern as ListModelsFn) so this router never imports
# Qdrant/Ollama clients directly.
ReadinessCheckFn = Callable[[], Awaitable[dict]]


@router.get("/health")
async def health() -> dict:
    """Plain liveness — no dependency on Qdrant/Ollama/SQLite. Used by the
    Docker healthcheck (docker-compose.yml)."""
    return {"status": "ok"}


@router.get("/health/ollama")
async def health_ollama(request: Request) -> dict:
    """A REAL connectivity check, not a liveness stub — reuses
    OllamaClient.list_models() to prove the configured OLLAMA_BASE_URL
    (host.docker.internal from inside a container, Sprint 11) is actually
    reachable, not just plausible-looking config.
    """
    list_models: ListModelsFn | None = request.app.state.list_ollama_models
    if list_models is None:
        raise HTTPException(status_code=503, detail="Ollama health check not configured")

    try:
        models = await list_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unreachable: {exc}") from exc

    return {"status": "ok", "models": models}


@router.get("/health/ready")
async def health_ready(request: Request) -> dict:
    """Sprint 22: is production search actually usable right now — active
    collection/alias exists with the expected dense dimension, Qdrant is
    reachable, the embedding backend is reachable, and the configured
    model is available. Deliberately does NOT run a real embedding
    inference call on every probe (cheap/reliable health semantics per
    the Sprint 22 spec, not a full round-trip search) — see
    app/migration/readiness.py::check_readiness.
    """
    readiness_check: ReadinessCheckFn | None = request.app.state.readiness_check
    if readiness_check is None:
        raise HTTPException(status_code=503, detail="Readiness check not configured")

    result = await readiness_check()
    if not result.get("ready", False):
        raise HTTPException(status_code=503, detail=result)
    return result
