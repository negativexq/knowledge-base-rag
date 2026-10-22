import { describe, expect, it } from "vitest"
import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { followUpQuestions } from "@/lib/followUps"

const source = (rank: number, id: string) => ({ rank, source_id: id }) as RetrievedSource
const unit = { support_id: "E1.S1", source_rank: 1, source_type: "filesystem", source_id: "report.pdf", section_label: "Revenue by segment", text: "" } as SupportUnitRef

describe("followUpQuestions", () => {
  it("builds suggestions from the cited section, the calculation and other documents", () => {
    const suggestions = followUpQuestions({
      question: "What was total revenue?", outcome: "answered",
      sources: [source(1, "report.pdf"), source(2, "annual.pdf")], citedUnits: [unit],
      calculations: [{ id: "c", expression: "a+b", result: "3", unit: "", support_ids: [], inputs: [
        { name: "a", label: "Cloud", value: "1", unit: "", support_id: null, page: null },
        { name: "b", label: "Devices", value: "2", unit: "", support_id: null, page: null }] }],
    })
    expect(suggestions).toEqual([
      "Show Cloud, Devices side by side in a table",
      'Summarize the "Revenue by segment" section of report.pdf',
      "Does annual.pdf say anything different about: What was total revenue?",
    ])
  })

  it("offers a narrower search when the answer could not be verified, and nothing when stopped", () => {
    const base = { question: "Q?", sources: [source(1, "report.pdf"), source(2, "annual.pdf")], citedUnits: [], calculations: [] }
    expect(followUpQuestions({ ...base, outcome: "unverified" })).toEqual(["Look only in report.pdf: Q?"])
    expect(followUpQuestions({ ...base, outcome: "stopped" })).toEqual([])
  })
})
