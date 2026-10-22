import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { readResearchSessions, type ResearchTurn } from "@/lib/research"
import { attachLibrary, cancelRun, isRunning, resetResearchRuns, setViewing, startRun, useResearchRuns } from "@/lib/researchRuns"
import { act, renderHook } from "@testing-library/react"

const SCOPE = "kb-research:test"
const turn = (question: string) => ({ question, steps: [], answer: "", sources: [], streaming: true, errorMessage: null, validation: null, grounding: null, metadata: null }) as unknown as ResearchTurn

beforeEach(() => { localStorage.clear(); resetResearchRuns() })
afterEach(() => { vi.unstubAllGlobals(); resetResearchRuns() })

test("a run keeps its live turn and stores the finished answer when no workspace is open", () => {
  const run = startRun(SCOPE, "s1", turn("What is the margin?"))
  run.update((value) => ({ ...value, answer: "12%" }))
  const { result } = renderHook(() => useResearchRuns())
  expect(result.current.live.get("s1")?.answer).toBe("12%")
  expect(isRunning("s1")).toBe(true)

  act(() => run.finish())

  const [session] = readResearchSessions(SCOPE)
  expect(session.id).toBe("s1")
  expect(session.title).toBe("What is the margin?")
  expect(session.turns[0]).toMatchObject({ answer: "12%", streaming: false })
  expect(isRunning("s1")).toBe(false)
  expect(result.current.finished).toMatchObject([{ sessionId: "s1", outcome: "answered" }])
})

test("a mounted library receives the finished turn instead of storage", () => {
  const saver = vi.fn()
  attachLibrary(SCOPE, saver)
  startRun(SCOPE, "s1", turn("Q")).finish({ errorMessage: "The response stream was interrupted." })
  expect(saver).toHaveBeenCalledWith("s1", expect.objectContaining({ streaming: false, errorMessage: "The response stream was interrupted." }))
  expect(localStorage.getItem(SCOPE)).toBeNull()
})

test("cancelling ends the run quietly and ignores the old stream's late events", () => {
  const saver = vi.fn()
  attachLibrary(SCOPE, saver)
  const run = startRun(SCOPE, "s1", turn("Q"))
  cancelRun("s1")
  expect(run.signal.aborted).toBe(true)
  run.update((value) => ({ ...value, answer: "late" }))
  run.finish()
  expect(saver).toHaveBeenCalledTimes(1)
  expect(saver.mock.calls[0][1]).toMatchObject({ errorMessage: "Cancelled.", answer: "" })
  const { result } = renderHook(() => useResearchRuns())
  expect(result.current.finished).toEqual([])
})

test("no notice for the session being watched; opening a session clears its notice", () => {
  setViewing("s1")
  startRun(SCOPE, "s1", turn("Watched")).finish()
  startRun(SCOPE, "s2", turn("Elsewhere")).finish()
  const { result, rerender } = renderHook(() => useResearchRuns())
  expect(result.current.finished.map((item) => item.sessionId)).toEqual(["s2"])
  setViewing("s2")
  rerender()
  expect(result.current.finished).toEqual([])
})

test("a hidden tab gets a browser notification when permission was granted", () => {
  const created: string[] = []
  vi.stubGlobal("Notification", Object.assign(function (this: object, title: string) { created.push(title) }, { permission: "granted" }))
  vi.spyOn(document, "hidden", "get").mockReturnValue(true)
  startRun(SCOPE, "s1", turn("Q")).finish()
  expect(created).toEqual(["Research finished"])
})
