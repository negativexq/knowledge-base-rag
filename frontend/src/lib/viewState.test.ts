import { describe, expect, it } from "vitest"
import { readKnowledgeView, knowledgeViewQuery } from "@/lib/knowledgeView"
import { passageMatches } from "@/lib/passageSearch"
import { readResearchView, updateViewQuery, viewLink } from "@/lib/viewState"

describe("Workspace view links", () => {
  it("round-trips table settings and normalizes invalid values", () => {
    const view = readKnowledgeView("?source=filesystem&q=deploy&status=error&quality=review&sort=chunk_count&order=desc&columns=quality,status&density=compact&rows=50&page=3")
    expect(view).toMatchObject({ source: "filesystem", search: "deploy", status: "error", quality: "review", page: 2, pageSize: 50, compact: true, columns: ["quality", "status"], sort: { key: "chunk_count", descending: true } })
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(knowledgeViewQuery(view))) if (value !== null) params.set(key, value)
    expect(readKnowledgeView(params.toString())).toEqual(view)
    expect(readKnowledgeView("?sort=secret&columns=invalid&rows=999&page=-5&quality=invalid")).toMatchObject({ page: 0, pageSize: 25, quality: "", columns: [], sort: { key: "source_id" } })
  })

  it("preserves router history metadata and shares only explicit view values", () => {
    window.history.replaceState({ idx: 4, key: "router-key" }, "", "/playground?token=private&answer=private#private")
    updateViewQuery({ mode: "inspect", panel: "why" })
    expect(window.history.state).toEqual({ idx: 4, key: "router-key" })
    const shared = new URL(viewLink({ mode: "inspect", panel: "why", inspector: "open" }))
    expect([...shared.searchParams.keys()]).toEqual(["mode", "panel", "inspector"])
    expect(shared.hash).toBe("")
    expect(shared.href).not.toContain("private")
  })

  it("keeps technical panels inside Inspect and accepts safe research panels", () => {
    expect(readResearchView("?mode=research&panel=security&inspector=open")).toEqual({ mode: "research", tab: "sources", open: true })
    expect(readResearchView("?mode=inspect&panel=trace&inspector=open")).toEqual({ mode: "inspect", tab: "trace", open: true })
    expect(readResearchView("?panel=notes").tab).toBe("notes")
  })

  it("finds literal text without treating punctuation as a regular expression", () => {
    expect(passageMatches("Use [a+b] then [A+B].", "[a+b]", "source")).toEqual([{ id: "source:0", start: 4, length: 5 }, { id: "source:1", start: 15, length: 5 }])
    expect(passageMatches("any text", "  ", "source")).toEqual([])
  })
})
