import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { Identity, RetrievalReportPayload, RetrievedSource } from "@/api/types"
import { CitationChip } from "@/components/CitationChip"
import { RetrievalPipeline } from "@/components/RetrievalPipeline"
import { SecurityInspector } from "@/components/SecurityInspector"
import { SourceCard } from "@/components/SourceCard"
import { TraceWaterfall } from "@/components/TraceWaterfall"

const identity: Identity = {
  user_id: "user_a",
  tenant_id: "tenant-a",
  roles: ["USER"],
  can_sync: false,
  is_admin: false,
  auth_enabled: true,
}

const report: RetrievalReportPayload = {
  stages: [
    {
      name: "hybrid_retrieval",
      duration_ms: 4.2,
      candidates_in: null,
      candidates_out: 20,
      top_score: 0.24,
      detail: { fusion: "RRF", configured_prefetch_limit_per_branch: 40 },
    },
    {
      name: "rerank",
      duration_ms: 8,
      candidates_in: 20,
      candidates_out: 5,
      top_score: null,
      detail: {},
    },
  ],
  authorization: {
    acl_applied: true,
    tenant_id: "tenant-a",
    is_system_context: false,
    user_filters_applied: false,
  },
  security: {
    prompt_policy_version: "answer_v3",
    untrusted_context_enabled: true,
    security_validation_mode: "fast",
    output_policy_passed: null,
    output_policy_violations: [],
  },
  total_duration_ms: 12.2,
  reranker: {
    enabled: true,
    model: "BAAI/bge-reranker-v2-m3",
    backend: "sentence-transformers",
    candidate_k: 20,
    top_n: 5,
  },
  context: { retrieved_chunk_count: 5, top_context_tokens: null },
}

const source: RetrievedSource = {
  rank: 1,
  source_type: "markdown",
  source_id: "runbook.md",
  citation_location: "Operations/Deploy",
  page_number: null,
  paragraph_index: null,
  heading_path: ["Operations", "Deploy"],
  snippet: "Deploy safely.",
  score: null,
  document_version: "v1",
  tenant_id: "tenant-a",
  visibility: "private",
}

describe("Evidence Inspector", () => {
  it("renders real retrieval stages, missing metrics as —, and labels scores without confidence semantics", () => {
    render(<RetrievalPipeline report={report} />)
    expect(screen.getByText("Dense + sparse → RRF fusion")).toBeInTheDocument()
    expect(screen.getByText("Reranker")).toBeInTheDocument()
    expect(screen.getByText("RRF score: 0.240")).toBeInTheDocument()
    expect(screen.getByText("in: —")).toBeInTheDocument()
    expect(screen.getByText("stage score: —")).toBeInTheDocument()
    expect(screen.queryByText(/confidence|probability/i)).not.toBeInTheDocument()
  })

  it("renders ACL, tenant, role and enforcement flow", () => {
    render(<SecurityInspector report={report} identity={identity} />)
    expect(screen.getByText("Applied")).toBeInTheDocument()
    expect(screen.getByText("tenant-a")).toBeInTheDocument()
    expect(screen.getByText("USER")).toBeInTheDocument()
    expect(screen.getByText("mandatory ACL filter")).toBeInTheDocument()
    expect(screen.getByText("authorized candidates only")).toBeInTheDocument()
    expect(screen.getByText("Isolated")).toBeInTheDocument()
    expect(screen.getByText("answer_v3")).toBeInTheDocument()
    expect(screen.getByText(/^Fast/)).toBeInTheDocument()
    expect(screen.getByText("Post-stream validation")).toBeInTheDocument()
    expect(screen.getByText(/not yet measured/)).toBeInTheDocument()
  })

  it("renders a defensive source payload", () => {
    render(
      <SourceCard
        source={{ ...source, source_id: null, source_type: null, citation_location: null }}
        cited={false}
        highlighted={false}
      />,
    )
    expect(screen.getByText("unknown")).toBeInTheDocument()
    expect(screen.getByText("Deploy safely.")).toBeInTheDocument()
  })

  it("calls the focus handler for the clicked citation rank", () => {
    const onClick = vi.fn()
    render(<CitationChip rank={2} valid onClick={onClick} />)
    fireEvent.click(screen.getByRole("button", { name: "Jump to source 2" }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it("distinguishes a trace not indexed yet from a trace with spans", () => {
    const { rerender } = render(
      <TraceWaterfall trace={{ trace_id: "t1", available: false, jaeger_url: "http://jaeger", spans: [] }} />,
    )
    expect(screen.getByText("Trace not indexed yet")).toBeInTheDocument()
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument()

    rerender(
      <TraceWaterfall
        trace={{
          trace_id: "t1",
          available: true,
          jaeger_url: "http://jaeger",
          spans: [{ name: "chat_request", duration_ms: 10, offset_ms: 0 }],
        }}
      />,
    )
    expect(screen.getByText("chat_request")).toBeInTheDocument()
  })
})
