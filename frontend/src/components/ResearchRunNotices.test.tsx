import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, expect, test } from "vitest"

import { ResearchRunNotices } from "@/components/ResearchRunNotices"
import type { ResearchTurn } from "@/lib/research"
import { resetResearchRuns, startRun } from "@/lib/researchRuns"

const turn = (question: string) => ({ question, steps: [], answer: "", sources: [], streaming: true, errorMessage: null, validation: null, grounding: null, metadata: null }) as unknown as ResearchTurn

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); resetResearchRuns() })

test("reports research finished elsewhere and opens it in the workspace", () => {
  render(<MemoryRouter initialEntries={["/knowledge"]}><Routes><Route path="/knowledge" element={<ResearchRunNotices />} /><Route path="/playground" element={<p>Workspace</p>} /></Routes></MemoryRouter>)
  act(() => startRun("scope-a", "s1", turn("Which version added TLS?")).finish())
  act(() => startRun("scope-a", "s2", turn("Failed one")).finish({ errorMessage: "Request failed (500)." }))

  expect(screen.getByText("Research finished")).toBeInTheDocument()
  expect(screen.getByText("Research stopped")).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[1])
  expect(screen.queryByText("Research stopped")).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole("button", { name: "Open answer" }))
  expect(screen.getByText("Workspace")).toBeInTheDocument()
  expect(JSON.parse(sessionStorage.getItem("scope-a:launch")!)).toEqual({ sessionId: "s1", projectId: null })
})
