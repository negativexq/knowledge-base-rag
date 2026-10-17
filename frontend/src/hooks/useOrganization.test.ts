import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useOrganization } from "@/hooks/useOrganization"
import { readOrganization } from "@/lib/organization"

describe("personal research organization", () => {
  it("removes a project without deleting research and restores its assignments", () => {
    const { result } = renderHook(() => useOrganization("research-a"))
    let projectId = ""
    act(() => { projectId = result.current.create("projects", "Deployment", "Review")!.id })
    act(() => { result.current.assign("session-1", projectId) })
    localStorage.setItem("research-a", "saved research")
    let undo: (() => void) | null = null
    act(() => { undo = result.current.remove("projects", projectId) })
    expect(result.current.projects).toHaveLength(0)
    expect(result.current.assignments).toEqual({})
    expect(localStorage.getItem("research-a")).toBe("saved research")
    act(() => { undo!() })
    expect(result.current.assignments).toEqual({ "session-1": projectId })
    expect(readOrganization("research-b").projects).toEqual([])
  })

  it("deduplicates document memberships and removes only the selected reference", () => {
    const { result } = renderHook(() => useOrganization("research-a"))
    const first = { sourceType: "pdf", sourceId: "runbook" }
    const second = { sourceType: "markdown", sourceId: "runbook" }
    let id = ""
    act(() => { id = result.current.create("collections", "Operations", "", [first, first])!.id })
    act(() => { result.current.addDocuments(id, [first, second]) })
    expect(result.current.collections[0].documents).toEqual([first, second])
    act(() => { result.current.removeDocument(id, first) })
    expect(result.current.collections[0].documents).toEqual([second])
    const reloaded = renderHook(() => useOrganization("research-a"))
    expect(reloaded.result.current.collections[0].documents).toEqual([second])
  })
})
