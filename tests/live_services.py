"""Shared checks and wiring for tests that run against the real local
services (native Ollama on :11434, Qdrant on :6333). Each check is cheap
and offline-safe, so a missing service or model skips a test instead of
failing it."""

import json
import socket
import urllib.request

from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.shared.config import Settings, settings


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def ollama_models() -> set[str]:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=0.5) as response:
            return {model.get("name") for model in json.load(response).get("models", [])}
    except (OSError, ValueError):
        return set()


def qdrant_up() -> bool:
    return port_open("localhost", 6333)


def ollama_has(*models: str) -> bool:
    available = ollama_models()
    return all(model in available for model in models)


def production_embed_model(config: Settings = settings) -> str:
    return active_embedding_config(config).ollama_model


def production_embed_fn(ollama: OllamaClient, config: Settings = settings):
    """Document embedding exactly as app/wiring.py's sync path does it."""
    embed_config = active_embedding_config(config)

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    return embed_fn
