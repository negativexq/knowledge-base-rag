import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { researchApi } from "@/api/research"
import { sourcesApi } from "@/api/sources"
import { DocumentExplorer } from "@/components/DocumentExplorer"
import { ClarificationPrompt } from "@/components/ClarificationPrompt"
import { ComparisonComposer } from "@/components/ComparisonComposer"
import { ComparisonTable } from "@/components/ComparisonTable"
import { ResearchActivity } from "@/components/ResearchActivity"
import { AnswerFeedback } from "@/components/AnswerFeedback"
import type { ResearchTurn } from "@/lib/research"
import type { DocumentRecord, RetrievedSource } from "@/api/types"

vi.mock("@/api/research", () => ({ researchApi: { read: vi.fn(), feedback: vi.fn() } }))
vi.mock("@/api/sources", () => ({ sourcesApi: { documents: vi.fn() } }))

function wrap(children: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>)
}
const document = { source_type: "filesystem", source_id: "manual", document_version: "v1" }
const source = (rank: number, id: string): RetrievedSource => ({ rank, source_id: id, source_type: "filesystem", snippet: "Text", heading_path: [], page_number: 1, paragraph_index: 0, citation_location: "1/0", score: 1, document_version: "v1", tenant_id: "a", visibility: "tenant" })

beforeEach(() => vi.clearAllMocks())
describe("research workflow", () => {
  it("opens an unseen section and its neighbors through the scoped reader API", async () => {
    vi.mocked(researchApi.read).mockImplementation(async (request) => ({ document, has_more: false, scan_limited: false, next_offset: null,
      outline: request.action === "outline" ? [{ section_id: "setup", title: "Setup", page_number: 2, chunk_count: 1 }] : [],
      passages: request.action !== "outline" ? [{ chunk_id: "c2", text: "Install with TLS", page_number: 2, page_end: 2, section_id: "setup", heading_path: ["Setup"] }] : [],
      indexed_at: "2026-10-18T00:00:00Z", current_version: "v2",
    }))
    wrap(<DocumentExplorer document={document} />)
    fireEvent.click(await screen.findByRole("button", { name: "Setup · 1 passages" }))
    expect(await screen.findByText("Install with TLS")).toBeInTheDocument()
    expect(screen.getByText(/older document version/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Read surrounding passages" }))
    await waitFor(() => expect(researchApi.read).toHaveBeenLastCalledWith({ document, action: "neighbors", chunk_id: "c2" }))
  })

  it("offers clarification choices and accepts a custom reply", () => {
    const reply = vi.fn()
    render(<ClarificationPrompt clarification={{ question: "Which platform?", options: ["Linux"] }} disabled={false} onReply={reply} />)
    fireEvent.click(screen.getByRole("button", { name: "Linux" }))
    expect(reply).toHaveBeenCalledWith("Linux")
    fireEvent.change(screen.getByLabelText("Your clarification"), { target: { value: "Windows" } })
    fireEvent.click(screen.getByRole("button", { name: "Continue research" }))
    expect(reply).toHaveBeenLastCalledWith("Windows")
  })

  it("requires two selected documents and forwards their scope", async () => {
    vi.mocked(sourcesApi.documents).mockResolvedValue(["linux", "windows"].map((id) => ({ source_id: id, source_type: "filesystem", status: "active" }) as DocumentRecord))
    const compare = vi.fn()
    wrap(<ComparisonComposer disabled={false} onCompare={compare} />)
    expect(screen.getByRole("button", { name: "Compare selected documents" })).toBeDisabled()
    fireEvent.click(await screen.findByLabelText("linux"))
    fireEvent.click(screen.getByLabelText("windows"))
    fireEvent.change(screen.getByLabelText("What should be compared?"), { target: { value: "Compare protocols" } })
    fireEvent.click(screen.getByRole("button", { name: "Compare selected documents" }))
    expect(compare).toHaveBeenCalledWith("Compare protocols", ["linux", "windows"])
  })

  it("renders comparison citations with the same support mapping as answers", () => {
    const cite = vi.fn()
    const units = ["linux", "windows"].map((id, index) => ({ source_id: id, support_id: `E${index + 1}.S1`, source_rank: index + 1, source_type: "filesystem", section_label: "Setup", text: "Protocol" }))
    render(<ComparisonTable rows={[{ aspect: "Protocol", cells: [
      { source_id: "linux", text: "TLS", support_ids: ["E1.S1"] },
      { source_id: "windows", text: "SSH", support_ids: ["E2.S1"] },
    ] }]} sources={[source(1, "linux"), source(2, "windows")]} units={units} onCite={cite} />)
    fireEvent.click(screen.getByRole("button", { name: "Jump to E2.S1 in source 2" }))
    expect(cite).toHaveBeenCalledWith(2, "E2.S1")
  })

  it("marks interrupted steps as stopped and saves a flagged claim", async () => {
    vi.mocked(researchApi.feedback).mockResolvedValue({ id: "report" } as Awaited<ReturnType<typeof researchApi.feedback>>)
    render(<><ResearchActivity steps={[{ id: "1", operation: "search", status: "running" }]} streaming={false} /><AnswerFeedback turn={{ question: "Protocol?", answer: "TLS [E1.S1]", metadata: { trace_id: "trace" } } as ResearchTurn} /></>)
    expect(screen.getByText("Stopped")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Report an issue" }))
    fireEvent.change(screen.getByLabelText("Problematic claim (optional)"), { target: { value: "TLS" } })
    fireEvent.click(screen.getByRole("button", { name: "Submit feedback" }))
    expect(await screen.findByText(/Feedback saved for review/)).toBeInTheDocument()
    expect(researchApi.feedback).toHaveBeenCalledWith(expect.objectContaining({ claim: "TLS", support_ids: ["E1.S1"], trace_id: "trace" }))
  })
})
