from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

ListModelsFn = Callable[[], Awaitable[list[str]]]


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
