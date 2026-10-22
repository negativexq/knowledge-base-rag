import { MemoryRouter } from "react-router-dom"
import { RecentConversations } from "@/components/RecentConversations"
import { WorkspaceCommandsProvider } from "@/components/WorkspaceCommandsProvider"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, beforeEach, it, vi } from "vitest"

import { chatApi } from "@/api/chat"
import { uiApi } from "@/api/ui"
import type { Identity } from "@/api/types"
import { useIdentity } from "@/hooks/useIdentity"
import Playground from "@/pages/Playground"
import { readResearchSessions, researchScope } from "@/lib/research"
import { resetResearchRuns } from "@/lib/researchRuns"
import { act } from "@testing-library/react"

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

function renderPlayground(withSidebar = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><WorkspaceCommandsProvider>
        {withSidebar && <RecentConversations scope={researchScope(identity)} />}
        <Playground />
      </WorkspaceCommandsProvider></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Playground evidence flow", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetResearchRuns()
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

  it("opens supporting evidence with its passage, location and answer citation", async () => {
    renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "How should we deploy?" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    const trigger = await screen.findByRole("button", { name: "Supporting evidence 1" })
    fireEvent.click(trigger)
    const inspector = screen.getByRole("complementary", { name: "Evidence inspector" })
    expect(inspector).toHaveStyle({ width: "420px" })
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(within(inspector).getByRole("button", { name: "View source 1: runbook" })).toHaveAttribute("aria-expanded", "true")
    expect(within(inspector).getByText(/Page 1/)).toBeInTheDocument()
    expect(within(inspector).getByText("Deploy safely.")).toBeInTheDocument()
    const relation = within(inspector).getByRole("region", { name: "Citation relationship for source 1" })
    expect(relation).toHaveTextContent("[s.filesystem:runbook/1/0]")
    expect(relation).toHaveTextContent("Answer")
    fireEvent.click(within(inspector).getByRole("button", { name: "Close evidence inspector" }))
    expect(screen.queryByRole("complementary", { name: "Evidence inspector" })).not.toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "Question" })).toBeInTheDocument()
  })

  it("keeps research uncluttered and reveals engineering detail in Inspect", () => {
    renderPlayground()
    expect(screen.queryByRole("complementary", { name: "Evidence inspector" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }))
    expect(screen.getByRole("tab", { name: "Retrieval" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Security" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Research" }))
    expect(screen.queryByRole("complementary", { name: "Evidence inspector" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }))
    expect(screen.getByRole("tab", { name: "Why" })).toBeInTheDocument()
    expect(screen.queryByRole("tab", { name: "Security" })).not.toBeInTheDocument()
  })

  it("opens the evidence belonging to an earlier answer after a follow-up", async () => {
    renderPlayground()
    const input = screen.getByRole("textbox", { name: "Question" })
    fireEvent.change(input, { target: { value: "First question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByRole("button", { name: "Jump to source 1" })
    vi.mocked(chatApi.ask).mockImplementationOnce(async (_q, _h, handlers) => {
      handlers.onSources([])
      handlers.onToken("A different answer without sources.")
      handlers.onDone()
    })
    fireEvent.change(input, { target: { value: "Second question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByText("A different answer without sources.")
    fireEvent.click(screen.getByRole("button", { name: "Jump to source 1" }))
    expect(screen.getByRole("button", { name: "View source 1: runbook" })).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Deploy safely.")).toBeInTheDocument()
  })

  it("renames, stars and reopens saved research after starting a new session", async () => {
    renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "Deployment investigation" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByRole("button", { name: "Jump to source 1" })
    fireEvent.click(screen.getByRole("button", { name: "History" }))
    fireEvent.click(screen.getByRole("button", { name: "Rename Deployment investigation" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Research title" }), { target: { value: "Release notes" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))
    fireEvent.click(screen.getByRole("button", { name: "Star Release notes" }))
    expect(screen.getByRole("button", { name: "Unstar Release notes" })).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(screen.getByRole("button", { name: "Close research history" }))
    fireEvent.click(screen.getByRole("button", { name: "New chat" }))
    expect(screen.queryByText("Deployment investigation")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "History" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Search research history" }), { target: { value: "Deployment investigation" } })
    fireEvent.click(screen.getByRole("button", { name: /Release notes.*1 question/ }))
    expect(screen.getByText("Deployment investigation")).toBeInTheDocument()
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]).toMatchObject({ title: "Release notes", starred: true }))
    fireEvent.click(screen.getByRole("button", { name: "History" }))
    fireEvent.click(screen.getByRole("button", { name: "Remove Release notes" }))
    expect(screen.queryByRole("button", { name: /Release notes.*1 question/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Undo" }))
    expect(screen.getByRole("button", { name: /Release notes.*1 question/ })).toBeInTheDocument()
  })

  it("keeps pinned evidence across reloads without making another chat request", async () => {
    const first = renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "Pin this research" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    fireEvent.click(await screen.findByRole("button", { name: "Jump to source 1" }))
    fireEvent.click(screen.getByRole("button", { name: "Pin source 1" }))
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]?.pins).toHaveLength(1))
    first.unmount()
    renderPlayground()
    fireEvent.click(screen.getByRole("button", { name: "Pinned evidence (1)" }))
    expect(screen.getByText("Deploy safely.")).toBeInTheDocument()
    expect(chatApi.ask).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole("button", { name: "Unpin evidence from runbook" }))
    expect(screen.getByText("No pinned evidence")).toBeInTheDocument()
  })

  it("does not expose saved research when the identity changes", async () => {
    const view = renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "Private tenant-a question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByRole("button", { name: "Jump to source 1" })
    await waitFor(() => expect(readResearchSessions(researchScope(identity))).toHaveLength(1))
    vi.mocked(useIdentity).mockReturnValue({ data: { ...identity, tenant_id: "tenant-b", user_id: "user_b" } } as ReturnType<typeof useIdentity>)
    view.rerender(<QueryClientProvider client={new QueryClient()}><Playground /></QueryClientProvider>)
    expect(screen.queryByText("Private tenant-a question")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "History" }))
    expect(screen.getByText("Your completed research will appear here.")).toBeInTheDocument()
  })

  it("keeps research usable and reports when browser persistence fails", async () => {
    const write = vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new DOMException("Storage full", "QuotaExceededError") })
    try {
      renderPlayground()
      expect(await screen.findByText(/Browser storage is unavailable or full/)).toBeInTheDocument()
      fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "In-memory research" } })
      fireEvent.click(screen.getByRole("button", { name: "Ask" }))
      expect(await screen.findByRole("button", { name: "Jump to source 1" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Export research as Markdown" })).toBeEnabled()
    } finally { write.mockRestore() }
  })

  it("downloads the current completed research as a Markdown file", async () => {
    const originalURL = URL
    const createObjectURL = vi.fn(() => "blob:local-research")
    vi.stubGlobal("URL", class extends originalURL { static createObjectURL = createObjectURL; static revokeObjectURL = vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    try {
      renderPlayground()
      const exportButton = screen.getByRole("button", { name: "Export research as Markdown" })
      expect(exportButton).toBeDisabled()
      fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "Export deployment" } })
      fireEvent.click(screen.getByRole("button", { name: "Ask" }))
      await screen.findByRole("button", { name: "Jump to source 1" })
      fireEvent.click(exportButton)
      expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
      expect(click).toHaveBeenCalledOnce()
      expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe("Export deployment.md")
    } finally { click.mockRestore(); vi.unstubAllGlobals() }
  })

  it("shows saved conversations below Research and manages them through the three-dot menu", async () => {
    const first = renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "An older conversation" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await screen.findByRole("button", { name: "Jump to source 1" })
    await waitFor(() => expect(readResearchSessions(researchScope(identity))).toHaveLength(1))
    first.unmount()
    renderPlayground(true)
    let menu = screen.getByRole("list", { name: "Recent conversations" })
    expect(within(menu).getByRole("button", { name: "Open conversation: An older conversation" })).toBeInTheDocument()
    fireEvent.keyDown(within(menu).getByRole("button", { name: "Conversation options: An older conversation" }), { key: "Enter" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "Rename" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Conversation name" }), { target: { value: "Rollout review" } })
    fireEvent.click(screen.getByRole("button", { name: "Save name" }))
    expect(within(menu).getByRole("button", { name: "Open conversation: Rollout review" })).toBeInTheDocument()
    fireEvent.keyDown(within(menu).getByRole("button", { name: "Conversation options: Rollout review" }), { key: "Enter" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "Star" }))
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]?.starred).toBe(true))
    fireEvent.keyDown(within(menu).getByRole("button", { name: "Conversation options: Rollout review" }), { key: "Enter" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "Pin to top" }))
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]?.pinned).toBe(true))
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]).toMatchObject({ title: "Rollout review", starred: true, pinned: true }))
    fireEvent.keyDown(within(menu).getByRole("button", { name: "Conversation options: Rollout review" }), { key: "Enter" })
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete conversation" }))
    await waitFor(() => expect(screen.queryByRole("button", { name: "Open conversation: Rollout review" })).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Undo delete" }))
    menu = await screen.findByRole("list", { name: "Recent conversations" })
    fireEvent.click(within(menu).getByRole("button", { name: "Open conversation: Rollout review" }))
    expect(within(screen.getByRole("region", { name: "Conversation" })).getByText("An older conversation")).toBeInTheDocument()
    fireEvent.click(within(menu.parentElement!).getByRole("button", { name: "New chat" }))
    expect(within(screen.getByRole("region", { name: "Conversation" })).queryByText("An older conversation")).not.toBeInTheDocument()
    expect(readResearchSessions(researchScope(identity))).toHaveLength(1)
  })

  it("persists linked notes and reopens their source after a reload", async () => {
    const first = renderPlayground()
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "A question for notes" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    fireEvent.click(await screen.findByRole("button", { name: "Jump to source 1" }))
    fireEvent.click(screen.getByRole("button", { name: "Pin source 1" }))
    fireEvent.click(screen.getByRole("button", { name: "Pinned evidence (1)" }))
    fireEvent.click(screen.getByRole("button", { name: "Add linked note" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Research note" }), { target: { value: "Follow up with the deployment owner." } })
    fireEvent.click(screen.getByRole("button", { name: "Save note" }))
    await waitFor(() => expect(readResearchSessions(researchScope(identity))[0]?.notes).toHaveLength(1))
    first.unmount()
    renderPlayground()
    expect(screen.getByText("Follow up with the deployment owner.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "runbook" }))
    expect(screen.getByRole("button", { name: "View source 1: runbook" })).toHaveAttribute("aria-expanded", "true")
  })

  it("remembers workspace layout while explicit view links take precedence", () => {
    const first = renderPlayground()
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }))
    fireEvent.click(screen.getByRole("tab", { name: "Why" }))
    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize evidence inspector" }), { key: "ArrowLeft" })
    first.unmount()
    window.history.replaceState(null, "", "/playground")
    const second = renderPlayground()
    expect(screen.getByRole("button", { name: "Inspect" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("tab", { name: "Why" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("separator", { name: "Resize evidence inspector" })).toHaveAttribute("aria-valuenow", "440")
    second.unmount()
    window.history.replaceState(null, "", "/playground?mode=research&panel=notes&inspector=open")
    renderPlayground()
    expect(screen.getByRole("button", { name: "Research" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true")
  })

  it("aggregates the real stream and focuses the cited source card", async () => {
    renderPlayground()
    fireEvent.change(screen.getByPlaceholderText("Ask anything…"), {
      target: { value: "How do I deploy?" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))

    const citation = await screen.findByRole("button", { name: "Jump to source 1" })
    expect(screen.getByText("Answer")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Evidence/ })).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(citation)
    const sourceCard = screen.getByRole("button", { name: "View source 1: runbook" }).parentElement
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
    expect(within(screen.getByRole("region", { name: "Conversation" })).queryByText("How do I deploy?")).not.toBeInTheDocument()

    fireEvent.change(input, { target: { value: "Unrelated question" } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
    await within(screen.getByRole("region", { name: "Conversation" })).findByText("Unrelated question")
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
    const card = screen.getByRole("button", { name: "View source 1: nimbus_cli_md" }).parentElement
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

describe("Playground answer confidence and why-this-answer", () => {
  const unit = {
    support_id: "E1.S2",
    source_rank: 1,
    source_type: "filesystem",
    source_id: "nimbus_cli_md",
    section_label: "Senkronizasyon Komutları > Çakışma Çözümü",
    text: "Yerel sürümü zorla yüklemek için --force-local bayrağı kullanılır.",
  }

  function stream(options: {
    answer: string
    security: Record<string, unknown>
    metadata?: Record<string, unknown>
  }) {
    return async (_question: string, _history: unknown, handlers: Parameters<typeof chatApi.ask>[2]) => {
      handlers.onSources([
        {
          rank: 1,
          source_type: "filesystem",
          source_id: "nimbus_cli_md",
          citation_location: "Senkronizasyon Komutları/Çakışma Çözümü",
          page_number: 1,
          paragraph_index: 5,
          heading_path: ["Senkronizasyon Komutları", "Çakışma Çözümü"],
          snippet: unit.text,
          score: 0.9,
          document_version: "v1",
          tenant_id: "tenant-a",
          visibility: "tenant",
        },
      ])
      handlers.onRetrieval({
        stages: [
          {
            name: "query_rewrite",
            duration_ms: 900,
            candidates_in: null,
            candidates_out: null,
            top_score: null,
            detail: { outcome: "REWRITTEN", history_turns: 2, search_query: "Çakışmada yerel sürüm nasıl yüklenir?" },
          },
          { name: "hybrid_retrieval", duration_ms: 30, candidates_in: null, candidates_out: 24, top_score: null, detail: {} },
          { name: "rerank", duration_ms: 7000, candidates_in: 24, candidates_out: 5, top_score: 0.9, detail: {} },
        ],
        authorization: { acl_applied: true, tenant_id: "tenant-a", is_system_context: false, user_filters_applied: false },
        total_duration_ms: 8000,
        reranker: null,
        security: {
          prompt_policy_version: null,
          untrusted_context_enabled: true,
          security_validation_mode: "strict",
          output_policy_passed: null,
          output_policy_violations: [],
        },
      })
      handlers.onMetadata({
        prompt_version: "v1",
        trace_id: "trace-1",
        support_units: [unit],
        prompt_fit: { prompt_tokens: 2697, prompt_token_limit: 3072, units_sent: 25, units_dropped: 3 },
        ...options.metadata,
      })
      handlers.onToken(options.answer)
      handlers.onSecurity?.(options.security)
      handlers.onDone()
    }
  }

  const verified = {
    passed: true,
    abstain: false,
    validator_failure_codes: [],
    generation: { done_reason: "stop", prompt_tokens: 2702, output_tokens: 41 },
  }

  async function ask(question = "Çakışmada yerel sürüm?") {
    fireEvent.change(screen.getByPlaceholderText("Ask anything…"), { target: { value: question } })
    fireEvent.click(screen.getByRole("button", { name: "Ask" }))
  }

  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    vi.mocked(useIdentity).mockReturnValue({ data: identity } as ReturnType<typeof useIdentity>)
  })

  it("renders inline code, bold text and lists in the answer", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      stream({
        answer: "Use **one** flag:\n\n- `--force-local` uploads yours [E1.S2]\n- `--force-remote` keeps theirs",
        security: verified,
      }),
    )
    renderPlayground()
    await ask()

    expect(await screen.findByText("--force-local", { selector: "code" })).toBeInTheDocument()
    expect(screen.getByText("one", { selector: "strong" })).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByRole("button", { name: "Jump to E1.S2 in source 1" })).toBeInTheDocument()
  })

  it("previews the cited passage on hover", async () => {
    vi.mocked(chatApi.ask).mockImplementation(stream({ answer: "Use --force-local. [E1.S2]", security: verified }))
    renderPlayground()
    await ask()

    const chip = await screen.findByRole("button", { name: "Jump to E1.S2 in source 1" })
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument()
    fireEvent.pointerEnter(chip)
    const preview = await screen.findByRole("tooltip", { name: "Preview of E1.S2" })
    expect(preview).toHaveTextContent("Senkronizasyon Komutları > Çakışma Çözümü")
    expect(preview).toHaveTextContent(unit.text)
    fireEvent.pointerLeave(chip)
    await waitFor(() => expect(screen.queryByRole("tooltip", { name: "Preview of E1.S2" })).not.toBeInTheDocument())
  })

  it("copies the answer", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    vi.mocked(chatApi.ask).mockImplementation(stream({ answer: "Use --force-local. [E1.S2]", security: verified }))
    renderPlayground()
    await ask()

    fireEvent.click(await screen.findByRole("button", { name: "Copy answer" }))

    expect(writeText).toHaveBeenCalledWith("Use --force-local. [E1.S2]")
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument()
  })

  it("explains why an answer was not verified", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      stream({
        answer: "I could not produce a verified answer from the documents.",
        security: {
          passed: false,
          abstain: true,
          validator_failure_codes: ["OUTPUT_TRUNCATED"],
          generation: { done_reason: "length", prompt_tokens: 4079, output_tokens: 17 },
        },
      }),
    )
    renderPlayground()
    await ask()

    expect(await screen.findByText("Citation validation failed")).toBeInTheDocument()
    expect(screen.getByText(/ran out of room/)).toBeInTheDocument()
  })

  it("says when the model was not called for lack of evidence", async () => {
    vi.mocked(chatApi.ask).mockImplementation(
      stream({
        answer: "I could not find this in the document.",
        security: { passed: true, abstain: true, validator_failure_codes: [] },
        metadata: { generation_skipped: "EMPTY_RERANK_RESULT", support_units: [], prompt_fit: null },
      }),
    )
    renderPlayground()
    await ask()

    expect(await screen.findByText("No matching evidence")).toBeInTheDocument()
  })

  it("walks through why this answer came out the way it did", async () => {
    vi.mocked(chatApi.ask).mockImplementation(stream({ answer: "Use --force-local. [E1.S2]", security: verified }))
    renderPlayground()
    await ask()
    await screen.findByText("Citation integrity verified")

    fireEvent.click(screen.getByRole("button", { name: /Evidence/ }))
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Why" }))
    fireEvent.click(screen.getByRole("tab", { name: "Why" }))

    const panel = await screen.findByRole("list", { name: "Why this answer" })
    expect(panel).toHaveTextContent("Searched as: Çakışmada yerel sürüm nasıl yüklenir?")
    expect(panel).toHaveTextContent("24 candidates → 5 after reranking")
    expect(panel).toHaveTextContent("2,697 / 3,072 prompt tokens")
    expect(panel).toHaveTextContent("25 passages sent, 3 lowest-ranked left out to fit")
    expect(panel).toHaveTextContent("Finished normally · 41 output tokens")
    expect(panel).toHaveTextContent("Citation integrity verified")
  })

  it("keeps the conversation across a reload and New chat clears it", async () => {
    vi.mocked(chatApi.ask).mockImplementation(stream({ answer: "Use --force-local. [E1.S2]", security: verified }))
    const first = renderPlayground()
    await ask("Kept question?")
    await screen.findByText("Citation integrity verified")
    first.unmount()

    renderPlayground()
    expect(within(screen.getByRole("region", { name: "Conversation" })).getByText("Kept question?")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Jump to E1.S2 in source 1" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "New chat" }))
    await waitFor(() => expect(sessionStorage.length).toBe(0))
  })

  it("composes multi-line questions: Enter asks, Shift+Enter adds a line", async () => {
    vi.mocked(chatApi.ask).mockImplementation(stream({ answer: "Use --force-local. [E1.S2]", security: verified }))
    renderPlayground()
    const composer = screen.getByRole("textbox", { name: "Question" })

    fireEvent.change(composer, { target: { value: "First line" } })
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: true })
    expect(chatApi.ask).not.toHaveBeenCalled()

    fireEvent.change(composer, { target: { value: "First line\nSecond line" } })
    fireEvent.keyDown(composer, { key: "Enter" })

    expect(vi.mocked(chatApi.ask).mock.calls[0][0]).toBe("First line\nSecond line")
    expect(await screen.findByText("Citation integrity verified")).toBeInTheDocument()
  })
  it("continues after clarification and retains the user's reply", async () => {
    vi.mocked(chatApi.ask).mockImplementationOnce(async (_question, _history, handlers) => {
      handlers.onProgress?.({ id: "s1", operation: "search", status: "completed" })
      handlers.onClarification?.({ question: "Which platform?", options: ["Linux", "Windows"] })
      handlers.onDone()
    })
    renderPlayground()
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "How do I install it?" } })
    fireEvent.keyDown(screen.getByLabelText("Question"), { key: "Enter" })
    fireEvent.click(await screen.findByRole("button", { name: "Linux" }))
    await waitFor(() => expect(chatApi.ask).toHaveBeenCalledTimes(2))
    expect(vi.mocked(chatApi.ask).mock.calls[1][0]).toBe("How do I install it?")
    expect(vi.mocked(chatApi.ask).mock.calls[1][4]).toEqual({ clarification: { question: "Which platform?", answer: "Linux" } })
    expect(await screen.findByText("Clarification: Linux")).toBeInTheDocument()
  })

  it("aborts a running request and ignores late model events", async () => {
    let handlers: Parameters<typeof chatApi.ask>[2] | undefined
    vi.mocked(chatApi.ask).mockImplementation(async (_question, _history, incoming) => {
      handlers = incoming
      incoming.onProgress?.({ id: "s1", operation: "search", status: "running" })
    })
    renderPlayground()
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Investigate" } })
    fireEvent.keyDown(screen.getByLabelText("Question"), { key: "Enter" })
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }))
    expect(vi.mocked(chatApi.ask).mock.calls[0][3]?.aborted).toBe(true)
    handlers!.onToken("Late answer that must not appear")
    expect(screen.queryByText("Late answer that must not appear")).not.toBeInTheDocument()
    expect(screen.getByText("Stopped")).toBeInTheDocument()
  })

  it("keeps research running in the background while another session is open", async () => {
    let handlers: Parameters<typeof chatApi.ask>[2] | undefined
    vi.mocked(chatApi.ask).mockImplementation(async (_question, _history, incoming) => { handlers = incoming })
    renderPlayground()
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Long investigation" } })
    fireEvent.keyDown(screen.getByLabelText("Question"), { key: "Enter" })
    await screen.findByRole("button", { name: "Cancel" })
    fireEvent.click(screen.getByRole("button", { name: "New chat" }))

    expect(vi.mocked(chatApi.ask).mock.calls[0][3]?.aborted).toBe(false)
    expect(screen.getByText("1 research is still running")).toBeInTheDocument()
    act(() => handlers!.onToken("Background answer"))
    fireEvent.click(screen.getByRole("button", { name: "Long investigation" }))
    expect(await screen.findByText("Background answer")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "New chat" }))
    act(() => handlers!.onDone())
    await waitFor(() => expect(readResearchSessions(researchScope(identity)).flatMap((session) => session.turns.map((turn) => turn.answer))).toEqual(["Background answer"]))
  })

  it("does not cancel research when the workspace is left", async () => {
    let handlers: Parameters<typeof chatApi.ask>[2] | undefined
    vi.mocked(chatApi.ask).mockImplementation(async (_question, _history, incoming) => { handlers = incoming })
    const { unmount } = renderPlayground()
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Leave and come back" } })
    fireEvent.keyDown(screen.getByLabelText("Question"), { key: "Enter" })
    await screen.findByRole("button", { name: "Cancel" })
    unmount()

    expect(vi.mocked(chatApi.ask).mock.calls[0][3]?.aborted).toBe(false)
    handlers!.onToken("Finished while away")
    handlers!.onDone()
    const [session] = readResearchSessions(researchScope(identity))
    expect(session.turns[0]).toMatchObject({ question: "Leave and come back", answer: "Finished while away", streaming: false })
  })
})
