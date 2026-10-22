import { act, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ResearchStep } from "@/api/types"
import { ResearchActivity } from "@/components/ResearchActivity"

const stage = (id: string, name: string, status: ResearchStep["status"], extra: Partial<ResearchStep> = {}): ResearchStep => ({
  id, kind: "stage", stage: name, operation: "", status, message: `${name} message`, ...extra,
})

describe("ResearchActivity", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it("shows the active stage, its own elapsed time and the total elapsed time", () => {
    vi.setSystemTime(0)
    const steps = [
      stage("s1", "retrieval", "completed", { duration_ms: 1200, receivedAt: 0 }),
      stage("s2", "input_review", "running", { receivedAt: 17_000 }),
    ]
    render(<ResearchActivity steps={steps} streaming startedAt={0} />)
    act(() => vi.advanceTimersByTime(42_000))
    expect(screen.getByText("Researching the documents")).toBeInTheDocument()
    expect(screen.getByText("00:42")).toBeInTheDocument()
    const active = screen.getByText("input_review message").closest("li")!
    expect(active).toHaveAttribute("aria-current", "step")
    expect(within(active).getByText("25 s")).toBeInTheDocument()
    expect(screen.getByText("retrieval message").closest("li")).toHaveAttribute("data-status", "completed")
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it("presents a repair as a recheck rather than an error", () => {
    const steps = [
      stage("s1", "input_review", "retrying", { reason: "check_failed", receivedAt: 0 }),
      stage("s2", "evidence_repair", "running", { reason: "incomplete_coverage", message: "Coverage is incomplete; inspecting more of the source", receivedAt: 0 }),
    ]
    render(<ResearchActivity steps={steps} streaming startedAt={0} />)
    expect(screen.getByText("Needed another look")).toBeInTheDocument()
    expect(screen.getByText("Coverage is incomplete; inspecting more of the source")).toBeInTheDocument()
    const list = screen.getByRole("list", { name: "Research stages" })
    expect(within(list).queryByText(/fail|error/i)).not.toBeInTheDocument()
  })

  it("collapses to a truthful summary when research ends", () => {
    const steps = [
      stage("s1", "retrieval", "completed", { duration_ms: 900 }),
      stage("s2", "calculation", "completed", { duration_ms: 3000 }),
      { id: "op", operation: "extract", status: "completed", added_evidence: 2 } as ResearchStep,
    ]
    const { rerender } = render(<ResearchActivity steps={steps} streaming={false} startedAt={0} finishedAt={58_400} outcome="answered" />)
    expect(screen.getByText("Research completed · 58 s · 2 stages")).toBeInTheDocument()
    rerender(<ResearchActivity steps={steps} streaming={false} startedAt={0} finishedAt={58_400} outcome="unverified" />)
    expect(screen.getByText("Sufficient evidence could not be verified · 58 s · 2 stages")).toBeInTheDocument()
  })

  it("lists tool operations and their evidence counts under technical details", () => {
    const steps = [
      stage("s1", "extraction", "running"),
      { id: "op", operation: "read", status: "completed", added_evidence: 3 } as ResearchStep,
    ]
    render(<ResearchActivity steps={steps} streaming startedAt={0} />)
    const details = screen.getByText("Technical details").closest("details")!
    expect(within(details).getByText("Inspecting evidence")).toBeInTheDocument()
    expect(within(details).getByText("+3 evidence")).toBeInTheDocument()
  })

  it("keeps operation-only research readable", () => {
    render(<ResearchActivity steps={[{ id: "1", operation: "search", status: "running" }]} streaming={false} />)
    expect(screen.getByText("Searching sources")).toBeInTheDocument()
    expect(screen.getByText("Stopped")).toBeInTheDocument()
  })
})
