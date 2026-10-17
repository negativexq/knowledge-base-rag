import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { DocumentRecord } from "@/api/types"
import { KnowledgeDocuments } from "@/components/KnowledgeDocuments"

const base: DocumentRecord = { tenant_id: "tenant-a", source_type: "filesystem", source_id: "alpha.md", content_hash: "a", version: 2, status: "healthy", chunk_count: 12, pipeline_fingerprint: null, last_synced_at: "2026-10-17T09:00:00Z" }
const review = { pages: 2, ocr_pages: {}, skipped_pages: 1, garbled_blocks_dropped: 0, empty_pages: 1, headings: 0, tables: 0, furniture: 0, heading_source: "none", needs_review: true }
const documents: DocumentRecord[] = [base, { ...base, source_id: "beta.pdf", version: 10, chunk_count: 3, status: "error", ingestion_quality: review }, { ...base, source_id: "gamma.pdf", version: 1, chunk_count: null, ingestion_quality: { ...review, needs_review: false } }]
function renderDocuments(docs = documents) {
  return render(<KnowledgeDocuments documents={docs} onOpen={vi.fn()} preferencesKey="test-table" />)
}
const names = () => within(screen.getByRole("table")).getAllByRole("button", { name: /\.(md|pdf)$/ }).map((button) => button.textContent)

describe("Knowledge table controls", () => {
  it("combines filters and clears them without losing loaded documents", () => {
    renderDocuments()
    fireEvent.change(screen.getByRole("combobox", { name: "Filter by status" }), { target: { value: "error" } })
    fireEvent.change(screen.getByRole("combobox", { name: "Filter by parse quality" }), { target: { value: "review" } })
    expect(names()).toEqual(["beta.pdf"])
    fireEvent.change(screen.getByRole("textbox", { name: "Filter documents by name" }), { target: { value: "alpha" } })
    expect(screen.getByText("No documents match")).toBeInTheDocument()
    expect(screen.getByText("0 of 3 loaded documents")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }))
    expect(names()).toEqual(["alpha.md", "beta.pdf", "gamma.pdf"])
  })

  it("sorts numerically and keeps unknown counts last in either direction", () => {
    renderDocuments()
    fireEvent.click(screen.getByRole("button", { name: "Sort by Version" }))
    expect(names()).toEqual(["gamma.pdf", "alpha.md", "beta.pdf"])
    fireEvent.click(screen.getByRole("button", { name: "Sort by Chunks" }))
    expect(names()).toEqual(["beta.pdf", "alpha.md", "gamma.pdf"])
    fireEvent.click(screen.getByRole("button", { name: "Sort by Chunks" }))
    expect(names()).toEqual(["alpha.md", "beta.pdf", "gamma.pdf"])
    expect(screen.getByRole("button", { name: "Sort by Chunks" }).closest("th")).toHaveAttribute("aria-sort", "descending")
  })

  it("remembers column visibility and density in this browser", () => {
    const first = renderDocuments()
    fireEvent.change(screen.getByRole("combobox", { name: "Table density" }), { target: { value: "compact" } })
    fireEvent.click(screen.getByRole("button", { name: "Columns" }))
    fireEvent.click(screen.getByRole("checkbox", { name: "Chunks" }))
    expect(screen.queryByRole("button", { name: "Sort by Chunks" })).not.toBeInTheDocument()
    first.unmount()
    renderDocuments()
    expect(screen.getByRole("combobox", { name: "Table density" })).toHaveValue("compact")
    expect(screen.queryByRole("button", { name: "Sort by Chunks" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sort by Name" })).toBeInTheDocument()
  })

  it("saves and restores named filter and layout views", async () => {
    renderDocuments()
    fireEvent.change(screen.getByRole("combobox", { name: "Filter by status" }), { target: { value: "error" } })
    fireEvent.change(screen.getByRole("combobox", { name: "Table density" }), { target: { value: "compact" } })
    fireEvent.click(screen.getByRole("button", { name: "Sort by Chunks" }))
    fireEvent.click(screen.getByRole("button", { name: "Views" }))
    fireEvent.change(screen.getByRole("textbox", { name: "New saved view name" }), { target: { value: "Failed documents" } })
    fireEvent.click(screen.getByRole("button", { name: "Save view" }))
    await waitFor(() => expect(JSON.parse(localStorage.getItem("test-table:views")!)).toHaveLength(1))
    fireEvent.click(screen.getByRole("button", { name: "Views" }))
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }))
    fireEvent.change(screen.getByRole("combobox", { name: "Table density" }), { target: { value: "comfortable" } })
    expect(names()).toHaveLength(3)
    fireEvent.click(screen.getByRole("button", { name: "Views" }))
    fireEvent.click(screen.getByRole("button", { name: "Failed documents" }))
    expect(names()).toEqual(["beta.pdf"])
    expect(screen.getByRole("combobox", { name: "Table density" })).toHaveValue("compact")
    expect(screen.getByRole("combobox", { name: "Filter by status" })).toHaveValue("error")
    expect(screen.getByRole("button", { name: "Sort by Chunks" }).closest("th")).toHaveAttribute("aria-sort", "ascending")
  })

  it("restores view settings from URLs and responds to browser navigation", () => {
    window.history.replaceState(null, "", "/knowledge?source=filesystem&q=beta&quality=review")
    renderDocuments()
    expect(names()).toEqual(["beta.pdf"])
    expect(screen.getByRole("textbox", { name: "Filter documents by name" })).toHaveValue("beta")
    act(() => {
      window.history.replaceState(null, "", "/knowledge?q=alpha")
      window.dispatchEvent(new PopStateEvent("popstate"))
    })
    expect(names()).toEqual(["alpha.md"])
    expect(screen.getByRole("combobox", { name: "Filter by parse quality" })).toHaveValue("")
  })

  it("paginates loaded rows and resets to the first page after filtering", () => {
    renderDocuments(Array.from({ length: 32 }, (_, index) => ({ ...base, source_id: `doc-${index + 1}.md` })))
    expect(names()).toHaveLength(25)
    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(names()).toHaveLength(7)
    fireEvent.change(screen.getByRole("textbox", { name: "Filter documents by name" }), { target: { value: "doc-32" } })
    expect(names()).toEqual(["doc-32.md"])
    expect(screen.getByText("Page 1 of 1")).toBeInTheDocument()
  })
})
