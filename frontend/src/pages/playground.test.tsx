import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, beforeEach, it, vi } from "vitest"

import { chatApi } from "@/api/chat"
import { uiApi } from "@/api/ui"
import type { Identity } from "@/api/types"
import { useIdentity } from "@/hooks/useIdentity"
import Playground from "@/pages/Playground"

vi.mock("@/api/chat", () => ({ chatApi: { ask: vi.fn() } }))
vi.mock("@/api/ui", () => ({ uiApi: { trace: vi.fn() } }))
vi.mock("@/hooks/useIdentity", () => ({ useIdentity: vi.fn() }))

const identity: Identity = {
  user_id: "user_a",
  tenant_id: "tenant-a",
  roles: ["USER"],
  can_sync: false,
  is_admin: false,
  auth_enabled: true,
}

function renderPlayground() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Playground />
    </QueryClientProvider>,
  )
}

describe("Playground evidence flow", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useIdentity).mockReturnValue({ data: identity } as ReturnType<typeof useIdentity>)
    vi.mocked(uiApi.trace).mockResolvedValue({
      trace_id: "trace-1",
      available: false,
      jaeger_url: "http://localhost:16686",
      spans: [],
    })
    vi.mocked(chatApi.ask).mockImplementation(async (_question, handlers) => {
      handlers.onSources([
        {
          rank: 1,
          source_type: "filesystem",
          source_id: "runbook",
          citation_location: "1/0",
          page_number: 1,
          paragraph_index: 0,
          heading_path: [],
          snippet: "Deploy safely.",
          score: 0.24,
          document_version: "v1",
          tenant_id: "tenant-a",
          visibility: "tenant",
        },
      ])
      handlers.onRetrieval({
        stages: [],
        authorization: {
          acl_applied: true,
          tenant_id: "tenant-a",
          is_system_context: false,
          user_filters_applied: false,
        },
        total_duration_ms: 0,
      })
      handlers.onMetadata({ prompt_version: "v1", trace_id: "trace-1" })
      handlers.onToken("Answer [s.filesystem:runbook/1/0]")
      handlers.onGrounding({
        grounded: true,
        has_citations: true,
        citations_found: [["filesystem", "runbook.md", "1/0"]],
        ungrounded_citations: [],
      })
      handlers.onDone()
    })
  })

  it("aggregates the real stream and focuses the cited source card", async () => {
    renderPlayground()
    fireEvent.change(screen.getByPlaceholderText("Ask anything…"), {
      target: { value: "How do I deploy?" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))

    const citation = await screen.findByRole("button", { name: "Jump to source 1" })
    expect(screen.getByText("Answer")).toBeInTheDocument()
    expect(screen.getByText("runbook")).toBeInTheDocument()

    fireEvent.click(citation)
    const sourceCard = screen.getByText("runbook").closest("[class*='border']")
    expect(sourceCard).toHaveClass("border-[var(--color-accent)]")
  })
})
