// Sprint 24: TypeScript mirrors of the REAL backend contracts verified
// in app/api/*.py, app/security/models.py, app/retrieval/report.py, and
// app/llm/generate.py — not invented shapes. Where the backend can omit
// a field, the type says `| null`, not an optimistic non-null.

export interface Identity {
  user_id: string
  tenant_id: string
  roles: string[]
  can_sync: boolean
  is_admin: boolean
  auth_enabled: boolean
}

export interface HealthStatus {
  status: string
}

export interface ReadinessCheck {
  ready: boolean
  checks: Record<string, boolean>
  detail: Record<string, string>
  active_collection: string
  active_alias: string
  configured_model: string
  configured_dimension: number
}

export interface SourceSummary {
  source_type: string
  document_count: number
  is_running: boolean
}

export interface SyncResult {
  source_type: string
  status: "success" | "error" | "rejected" | "cancelled"
  run_id: number | null
  error: string | null
  stats: {
    files_processed: number
    chunks_upserted: number
    files_skipped: number
    files_deleted: number
  } | null
  trace_id: string | null
}

export interface SyncRun {
  id: number
  source_type: string
  trigger: string
  status: string
  started_at: string
  finished_at: string | null
  files_processed: number
  files_skipped: number
  files_deleted: number
  chunks_upserted: number
  error_message: string | null
  trace_id: string | null
}

// ---- /ui aggregation contracts (app/api/ui.py) ----

export interface ActiveIndex {
  model: string
  model_key: string
  dimension: number
  output_dimension: number | null
  backend: string
  fingerprint: string
  alias: string
  active_collection: string | null
  previous: {
    model_key: string | null
    output_dimension: number | null
    collection: string | null
    fingerprint: string | null
  } | null
  rollback_available: boolean
  migration_id: string | null
  available: boolean
}

export interface OverviewSource extends SourceSummary {
  last_sync_at: string | null
  last_sync_status: string | null
}

export interface OverviewRun {
  id: number
  source_type: string
  status: string
  trigger: string
  started_at: string
  files_processed: number
  chunks_upserted: number
}

export interface Overview {
  tenant_id: string
  document_count: number
  chunk_count: number | null
  chunk_count_complete: boolean
  source_count: number
  sources: OverviewSource[]
  recent_runs: OverviewRun[]
  active_index: ActiveIndex
  security: {
    auth_enabled: boolean
    tenant_isolation: boolean
    mandatory_acl: boolean
    tenant_id: string
    roles: string[]
  }
}

export interface DocumentRecord {
  tenant_id: string
  source_type: string
  source_id: string
  content_hash: string
  version: number
  status: string
  chunk_count: number | null
  pipeline_fingerprint: string | null
  last_synced_at: string
}

export interface UiSettings {
  active_pipeline: ActiveIndex
  retrieval: {
    rerank_candidate_k: number
    rerank_top_n: number
    sparse_model: string
    reranker_model: string
    fusion: string
  }
  authentication: {
    enabled: boolean
    scheme: string
    roles: string[]
  }
  security: {
    prompt_policy_version: string
    untrusted_context_enabled: boolean
    validation_mode: string
  }
  integrations: {
    qdrant_url: string
    ollama_base_url: string
    otel_endpoint: string
    generation_provider: string
    generation_model: string
  }
}

export interface EvaluationMetricEntry {
  key: string
  label: string
  value: number | null
  stddev: number | null
  runs: number | null
}

export interface EvaluationBaseline {
  config: string
  source: string
  metrics: EvaluationMetricEntry[]
}

export interface EvaluationTimelineEntry {
  sprint: number
  title: string
  question: string
  artifact_dir: string
  available: boolean
}

export interface MigrationQualityGate {
  passed: boolean
  question_count: number
  dataset_fingerprint: string
  cross_recall_at_5: number
  cross_mrr: number
  mono_recall_at_5: number
  ndcg_at_5: number
  tolerance: number
}

export interface Evaluations {
  baseline: EvaluationBaseline | null
  migration_quality_gate: MigrationQualityGate | null
  security_validation: Record<string, unknown> | null
  prompt_injection: PromptInjectionEvaluation | null
  timeline: EvaluationTimelineEntry[]
  available: boolean
}

export interface PromptInjectionEvaluation {
  source: string
  prompt_version: string
  mode: string
  case_count: number
  metrics: Record<string, number | null>
  breakdown: Record<string, Record<string, number | null>>
  available: boolean
}

export interface TraceSpan {
  name: string
  duration_ms: number
  offset_ms: number
}

export interface TraceDetail {
  trace_id: string
  available: boolean
  jaeger_url: string
  spans: TraceSpan[]
}

// ---- /chat SSE contracts (app/api/chat.py, app/llm/generate.py) ----

export interface RetrievedSource {
  rank: number
  source_type: string | null
  source_id: string | null
  citation_location: string | null
  page_number: number | null
  paragraph_index: number | null
  heading_path: string[]
  snippet: string
  score: number | null
  document_version: string | null
  tenant_id: string | null
  visibility: string | null
}

export interface RetrievalStageInfo {
  name: string
  duration_ms: number
  candidates_in: number | null
  candidates_out: number | null
  top_score: number | null
  detail: Record<string, unknown>
}

export interface RetrievalReportPayload {
  stages: RetrievalStageInfo[]
  authorization: {
    acl_applied: boolean
    tenant_id: string | null
    is_system_context: boolean
    user_filters_applied: boolean
  }
  total_duration_ms: number
  security: {
    prompt_policy_version: string | null
    untrusted_context_enabled: boolean
    security_validation_mode: string | null
    output_policy_passed: boolean | null
    output_policy_violations: string[]
  }
}

export interface ChatMetadata {
  prompt_version: string
  trace_id: string
  untrusted_context_enabled?: boolean
  security_validation_mode?: string
}

export interface GroundingResult {
  grounded: boolean
  has_citations: boolean
  citations_found: [string, string, string][]
  ungrounded_citations: [string, string, string][]
}
