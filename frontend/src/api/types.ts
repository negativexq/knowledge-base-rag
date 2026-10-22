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
  chunking: {
    name: string
    mode: string
    target_tokens: number
    overlap_tokens: number
    hard_max_tokens: number | null
    tokenizer_model: string
    tokenizer_revision: string
    boundary_strategy: string
  }
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

// app/parsing/models.py::ParseReport.as_dict()
export interface IngestionQuality {
  pages: number
  ocr_pages: Record<string, number>
  skipped_pages: number
  garbled_blocks_dropped: number
  empty_pages: number
  headings: number
  tables: number
  furniture: number
  heading_source: string
  needs_review: boolean
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
  // Only PDFs ingested since quality reports were added carry one.
  ingestion_quality?: IngestionQuality | null
  last_synced_at: string
}

export interface UiSettings {
  active_pipeline: ActiveIndex
  retrieval: {
    rerank_candidate_k: number
    rerank_top_n: number
    reranker_enabled: boolean
    reranker_backend: string
    sparse_model: string
    reranker_model: string | null
    fusion: string
    chunking: ActiveIndex["chunking"]
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
  reranker_decision: RerankerDecision | null
  chunking_decision: ChunkingDecision | null
  timeline: EvaluationTimelineEntry[]
  available: boolean
}

export interface RerankerDecisionConfig {
  config: string
  model: string
  overall: Record<string, number>
  cross_lingual: Record<string, number | null>
  mono_lingual: Record<string, number | null>
  latency: Record<string, number | string | null>
  rescue_drop: Record<string, number | string | null>
}

export interface RerankerDecision {
  source: string
  dataset: string
  question_count: number
  recommendation: string
  rule: string
  configs: RerankerDecisionConfig[]
  available: boolean
}

export interface ChunkingDecisionConfig {
  config: string
  overall: Record<string, number>
  cross_lingual: Record<string, number | null>
  chunk_stats: Record<string, unknown>
  context_efficiency: Record<string, number | string | null>
  latency: Record<string, number | string | null>
}

export interface ChunkingDecision {
  source: string
  dataset: string
  question_count: number
  recommendation: string
  rule: string
  configs: ChunkingDecisionConfig[]
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

export interface UsageSummary {
  llm_requests: number; input_tokens: number; output_tokens: number; cached_tokens: number
  tool_calls: number; retries: number; usage_complete: boolean
  priced_requests: number; cost_complete: boolean; cost_usd: number | null; known_cost_usd: number
}
export interface RequestTrace {
  trace_id: string; span_id: string; started_at: string; duration_ms?: number
  outcome: string; pipeline: string; error_type?: string | null
  parent_trace_id?: string | null; usage?: UsageSummary
}
export interface TraceSpan {
  span_id?: string | null
  parent_span_id?: string | null
  status?: string
  attributes?: Record<string, string | number | boolean | string[]>
  name: string
  duration_ms: number
  offset_ms: number
}

export interface TraceDetail {
  trace_id: string
  available: boolean
  jaeger_url: string
  spans: TraceSpan[]
  request?: RequestTrace | null
  can_open_external?: boolean
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
  token_count?: number | null
  // Readable section labels the evidence block spans, in document order
  // (more than one when a small source was merged in full).
  section_labels?: string[]
}

export interface RetrievalStageInfo {
  name: string
  duration_ms: number
  candidates_in: number | null
  candidates_out: number | null
  top_score: number | null
  detail: Record<string, unknown>
}

export interface AnswerabilityFeatures {
  pre_acl_candidate_count: number | null
  authorized_candidate_count: number
  reranked_count: number
  top1_score: number | null
  top2_score: number | null
  top3_score: number | null
  top1_top2_margin: number | null
  top1_top3_margin: number | null
  mean_top3_score: number | null
  mean_top5_score: number | null
  min_top5_score: number | null
  max_top5_score: number | null
  std_top5_score: number | null
  distinct_source_count_top5: number | null
  distinct_document_count_top5: number | null
  top1_fused_rank: number | null
  top1_dense_rank: number | null
  top1_sparse_rank: number | null
  dense_sparse_agreement: number | null
  fused_rerank_agreement: number | null
  source_score_concentration: number | null
  duplicate_source_chunk_count_top5: number | null
  feature_latency_ms: number
}

export interface AnswerabilityObservation {
  reason: string
  features: AnswerabilityFeatures
  top_authorized_source_ids: string[]
  top_raw_reranker_scores: number[]
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
  reranker: {
    enabled: boolean
    model: string | null
    backend: string | null
    candidate_k: number
    top_n: number
  } | null
  // Additive and optional for clients that consume older retrieval reports.
  answerability?: AnswerabilityObservation
  context?: {
    retrieved_chunk_count?: number
    top_context_tokens?: number | null
  }
  security: {
    prompt_policy_version: string | null
    untrusted_context_enabled: boolean
    security_validation_mode: string | null
    output_policy_passed: boolean | null
    output_policy_violations: string[]
  }
}

// One support unit the model was given on the support-ID answer path
// (app/llm/structured_output.py::support_unit_citation_map). An "[E1.S4]"
// citation resolves to it; source_rank is its card's rank in `sources`.
export interface SupportUnitRef {
  support_id: string
  source_rank: number
  source_type: string | null
  source_id: string | null
  section_label: string | null
  text: string
  page_number?: number | null
  page_end?: number | null
}

export interface ChatMetadata {
  parent_trace_id?: string | null
  phase?: string
  agentic?: { observability?: UsageSummary; requests?: number; tool_calls?: number }
  prompt_version: string
  trace_id: string
  untrusted_context_enabled?: boolean
  security_validation_mode?: string
  support_units?: SupportUnitRef[]
  // How the answer prompt was fitted to the context window (support-ID path).
  prompt_fit?: PromptFit | null
  // Set when the model was not called at all (no evidence), with the reason.
  generation_skipped?: string
  // Application-computed results with their cited inputs (research mode).
  calculations?: CalculationSummary[]
}

export interface CalculationInput {
  name: string
  label: string
  value: string | null
  unit: string
  support_id: string | null
  page: number | null
}

export interface CalculationSummary {
  id: string
  expression: string
  result: string
  unit: string
  inputs: CalculationInput[]
  support_ids: string[]
}

export interface PromptFit {
  prompt_tokens: number
  prompt_token_limit: number
  units_sent: number
  units_dropped: number
}

// The answer-level validation verdict (the `security` event that carries
// `passed`, emitted after the answer). Distinct from the retrieval-time
// `security` event, which carries output_policy_* fields instead.
export interface AnswerValidation {
  passed: boolean
  abstain: boolean
  validator_failure_codes: string[]
  // How the model call ended, as the provider reported it.
  generation?: {
    done_reason: string | null
    prompt_tokens: number | null
    output_tokens: number | null
  }
}

export interface GroundingResult {
  grounded: boolean
  has_citations: boolean
  citations_found: [string, string, string][]
  ungrounded_citations: [string, string, string][]
}

export interface ResearchStep {
  id: string
  // "stage": a user-facing research stage; otherwise a single tool operation.
  kind?: "stage"
  operation: string
  status: "running" | "completed" | "retrying" | "failed"
  failure_codes?: string[]
  stage?: string
  // Fixed application text for the stage or its reason code, never model output.
  message?: string
  reason?: string
  duration_ms?: number
  added_evidence?: number
  // Client clock (Date.now()) when this step was first seen as running.
  receivedAt?: number
}
export interface Clarification { question: string; options: string[] }
export interface ClarificationReply { question: string; answer: string }
export interface ComparisonCell {
  source_id: string
  text: string
  support_ids: string[]
  calculation?: { expression: string; result: string } | null
}
export interface ComparisonRow { aspect: string; cells: ComparisonCell[] }
export interface DocumentReference { source_type: string; source_id: string; document_version: string }
export interface DocumentReadRequest {
  document: DocumentReference
  action: "outline" | "search" | "section" | "page" | "neighbors"
  query?: string
  section_id?: string
  page?: number
  chunk_id?: string
  offset?: number
}
export interface DocumentReadResult {
  document: DocumentReference
  passages: { chunk_id: string; text: string; page_number: number | null; page_end: number | null; section_id: string; heading_path: string[] }[]
  outline: { section_id: string; title: string; page_number: number | null; chunk_count: number }[]
  has_more: boolean
  scan_limited: boolean
  next_offset: number | null
  indexed_at?: string | null
  current_version?: string | null
  status?: string | null
}

export type FeedbackReason = "incorrect" | "unsupported" | "outdated" | "incomplete" | "other"
export interface FeedbackSubmission {
  question: string; answer: string; claim: string; reason: FeedbackReason; note: string
  support_ids: string[]; trace_id: string | null
  // What the reporter says is right; reviewers confirm it before promotion.
  expected_answer?: string; expected_source?: string; expected_page?: number | null
}
export interface EvaluationCandidate {
  id: string; question: string; expected_answer: string; expected_source: string
  expected_page: number | null; reason: FeedbackReason; origin: "user_feedback"; feedback_id: string; created_at: string
}
export interface FeedbackRecord extends FeedbackSubmission {
  id: string; user_id: string; status: "open" | "triaged" | "resolved" | "dismissed"
  created_at: string; updated_at: string; reviewer_note: string; snapshot_origin: "user_submitted"
}

export interface DocumentPolicy {
  source_type: string
  source_id: string
  access: "tenant" | "restricted"
  user_ids: string[]
  group_ids: string[]
  revision: number
}
