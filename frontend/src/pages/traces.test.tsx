import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { syncApi } from "@/api/sync"
import { uiApi } from "@/api/ui"
import Traces from "@/pages/Traces"

vi.mock("@/api/sync", () => ({ syncApi: { allRuns: vi.fn() } }))
vi.mock("@/api/ui", () => ({ uiApi: { chatTraces: vi.fn(), trace: vi.fn() } }))

function page() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Traces /></MemoryRouter></QueryClientProvider>)
}

describe("Research traces", () => {
  it("opens a recorded agent request even when the sync service fails", async () => {
    vi.mocked(syncApi.allRuns).mockRejectedValue(new Error("Sync unavailable"))
    vi.mocked(uiApi.chatTraces).mockResolvedValue([{ trace_id: "abc", span_id: "root", started_at: new Date().toISOString(), pipeline: "pipeline_agentic_v1", outcome: "answered" }])
    vi.mocked(uiApi.trace).mockResolvedValue({ trace_id: "abc", available: true, jaeger_url: "http://jaeger", spans: [{ name: "agent.run", duration_ms: 10, offset_ms: 0 }] })
    page()
    fireEvent.click(await screen.findByRole("button", { name: /pipeline_agentic_v1/ }))
    expect(await screen.findByText("agent.run")).toBeInTheDocument()
    expect(uiApi.trace).toHaveBeenCalledWith("abc")
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled()
  })
})
