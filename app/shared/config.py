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

    # Real folder LocalFilesystemConnector scans when wired for real
    # (app/wiring.py, Sprint 10) — no such setting existed before this,
    # since app/main.py::create_app() was only ever exercised with fake
    # components in tests until now.
    filesystem_root_path: str = "data/documents"

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

    # DeepEval judge model for app/evaluation — deliberately independent of
    # ollama_model (generation). production-rag-platform found a smaller
    # judge (qwen2.5:3b-instruct) gave an internally inconsistent
    # verdict/reason pair; 7B fixed it. Kept as its own setting so a
    # golden-set run can use a different (typically smaller/faster) model
    # for generation than for judging, matching the reference project.
    eval_judge_model: str = "qwen2.5:7b-instruct"

    # Bounded concurrency for embedding calls during ingestion
    # (app/ingestion/ingest.py::embed_texts_concurrently) — kept as a
    # plain, independently-defaulted field rather than importing
    # ingest.py's own DEFAULT_EMBEDDING_CONCURRENCY constant, which would
    # create a circular import (ingest.py -> shared.tracing ->
    # shared.config). Chosen from a real benchmark against native Ollama,
    # not guessed — see docs/sprint-14-plan.md and the README's
    # throughput section for the measured chunks/sec at each level.
    embedding_concurrency: int = 4


settings = Settings()
