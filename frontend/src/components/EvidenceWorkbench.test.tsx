import { useState } from "react"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SourceCard } from "@/components/SourceCard"
import { EvidenceSources } from "@/components/EvidenceSources"
import { PinnedEvidence } from "@/components/PinnedEvidence"
import { ResearchNotes } from "@/components/ResearchNotes"
import { newResearchSession, type ResearchSession } from "@/lib/research"

function fixture(): ResearchSession {
  return { ...newResearchSession(), turns: [{ question: "Deploy?", answer: "An answer.", sources: [
    { rank: 1, source_type: "filesystem", source_id: "incident.pdf", citation_location: "4/0", page_number: 4, paragraph_index: 0, heading_path: ["Root cause"], snippet: "Configuration drift. Another drift.", score: 0.3, document_version: "v2", tenant_id: "tenant-a", visibility: "tenant" },
    { rank: 2, source_type: "filesystem", source_id: "runbook.md", citation_location: "1/0", page_number: null, paragraph_index: 0, heading_path: ["Recovery"], snippet: "Restore the previous configuration.", score: 0.2, document_version: "v3", tenant_id: "tenant-a", visibility: "tenant" },
  ], metadata: { prompt_version: "v1", trace_id: "t1", support_units: [{ support_id: "E1.S2", source_rank: 1, source_id: "incident.pdf", source_type: "filesystem", section_label: "Root cause", text: "Configuration drift was observed." }] }, streaming: false, errorMessage: null, report: null, grounding: null, validation: null, firstTokenAt: null, lastTokenAt: null, groundingAt: null, askStartedAt: null }], pins: [
    { turnIndex: 0, sourceRank: 1, supportId: null }, { turnIndex: 0, sourceRank: 1, supportId: "E1.S2" }, { turnIndex: 0, sourceRank: 2, supportId: null },
  ] }
}

describe("Research evidence workbench", () => {
  it("shows readable source locations without the raw citation code", () => {
    const source = { ...fixture().turns[0].sources[0], page_number: 2, citation_location: "2/0", heading_path: [], section_labels: ["One", "Two", "Three", "Four", "Five", "Six"] }
    render(<SourceCard source={source} cited={false} highlighted={false} />)
    const card = screen.getByRole("button", { name: "View source 1: incident.pdf" })
    expect(card).toHaveTextContent("Page 2 · +5 more sections")
    expect(card).not.toHaveTextContent("2/0")
  })

  it("compares exactly two captured passages with their actual versions and locations", () => {
    render(<PinnedEvidence session={fixture()} onOpen={vi.fn()} onRemove={vi.fn()} />)
    fireEvent.click(screen.getByRole("checkbox", { name: "Compare evidence 2" }))
    fireEvent.click(screen.getByRole("checkbox", { name: "Compare evidence 3" }))
    expect(screen.getByRole("checkbox", { name: "Compare evidence 1" })).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Compare selected (2/2)" }))
    const dialog = screen.getByRole("dialog", { name: "Evidence comparison" })
    const first = within(dialog).getByRole("region", { name: "Comparison passage 1" })
    const second = within(dialog).getByRole("region", { name: "Comparison passage 2" })
    expect(first).toHaveTextContent("Configuration drift was observed.")
    expect(first).toHaveTextContent("Root cause")
    expect(first).toHaveTextContent("v2")
    expect(second).toHaveTextContent("Restore the previous configuration.")
    expect(second).toHaveTextContent("v3")
    fireEvent.click(within(dialog).getByRole("button", { name: "Close evidence comparison" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("relates support-unit citations to their source without marking other retrieved evidence as cited", () => {
    const session = fixture()
    render(<EvidenceSources sources={session.turns[0].sources} units={new Map([[1, session.turns[0].metadata!.support_units!]])} answer="Configuration drift caused the failure. [E1.S2] Unsupported [E9.S1]" supportUnits={session.turns[0].metadata!.support_units!} highlightedRank={1} highlightedUnit="E1.S2" technical={false} cardRef={vi.fn()} isPinned={() => false} />)
    const relationship = screen.getByRole("region", { name: "Citation relationship for source 1" })
    expect(relationship).toHaveTextContent("[E1.S2]")
    expect(relationship).toHaveTextContent("Configuration drift caused the failure.")
    expect(relationship).not.toHaveTextContent("E9.S1")
    fireEvent.click(screen.getByRole("button", { name: "View source 2: runbook.md" }))
    expect(screen.getByRole("region", { name: "Citation relationship for source 2" })).toHaveTextContent("no matching citation")
  })

  it("opens passage matches, highlights literal text and navigates every match", () => {
    const session = fixture()
    const units = new Map([[1, session.turns[0].metadata!.support_units!]])
    const { container } = render(<EvidenceSources sources={session.turns[0].sources} units={units} highlightedRank={null} highlightedUnit={null} technical={false} cardRef={vi.fn()} isPinned={() => false} />)
    expect(screen.getByRole("button", { name: "View source 1: incident.pdf" })).toHaveAttribute("aria-expanded", "false")
    fireEvent.change(screen.getByRole("textbox", { name: "Search source passages" }), { target: { value: "drift" } })
    expect(screen.getByRole("status")).toHaveTextContent("1 of 3")
    expect(container.querySelectorAll("mark")).toHaveLength(3)
    expect(container.querySelector('mark[data-active="true"]')).toHaveAttribute("data-match-id", "source-1:unit-E1.S2:0")
    fireEvent.click(screen.getByRole("button", { name: "Next passage match" }))
    expect(screen.getByRole("status")).toHaveTextContent("2 of 3")
    expect(container.querySelector('mark[data-active="true"]')).toHaveAttribute("data-match-id", "source-1:snippet:0")
    fireEvent.change(screen.getByRole("textbox", { name: "Search source passages" }), { target: { value: "[missing]" } })
    expect(screen.getByRole("status")).toHaveTextContent("0 of 0")
    expect(screen.getByRole("button", { name: "Next passage match" })).toBeDisabled()
  })

  it("keeps personal notes separate and links them back to captured evidence", () => {
    const onOpen = vi.fn()
    function Notes() {
      const [session, setSession] = useState(fixture)
      return <ResearchNotes session={session} initialEvidence={session.pins[1]} disabled={false} onOpen={onOpen}
        onSave={(note) => setSession((value) => ({ ...value, notes: [...value.notes.filter((item) => item.id !== note.id), note] }))}
        onRemove={(id) => setSession((value) => ({ ...value, notes: value.notes.filter((note) => note.id !== id) }))} />
    }
    render(<Notes />)
    fireEvent.change(screen.getByRole("textbox", { name: "Research note" }), { target: { value: "Check whether this applies to the next rollout." } })
    fireEvent.click(screen.getByRole("button", { name: "Save note" }))
    expect(screen.getByText("Check whether this applies to the next rollout.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "incident.pdf · Root cause" }))
    expect(onOpen).toHaveBeenCalledWith({ turnIndex: 0, sourceRank: 1, supportId: "E1.S2" })
    fireEvent.click(screen.getByRole("button", { name: "Edit note 1" }))
    fireEvent.change(screen.getByRole("textbox", { name: "Research note" }), { target: { value: "Reviewed the rollout." } })
    fireEvent.click(screen.getByRole("button", { name: "Save note" }))
    expect(screen.queryByText("Check whether this applies to the next rollout.")).not.toBeInTheDocument()
    expect(screen.getByText("Reviewed the rollout.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Remove note 1" }))
    expect(screen.queryByText("Reviewed the rollout.")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Undo" }))
    expect(screen.getByText("Reviewed the rollout.")).toBeInTheDocument()
  })
})
