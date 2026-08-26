from typing import Literal, cast

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SecurityValidationMode = Literal["fast", "strict"]
VALID_SECURITY_VALIDATION_MODES = ("fast", "strict")


def validate_security_validation_mode(value: str) -> SecurityValidationMode:
    """Validate the server-owned release mode at every generation boundary."""
    if value not in VALID_SECURITY_VALIDATION_MODES:
        raise ValueError(
            f"security validation mode must be one of {VALID_SECURITY_VALIDATION_MODES}, "
            f"got {value!r}"
        )
    return cast(SecurityValidationMode, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_embed_model: str = "nomic-embed-text"

    # Sprint 18: Qwen3-Embedding-4B benchmark challenger config — served
    # via the same Ollama instance as everything else (no new transport),
    # so only its model name/revision/dimension/instruction strings need
    # to be configurable. Defaults match Qwen3-Embedding's published
    # model card (asymmetric instruction: queries get an "Instruct: ...
    # \nQuery: " prefix, documents get none) — see
    # app/llm/embedding_models.py. Not used by the production default
    # embedding path (settings.embedding_provider/ollama_embed_model
    # unchanged); only scripts/benchmark_embeddings.py reads these.
    qwen3_embed_model: str = "qwen3-embedding:4b"
    qwen3_embed_revision: str = "latest"
    # Verified against a real /api/embeddings call before use, not
    # assumed from the model card — see docs/sprint-18-plan.md.
    qwen3_embed_dimension: int = Field(default=2560, gt=0)
    qwen3_query_instruction: str = (
        "Given a search query, retrieve relevant passages that answer the query"
    )
    qwen3_document_instruction: str = ""

    # Sprint 19: Qwen3-Embedding-0.6B — the smaller sibling, same
    # instruction convention as the 4B (qwen3_query_instruction/
    # qwen3_document_instruction above are shared across both sizes,
    # a property of the Qwen3-Embedding family's format, not the 4B
    # specifically). Verified via a real /api/embed call: native output
    # dimension is 1024, not guessed.
    qwen3_0_6b_embed_model: str = "qwen3-embedding:0.6b"
    qwen3_0_6b_embed_revision: str = "latest"
    qwen3_0_6b_embed_dimension: int = Field(default=1024, gt=0)

    # Generation (chat) and embedding are independent choices — Claude has
    # no embedding endpoint, so embedding_provider can never follow
    # generation_provider. embedding_provider is a Literal of one value
    # today (only Ollama is implemented), kept as its own setting rather
    # than folded into generation_provider so a second embedding backend
    # can be added later without touching call sites that only care about
    # embedding.
    generation_provider: Literal["ollama", "claude"] = "ollama"
    embedding_provider: Literal["ollama"] = "ollama"

    # Sprint 22: the SINGLE source of truth for which embedding model
    # actually serves production traffic — every other embedding
    # attribute (Ollama model name, revision, instruction strings,
    # backend) is looked up FROM this key via
    # app/llm/embedding_models.py's existing per-model registry
    # (nomic_config/qwen3_4b_config/qwen3_0_6b_config), not duplicated
    # here as parallel raw strings that could drift out of sync with it.
    # embedding_output_dimension=None means "native" for the selected
    # model; an int (Sprint 19's Matryoshka truncation) requests that
    # output size instead — see
    # app/llm/embedding_models.py::get_embedding_model_config.
    #
    # Sprint 18-21 benchmarked nomic-embed-text@768 (the original
    # production default) against Qwen3-Embedding at several sizes/
    # dimensions and reached a pre-committed, statistically-supported
    # ADOPT_QWEN3_4B_1024 decision (docs/PLANNING.md Sprint 21 closing
    # note). Sprint 22 executes that decision as a real, validated,
    # rollback-tested Qdrant index migration
    # (app/migration/embedding_migration.py, docs/embedding-migration.md)
    # before flipping this default — so changing this value alone is
    # NEVER sufficient to move production traffic; the physical target
    # collection must exist, be validated, and be activated first (see
    # app/main.py's startup schema-mismatch guard).
    embedding_model_key: Literal["nomic", "qwen3-4b", "qwen3-0.6b"] = "qwen3-4b"
    embedding_output_dimension: int | None = 1024

    # Sprint 22: the logical Qdrant alias real traffic is served through
    # once a migration has activated it — see app/migration/aliasing.py.
    # Before any migration has ever run, this alias doesn't exist yet and
    # every call site transparently falls back to the literal
    # qdrant_collection_name below (today's exact pre-Sprint-22
    # behavior), so a fresh/unmigrated deployment is entirely unaffected.
    qdrant_active_alias: str = "kb_active"

    # Sprint 23: security boundary. Defaults to enabled — an explicit,
    # loud local-dev-only opt-out (never the silent/ambiguous default;
    # app/wiring.py logs a warning at startup when this is False). See
    # docs/security.md.
    auth_enabled: bool = True
    # Optional raw JSON blob — {"token-...": {"user_id":...,
    # "tenant_id":..., "roles": ["USER"]}} — REPLACING (not merging with)
    # app/security/auth.py::DEFAULT_DEV_TOKENS for a real deployment.
    # None (default) uses the demo dev token fixture — appropriate for
    # local development only.
    auth_tokens_json: str | None = None

    # Sprint 23: which tenant owns documents ingested through each
    # connector — server-side configuration, never a value a request/
    # ingest call can choose. Matches this app's existing one-connector-
    # instance-per-source_type architecture (app/wiring.py::
    # build_connectors): each connector is wholly owned by one tenant.
    filesystem_tenant_id: str = "tenant-a"
    notion_tenant_id: str = "tenant-a"

    # Sprint 24: comma-separated origins allowed to call this API from a
    # browser — the React operations console (frontend/) runs on its own
    # origin in local development. An explicit allow-list, never "*";
    # app/main.py also refuses to enable credentialed CORS, since this
    # app authenticates via an Authorization header, not cookies.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

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
    # gt=0, not ge=0: a periodic SyncScheduler interval of exactly 0 has
    # no sane meaning (busy-spin), same reasoning as
    # embedding_concurrency below (Sprint 16).
    filesystem_sync_interval_seconds: float = Field(default=300.0, gt=0)
    notion_sync_interval_seconds: float = Field(default=1800.0, gt=0)

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # Sprint 25: v3 is the production trust-boundary prompt. v1/v2 remain
    # loadable for reproducible baseline comparisons.
    active_prompt_version: str = "v3"
    # Production/default is release-gated. FAST is an explicit, documented
    # opt-in for latency-sensitive development paths only.
    security_validation_mode: SecurityValidationMode = "strict"

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
    # ge=1: asyncio.Semaphore(0) never lets any embed call through, so a
    # value of 0 would deadlock the first real sync instead of failing
    # loudly at startup (Sprint 16). le=32 is a generous ceiling, not a
    # tuned number — Sprint 14's benchmark already showed zero measured
    # benefit past 4, this constraint just needs to catch a clearly
    # unreasonable value, not pick the "right" one.
    embedding_concurrency: int = Field(default=4, ge=1, le=32)


settings = Settings()
