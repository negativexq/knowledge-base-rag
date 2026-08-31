from typing import Literal, Self, cast

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.evaluation.critical_validator_runtime import validate_validator_selector
from app.ingestion.chunking_config import (
    BOUNDARY_STRATEGY,
    QWEN3_EMBEDDING_TOKENIZER,
    QWEN3_TOKENIZER_REVISION,
    ChunkingConfig,
)
from app.llm.openai_client import OPENAI_MODEL
from app.reranker.config import (
    MULTILINGUAL_RERANKER_MODEL,
    RERANKER_BACKEND,
    RERANKER_CANDIDATE_K,
    RERANKER_TOP_N,
)
from app.security.auth import validate_auth_configuration

SecurityValidationMode = Literal["fast", "strict"]
RuntimeProfile = Literal["DEV_FAST", "BENCHMARK_REFERENCE"]
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

    app_env: Literal["development", "production"] = "development"
    runtime_profile: RuntimeProfile = "DEV_FAST"

    ollama_base_url: str = "http://host.docker.internal:11434"
    # DEV_FAST is the local interactive profile. Benchmark retrieval never
    # calls the chat provider, so changing this does not change retrieval
    # semantics or the embedding model.
    ollama_model: str = "qwen3.5:4b"
    ollama_thinking: bool = False
    ollama_num_ctx: int = Field(default=4096, gt=0)
    ollama_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    ollama_read_timeout_seconds: float = Field(default=180.0, gt=0)
    ollama_overall_timeout_seconds: float = Field(default=240.0, gt=0)
    ollama_embed_model: str = "nomic-embed-text"

    # The evidence-backed/support-unit path is the default portfolio profile.
    # Explicit false values remain available for legacy regression/debug runs.
    rag_pipeline_v2: bool = True
    support_ids_enabled: bool = True
    pipeline_v2_context_token_budget: int = Field(default=1200, gt=0)

    # Phase 6C is opt-in shadow telemetry. It never suppresses generation.
    semantic_answerability_enabled: bool = False
    semantic_answerability_shadow: bool = True
    answerability_eval_model: str = "qwen3:4b"
    answerability_eval_timeout_seconds: float = Field(default=30.0, gt=0)
    answerability_eval_retries: int = Field(default=1, ge=0, le=2)

    # Server-owned critical-value validator rollout controls. Architecture V2
    # is the validated portfolio-runtime default; baseline and V3 remain
    # explicit server-side rollback/debug options.
    critical_validator_version: Literal["baseline", "v3", "architecture_v2"] = "architecture_v2"
    critical_validator_v3_shadow_enabled: bool = False
    critical_validator_arch_v2_shadow_enabled: bool = False

    # Explicit local/debug forensic capture.  Both switches are required for
    # raw text; normal production telemetry remains bounded and unaffected.
    rag_forensic_capture_enabled: bool = False
    rag_forensic_capture_raw_text: bool = False
    rag_forensic_capture_dir: str | None = None

    @model_validator(mode="after")
    def validate_forensic_capture(self) -> Self:
        if self.rag_forensic_capture_raw_text and not self.rag_forensic_capture_enabled:
            raise ValueError(
                "RAG_FORENSIC_CAPTURE_RAW_TEXT requires RAG_FORENSIC_CAPTURE_ENABLED"
            )
        return self

    # Qwen3-Embedding-4B benchmark configuration — served
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
    # assumed from the model card.
    qwen3_embed_dimension: int = Field(default=2560, gt=0)
    qwen3_query_instruction: str = (
        "Given a search query, retrieve relevant passages that answer the query"
    )
    qwen3_document_instruction: str = ""

    # Qwen3-Embedding-0.6B — the smaller sibling, same
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
    generation_provider: Literal["ollama", "claude", "openai"] = "ollama"
    embedding_provider: Literal["ollama"] = "ollama"

    # The single source of truth for which embedding model
    # actually serves production traffic — every other embedding
    # attribute (Ollama model name, revision, instruction strings,
    # backend) is looked up FROM this key via
    # app/llm/embedding_models.py's existing per-model registry
    # (nomic_config/qwen3_4b_config/qwen3_0_6b_config), not duplicated
    # here as parallel raw strings that could drift out of sync with it.
    # embedding_output_dimension=None means "native" for the selected
    # model; an int requests that
    # output size instead — see
    # app/llm/embedding_models.py::get_embedding_model_config.
    #
    # The configured collection must match this model and dimension. A
    # model change alone is never sufficient to move production traffic;
    # the physical target collection must exist, be validated, and be
    # activated first (see app/migration and the startup schema guard).
    embedding_model_key: Literal["nomic", "qwen3-4b", "qwen3-0.6b"] = "qwen3-4b"
    embedding_output_dimension: int | None = 1024

    # Reranking is independently configurable from the embedding pipeline.
    # The measured multilingual benchmark adopted the
    # multilingual challenger: it recovered cross-lingual rank quality
    # without a mono-lingual Recall@5 regression. Latency is documented in
    # artifacts/reranker-benchmark-sprint26/report.md.
    reranker_enabled: bool = True
    reranker_model: str = MULTILINGUAL_RERANKER_MODEL
    reranker_backend: Literal["sentence-transformers"] = RERANKER_BACKEND
    # The global/reference value remains RERANKER_CANDIDATE_K (20). DEV_FAST
    # applies its measured local-iteration budget (15) unless an explicit
    # environment or constructor override pins another value.
    reranker_candidate_k: int = Field(default=RERANKER_CANDIDATE_K, gt=0)
    reranker_top_n: int = Field(default=RERANKER_TOP_N, gt=0)
    reranker_max_concurrency: int = Field(default=1, ge=1, le=16)
    reranker_trust_remote_code: bool = False

    # Production keeps the legacy word-window as the explicit
    # benchmark baseline until a measured candidate is adopted. Switching
    # to token-aware mode is one server-owned setting; ingestion,
    # fingerprinting, and the Operations Console all read this method.
    chunking_mode: Literal["baseline", "token_aware"] = "baseline"
    chunk_target_tokens: int = Field(default=512, gt=0)
    chunk_overlap_tokens: int = Field(default=64, ge=0)
    chunk_hard_max_tokens: int | None = Field(default=576, gt=0)
    chunk_tokenizer_model: str = QWEN3_EMBEDDING_TOKENIZER
    chunk_tokenizer_revision: str = QWEN3_TOKENIZER_REVISION
    chunk_boundary_strategy: str = BOUNDARY_STRATEGY

    def chunking_config(self) -> ChunkingConfig:
        if self.chunking_mode == "baseline":
            return ChunkingConfig.current_baseline()
        return ChunkingConfig(
            name=f"{self.chunk_target_tokens}-{self.chunk_overlap_tokens}",
            mode="token_aware",
            target_tokens=self.chunk_target_tokens,
            overlap_tokens=self.chunk_overlap_tokens,
            hard_max_tokens=self.chunk_hard_max_tokens,
            tokenizer_model=self.chunk_tokenizer_model,
            tokenizer_revision=self.chunk_tokenizer_revision,
            boundary_strategy=self.chunk_boundary_strategy,
        )

    # The logical Qdrant alias real traffic is served through
    # once a migration has activated it — see app/migration/aliasing.py.
    # Before any migration has ever run, this alias doesn't exist yet and
    # every call site transparently falls back to the literal
    # qdrant_collection_name below, so a fresh/unmigrated deployment is
    # entirely unaffected.
    qdrant_active_alias: str = "kb_active"

    # Authentication is enabled by default. The explicit bypass is allowed
    # only in development; the model validator rejects it in production.
    auth_enabled: bool = True
    # Explicit JSON credentials replace the development-only demo fixture.
    auth_tokens_json: str | None = None

    # Which tenant owns documents ingested through each
    # connector — server-side configuration, never a value a request/
    # ingest call can choose. Matches this app's existing one-connector-
    # instance-per-source_type architecture (app/wiring.py::
    # build_connectors): each connector is wholly owned by one tenant.
    filesystem_tenant_id: str = "tenant-a"
    notion_tenant_id: str = "tenant-a"

    # Comma-separated origins allowed to call this API from a
    # browser — the React operations console (frontend/) runs on its own
    # origin in local development. An explicit allow-list, never "*";
    # app/main.py also refuses to enable credentialed CORS, since this
    # app authenticates via an Authorization header, not cookies.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    claude_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 2048
    openai_api_key: str | None = None
    openai_model: str = OPENAI_MODEL

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "kb_chunks"

    registry_db_path: str = "data/registry.db"

    # Real folder LocalFilesystemConnector scans when wired for real.
    filesystem_root_path: str = "data/documents"

    notion_api_key: str | None = None

    # Per-connector sync intervals — a plain field per connector (same
    # pattern as claude_*/notion_api_key above), not a generic mapping in
    # Settings; app/sync/scheduler.py::SyncScheduler itself takes a generic
    # dict[str, float] built from these at app-wiring time, so the
    # scheduler stays connector-agnostic even though Settings isn't.
    # gt=0, not ge=0: a periodic SyncScheduler interval of exactly 0 has
    # no sane meaning (busy-spin), same reasoning as
    # embedding_concurrency below).
    filesystem_sync_interval_seconds: float = Field(default=300.0, gt=0)
    notion_sync_interval_seconds: float = Field(default=1800.0, gt=0)

    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # v3 is the production trust-boundary prompt. v1/v2 remain
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
    # loudly at startup. le=32 is a generous ceiling, not a
    # tuned number — the benchmark already showed zero measured
    # benefit past 4, this constraint just needs to catch a clearly
    # unreasonable value, not pick the "right" one.
    embedding_concurrency: int = Field(default=4, ge=1, le=32)

    @classmethod
    def dev_fast(cls, **overrides: object) -> Self:
        """Return the documented local interactive profile."""
        values = {
            "runtime_profile": "DEV_FAST",
            "ollama_model": "qwen3.5:4b",
            "ollama_thinking": False,
            "reranker_candidate_k": 15,
            "reranker_top_n": 5,
            "embedding_model_key": "qwen3-4b",
            "embedding_output_dimension": 1024,
            "active_prompt_version": "v3",
            "security_validation_mode": "strict",
        }
        values.update(overrides)
        return cls(_env_file=None, **values)

    @classmethod
    def benchmark_reference(cls, **overrides: object) -> Self:
        """Return the fixed retrieval reference profile for measurements."""
        values = {
            "runtime_profile": "BENCHMARK_REFERENCE",
            "reranker_candidate_k": RERANKER_CANDIDATE_K,
            "reranker_top_n": RERANKER_TOP_N,
            "embedding_model_key": "qwen3-4b",
            "embedding_output_dimension": 1024,
            "active_prompt_version": "v3",
            "security_validation_mode": "strict",
        }
        values.update(overrides)
        return cls(_env_file=None, **values)

    @model_validator(mode="after")
    def apply_runtime_profile_defaults(self) -> Self:
        if (
            self.runtime_profile == "DEV_FAST"
            and "reranker_candidate_k" not in self.model_fields_set
        ):
            self.reranker_candidate_k = 15
        return self

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        validate_auth_configuration(
            app_env=self.app_env,
            auth_enabled=self.auth_enabled,
            auth_tokens_json=self.auth_tokens_json,
        )
        return self

    @model_validator(mode="after")
    def validate_critical_validator(self) -> Self:
        validate_validator_selector(self.critical_validator_version)
        return self

    @model_validator(mode="after")
    def validate_reranker_bounds(self) -> Self:
        if self.reranker_candidate_k < self.reranker_top_n:
            raise ValueError(
                "reranker_candidate_k must be greater than or equal to "
                f"reranker_top_n ({self.reranker_top_n})"
            )
        return self


settings = Settings()
