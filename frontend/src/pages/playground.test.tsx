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
    vi.mocked(chatApi.ask).mockImplementation(async (_question, _history, handlers) => {
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

  it("sends earlier completed turns as history and New chat starts over", async () => {
    renderPlayground()
    const input = screen.getByPlaceholderText("Ask anything…")

    fireEvent.change(input, { target: { value: "How do I deploy?" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByRole("button", { name: "Jump to source 1" })

    fireEvent.change(input, { target: { value: "And roll back?" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByText("And roll back?")

    const calls = vi.mocked(chatApi.ask).mock.calls
    expect(calls[0][1]).toEqual([])
    expect(calls[1][0]).toBe("And roll back?")
    expect(calls[1][1]).toEqual([
      { role: "user", content: "How do I deploy?" },
      { role: "assistant", content: "Answer [s.filesystem:runbook/1/0]" },
    ])

    fireEvent.click(screen.getByRole("button", { name: "New chat" }))
    expect(screen.queryByText("How do I deploy?")).not.toBeInTheDocument()

    fireEvent.change(input, { target: { value: "Unrelated question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByText("Unrelated question")
    expect(vi.mocked(chatApi.ask).mock.calls[2][1]).toEqual([])
  })

  it("leaves failed turns out of the history", async () => {
    vi.mocked(chatApi.ask).mockImplementationOnce(async (_question, _history, handlers) => {
      handlers.onError("Request failed (500).")
    })
    renderPlayground()
    const input = screen.getByPlaceholderText("Ask anything…")

    fireEvent.change(input, { target: { value: "Broken question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByText("Request failed (500).")

    fireEvent.change(input, { target: { value: "Second try" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByText("Second try")

    expect(vi.mocked(chatApi.ask).mock.calls[1][1]).toEqual([])
  })

  it("shows the standalone query a follow-up was searched as", async () => {
    vi.mocked(chatApi.ask).mockImplementationOnce(async (_question, _history, handlers) => {
      handlers.onRetrieval({
        stages: [
          {
            name: "query_rewrite",
            duration_ms: 812,
            candidates_in: null,
            candidates_out: null,
            top_score: null,
            detail: {
              outcome: "REWRITTEN",
              history_turns: 2,
              search_query: "How do I roll back a deploy?",
            },
          },
        ],
        authorization: {
          acl_applied: true,
          tenant_id: "tenant-a",
          is_system_context: false,
          user_filters_applied: false,
        },
        total_duration_ms: 0,
      })
      handlers.onDone()
    })
    renderPlayground()

    fireEvent.change(screen.getByPlaceholderText("Ask anything…"), {
      target: { value: "And roll back?" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))

    expect(await screen.findByText("Searched as: How do I roll back a deploy?")).toBeInTheDocument()
  })
})


describe("Playground support-ID citations", () => {
  function supportIdStream(security: Record<string, unknown>, answer: string) {
    return async (_question: string, _history: unknown, handlers: Parameters<typeof chatApi.ask>[2]) => {
      handlers.onSources([
        {
          rank: 1,
          source_type: "filesystem",
          source_id: "nimbus_cli_md",
          citation_location: "Kimlik Doğrulama/Token Süresi",
          page_number: 1,
          paragraph_index: 1,
          heading_path: ["Kimlik Doğrulama", "Token Süresi"],
          snippet: "Nimbus CLI pip ile kurulur.",
          score: 0.9,
          document_version: "v1",
          tenant_id: "tenant-a",
          visibility: "tenant",
        },
        {
          rank: 2,
          source_type: "filesystem",
          source_id: "nimbus_handbook_pdf",
          citation_location: "3/0",
          page_number: 3,
          paragraph_index: 0,
          heading_path: [],
          snippet: "Free accounts include 15GB of storage.",
          score: 0.4,
          document_version: "v1",
          tenant_id: "tenant-a",
          visibility: "tenant",
        },
      ])
      handlers.onMetadata({
        prompt_version: "v1",
        trace_id: "trace-1",
        support_units: [
          {
            support_id: "E1.S1",
            source_rank: 1,
            source_type: "filesystem",
            source_id: "nimbus_cli_md",
            section_label: "Kurulum",
            text: "Nimbus CLI pip ile kurulur.",
          },
          {
            support_id: "E1.S2",
            source_rank: 1,
            source_type: "filesystem",
            source_id: "nimbus_cli_md",
            section_label: "Kimlik Doğrulama > Token Süresi",
            text: "Erişim token'ları 90 gün geçerlidir.",
          },
        ],
      })
      handlers.onToken(answer)
      handlers.onSecurity?.(security)
      handlers.onDone()
    }
  }

  async function askQuestion() {
    renderPlayground()
    fireEvent.change(screen.getByPlaceholderText("Ask anything…"), {
      target: { value: "Token ne kadar geçerli?" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useIdentity).mockReturnValue({ data: identity } as ReturnType<typeof useIdentity>)
  })

  it("turns a support ID into a chip that opens the unit on its source card", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      supportIdStream(
        { passed: true, abstain: false, validator_failure_codes: [] },
        "Erişim token'ları 90 gün geçerlidir. [E1.S2]",
      ),
    )
    await askQuestion()

    const chip = await screen.findByRole("button", { name: "Jump to E1.S2 in source 1" })
    expect(screen.queryByText(/\[E1\.S2\]/)).not.toBeInTheDocument()
    expect(screen.getByText("Citation integrity verified")).toBeInTheDocument()

    fireEvent.click(chip)

    const passage = screen.getByRole("note", { name: "Cited passage E1.S2" })
    expect(passage).toHaveTextContent("Kimlik Doğrulama > Token Süresi")
    expect(passage).toHaveTextContent("Erişim token'ları 90 gün geçerlidir.")
    expect(passage).toHaveAttribute("data-highlighted", "true")
    const card = screen.getByText("nimbus_cli_md").closest("[class*='border']")
    expect(card).toHaveClass("border-[var(--color-accent)]")
    // Uncited units and sources stay unmarked.
    expect(screen.queryByRole("note", { name: "Cited passage E1.S1" })).not.toBeInTheDocument()
    expect(screen.getAllByText("cited")).toHaveLength(1)
  })

  it("shows a failed badge when the answer did not pass validation", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      supportIdStream(
        { passed: false, abstain: true, validator_failure_codes: ["OUTPUT_TRUNCATED"] },
        "I could not produce a verified answer from the documents.",
      ),
    )
    await askQuestion()

    expect(await screen.findByText("Citation validation failed")).toBeInTheDocument()
  })

  it("shows no badge for a clean not-found answer", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      supportIdStream(
        { passed: true, abstain: true, validator_failure_codes: [] },
        "I could not find this in the document.",
      ),
    )
    await askQuestion()

    await screen.findByText("I could not find this in the document.")
    expect(screen.queryByText("Citation integrity verified")).not.toBeInTheDocument()
    expect(screen.queryByText("Citation validation failed")).not.toBeInTheDocument()
  })
})
