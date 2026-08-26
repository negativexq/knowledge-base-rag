import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { healthApi } from "@/api/health"
import { sourcesApi } from "@/api/sources"
import { syncApi } from "@/api/sync"
import { uiApi } from "@/api/ui"
import type { Identity } from "@/api/types"
import { useIdentity } from "@/hooks/useIdentity"
import Evaluations from "@/pages/Evaluations"
import Knowledge from "@/pages/Knowledge"
import Overview from "@/pages/Overview"
import SettingsPage from "@/pages/Settings"
import SyncRuns from "@/pages/SyncRuns"

vi.mock("@/api/health", () => ({
  healthApi: { readiness: vi.fn() },
  authApi: { identity: vi.fn() },
}))
vi.mock("@/api/sources", () => ({
  sourcesApi: { list: vi.fn(), documents: vi.fn() },
}))
vi.mock("@/api/sync", () => ({
  syncApi: { allRuns: vi.fn(), trigger: vi.fn(), history: vi.fn() },
}))
vi.mock("@/api/ui", () => ({
  uiApi: {
    overview: vi.fn(),
    activeIndex: vi.fn(),
    settings: vi.fn(),
    evaluations: vi.fn(),
    trace: vi.fn(),
  },
}))
vi.mock("@/hooks/useIdentity", () => ({ useIdentity: vi.fn() }))

const user: Identity = {
  user_id: "user_a",
  tenant_id: "tenant-a",
  roles: ["USER"],
  can_sync: false,
  is_admin: false,
  auth_enabled: true,
}
const operator: Identity = { ...user, user_id: "operator_a", roles: ["OPERATOR"], can_sync: true }

const activeIndex = {
  model: "qwen3-embedding:4b",
  model_key: "qwen3-4b",
  dimension: 2560,
  output_dimension: 1024,
  backend: "ollama",
  fingerprint: "fingerprint-1234567890",
  alias: "kb_active",
  active_collection: "kb_chunks_qwen3",
  previous: null,
  rollback_available: false,
  migration_id: null,
  available: true,
}

function renderWithClient(element: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useIdentity).mockReturnValue({ data: user } as ReturnType<typeof useIdentity>)
  vi.mocked(sourcesApi.list).mockResolvedValue([])
  vi.mocked(sourcesApi.documents).mockResolvedValue([])
  vi.mocked(syncApi.allRuns).mockResolvedValue([])
  vi.mocked(syncApi.trigger).mockResolvedValue({
    source_type: "filesystem",
    status: "success",
    run_id: 1,
    error: null,
    stats: null,
    trace_id: null,
  })
})

describe("console page regression states", () => {
  it("renders degraded health and unavailable counts without fake values", async () => {
    vi.mocked(uiApi.overview).mockResolvedValue({
      tenant_id: "tenant-a",
      document_count: 0,
      chunk_count: null,
      chunk_count_complete: false,
      source_count: 0,
      sources: [],
      recent_runs: [],
      active_index: { ...activeIndex, active_collection: null, available: false },
      security: {
        auth_enabled: true,
        tenant_isolation: true,
        mandatory_acl: true,
        tenant_id: "tenant-a",
        roles: ["USER"],
      },
    })
    vi.mocked(healthApi.readiness).mockResolvedValue({
      ready: false,
      checks: { qdrant: false, ollama: true },
      detail: {},
      active_collection: "",
      active_alias: "kb_active",
      configured_model: "qwen3-embedding:4b",
      configured_dimension: 1024,
    })

    renderWithClient(<Overview />)
    expect(await screen.findByText("degraded")).toBeInTheDocument()
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
    expect(screen.getByText(/Live index state unavailable/)).toBeInTheDocument()
  })

  it("renders an empty tenant-scoped Knowledge state and real returned metadata", async () => {
    renderWithClient(<Knowledge />)
    expect(await screen.findByText("No sources configured for your tenant")).toBeInTheDocument()

    vi.mocked(sourcesApi.list).mockResolvedValue([
      { source_type: "filesystem", document_count: 1, is_running: false },
    ])
    vi.mocked(sourcesApi.documents).mockResolvedValue([
      {
        tenant_id: "tenant-a",
        source_type: "filesystem",
        source_id: "tenant-a.md",
        content_hash: "hash-a",
        version: 2,
        status: "healthy",
        chunk_count: null,
        pipeline_fingerprint: null,
        last_synced_at: new Date().toISOString(),
      },
    ])
    renderWithClient(<Knowledge />)
    fireEvent.click(await screen.findByRole("button", { name: /filesystem/i }))
    expect(await screen.findByText("tenant-a.md")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("keeps sync action hidden for USER and visible for OPERATOR", async () => {
    vi.mocked(sourcesApi.list).mockResolvedValue([
      { source_type: "filesystem", document_count: 1, is_running: false },
    ])
    renderWithClient(<SyncRuns />)
    expect(await screen.findByText("Sync requires OPERATOR")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Sync now/i })).not.toBeInTheDocument()

    vi.mocked(useIdentity).mockReturnValue({ data: operator } as ReturnType<typeof useIdentity>)
    renderWithClient(<SyncRuns />)
    expect(await screen.findByRole("button", { name: /Sync now/i })).toBeInTheDocument()
  })

  it("renders an empty sync history and a successful row detail", async () => {
    vi.mocked(sourcesApi.list).mockResolvedValue([])
    renderWithClient(<SyncRuns />)
    expect(await screen.findByText("No sync runs yet")).toBeInTheDocument()

    vi.mocked(syncApi.allRuns).mockResolvedValue([
      {
        id: 7,
        source_type: "filesystem",
        trigger: "manual",
        status: "success",
        started_at: "2026-08-26T08:00:00Z",
        finished_at: "2026-08-26T08:00:02Z",
        files_processed: 1,
        files_skipped: 0,
        files_deleted: 0,
        chunks_upserted: 3,
        error_message: null,
        trace_id: null,
      },
    ])
    renderWithClient(<SyncRuns />)
    fireEvent.click(await screen.findByText("+1 ~0 -0"))
    expect(await screen.findByText("Run #7 · filesystem")).toBeInTheDocument()
    expect(screen.getAllByText("success").length).toBeGreaterThanOrEqual(2)
  })

  it("renders real evaluation metrics and explicit future metric state", async () => {
    vi.mocked(uiApi.evaluations).mockResolvedValue({
      baseline: {
        config: "qwen3-4b@1024",
        source: "artifacts/embedding-benchmark-sprint21/stability.json",
        metrics: [{ key: "recall", label: "Recall@5", value: 0.963, stddev: 0.01, runs: 10 }],
      },
      migration_quality_gate: null,
      security_validation: null,
      prompt_injection: {
        source: "artifacts/security-sprint25/adversarial-results.json",
        prompt_version: "v3",
        mode: "strict",
        case_count: 82,
        metrics: {
          injection_success_rate: 0,
          citation_spoof_success_rate: 0,
          citation_suppression_success_rate: 0,
          unauthorized_citation_rate: 0,
          cross_tenant_exfiltration_rate: 0,
          benign_answer_success_rate: 1,
        },
        breakdown: {},
        available: true,
      },
      reranker_decision: null,
      timeline: [],
      available: true,
    })
    renderWithClient(<Evaluations />)
    expect(await screen.findByText("0.9630")).toBeInTheDocument()
    expect(screen.getByText("Injection success rate")).toBeInTheDocument()
    expect(screen.getAllByText("0.0000").length).toBeGreaterThan(0)
    expect(screen.getByText("Faithfulness — not yet measured")).toBeInTheDocument()
  })

  it("renders active pipeline data and disabled rollback state", async () => {
    vi.mocked(uiApi.settings).mockResolvedValue({
      active_pipeline: activeIndex,
      retrieval: {
        rerank_candidate_k: 20,
        rerank_top_n: 5,
        reranker_enabled: true,
        reranker_backend: "sentence-transformers",
        sparse_model: "Qdrant/bm25",
        reranker_model: "BAAI/bge-reranker-v2-m3",
        fusion: "RRF",
      },
      authentication: { enabled: true, scheme: "bearer", roles: ["USER", "OPERATOR", "ADMIN"] },
      security: {
        prompt_policy_version: "answer_v3",
        untrusted_context_enabled: true,
        validation_mode: "fast",
      },
      integrations: {
        qdrant_url: "http://localhost:6333",
        ollama_base_url: "http://localhost:11434",
        otel_endpoint: "http://localhost:4317",
        generation_provider: "ollama",
        generation_model: "qwen2.5:7b-instruct",
      },
    })
    renderWithClient(<SettingsPage />)
    expect(await screen.findByText("qwen3-4b@1024")).toBeInTheDocument()
    expect(screen.getByText("BAAI/bge-reranker-v2-m3")).toBeInTheDocument()
    expect(screen.getByText("disabled")).toBeInTheDocument()
    expect(screen.getByText("Fast")).toBeInTheDocument()
    expect(screen.getByText("Post-stream validation")).toBeInTheDocument()
    expect(screen.getByText(/not exposed as a control/)).toBeInTheDocument()
  })

  it("renders explicit unauthenticated and forbidden UI states", async () => {
    const { ErrorState } = await import("@/components/ErrorState")
    render(
      <>
        <ErrorState kind="unauthenticated" />
        <ErrorState kind="forbidden" />
      </>,
    )
    await waitFor(() => {
      expect(screen.getByText("Not signed in")).toBeInTheDocument()
      expect(screen.getByText("Not authorized")).toBeInTheDocument()
    })
  })
})
