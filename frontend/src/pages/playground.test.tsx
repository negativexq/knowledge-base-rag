import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
    expect(screen.getByText("Kept question?")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Jump to E1.S2 in source 1" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "New chat" }))
    expect(sessionStorage.length).toBe(0)
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
})
