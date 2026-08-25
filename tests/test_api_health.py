from fastapi.testclient import TestClient

from app.main import create_app
from app.registry.store import DocumentRegistry
from app.sync.history import SyncHistory


class _StubManager:
    known_source_types: list[str] = []

    def is_running(self, source_type):
        return False


def _client(tmp_path, list_ollama_models=None, readiness_check=None) -> TestClient:
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return TestClient(
        create_app(
            _StubManager(), history, registry, list_ollama_models=list_ollama_models,
            readiness_check=readiness_check,
        )
    )


def test_health_returns_ok_without_touching_any_real_service(tmp_path):
    client = _client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ollama_returns_model_list_on_success(tmp_path):
    async def fake_list_models():
        return ["qwen2.5:7b-instruct", "nomic-embed-text"]

    client = _client(tmp_path, list_ollama_models=fake_list_models)

    response = client.get("/health/ollama")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "models": ["qwen2.5:7b-instruct", "nomic-embed-text"],
    }


def test_health_ollama_returns_503_when_ollama_is_unreachable(tmp_path):
    async def failing_list_models():
        raise RuntimeError("Could not reach Ollama: connection refused")

    client = _client(tmp_path, list_ollama_models=failing_list_models)

    response = client.get("/health/ollama")

    assert response.status_code == 503


def test_health_ollama_returns_503_when_not_configured(tmp_path):
    client = _client(tmp_path)

    response = client.get("/health/ollama")

    assert response.status_code == 503


def test_health_ready_returns_200_when_ready(tmp_path):
    async def ready():
        return {"ready": True, "checks": {}}

    client = _client(tmp_path, readiness_check=ready)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_health_ready_returns_503_when_not_ready(tmp_path):
    async def not_ready():
        return {"ready": False, "checks": {"active_collection_exists": False}}

    client = _client(tmp_path, readiness_check=not_ready)

    response = client.get("/health/ready")

    assert response.status_code == 503


def test_health_ready_returns_503_when_not_configured(tmp_path):
    client = _client(tmp_path)

    response = client.get("/health/ready")

    assert response.status_code == 503
