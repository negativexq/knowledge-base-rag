from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_embed_model: str = "nomic-embed-text"

    # Generation (chat) and embedding are independent choices — Claude has
    # no embedding endpoint, so embedding_provider can never follow
    # generation_provider. embedding_provider is a Literal of one value
    # today (only Ollama is implemented), kept as its own setting rather
    # than folded into generation_provider so a second embedding backend
    # can be added later without touching call sites that only care about
    # embedding.
    generation_provider: Literal["ollama", "claude"] = "ollama"
    embedding_provider: Literal["ollama"] = "ollama"

    claude_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 2048

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "kb_chunks"

    registry_db_path: str = "data/registry.db"

    notion_api_key: str | None = None

    # Per-connector sync intervals — a plain field per connector (same
    # pattern as claude_*/notion_api_key above), not a generic mapping in
    # Settings; app/sync/scheduler.py::SyncScheduler itself takes a generic
    # dict[str, float] built from these at app-wiring time, so the
    # scheduler stays connector-agnostic even though Settings isn't.
    filesystem_sync_interval_seconds: float = 300.0
    notion_sync_interval_seconds: float = 1800.0

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    active_prompt_version: str = "v1"


settings = Settings()
