import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { researchApi } from "@/api/research"
import type { FeedbackRecord } from "@/api/types"
import { useIdentity } from "@/hooks/useIdentity"
import Feedback from "@/pages/Feedback"

vi.mock("@/api/research", () => ({ researchApi: { reports: vi.fn(), review: vi.fn(), promote: vi.fn() }, fetchEvaluationCandidates: vi.fn() }))
vi.mock("@/hooks/useIdentity", () => ({ useIdentity: vi.fn() }))

const report = { id: "r1", question: "Which protocol?", answer: "TLS", claim: "", reason: "incorrect", note: "", support_ids: [], trace_id: null,
  user_id: "u", status: "open", created_at: "2026-10-22T00:00:00Z", updated_at: "2026-10-22T00:00:00Z", reviewer_note: "",
  snapshot_origin: "user_submitted", expected_answer: "SSH", expected_source: "windows.md", expected_page: 3 } as FeedbackRecord

describe("Feedback review", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useIdentity).mockReturnValue({ data: { tenant_id: "a", user_id: "op", can_sync: true } } as ReturnType<typeof useIdentity>)
    vi.mocked(researchApi.reports).mockResolvedValue([report])
  })

  it("shows the reporter's answer and adds a confirmed answer to the evaluation set", async () => {
    vi.mocked(researchApi.promote).mockResolvedValue({} as Awaited<ReturnType<typeof researchApi.promote>>)
    render(<QueryClientProvider client={new QueryClient()}><Feedback /></QueryClientProvider>)
    expect(await screen.findByText("SSH")).toBeInTheDocument()
    expect(screen.getByText(/windows.md, p. 3/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Confirmed correct answer"), { target: { value: "SSH 2" } })
    fireEvent.click(screen.getByRole("button", { name: "Add to evaluation set" }))
    expect(await screen.findByText(/Added to the evaluation set/)).toBeInTheDocument()
    expect(researchApi.promote).toHaveBeenCalledWith("r1", "SSH 2")
  })
})
