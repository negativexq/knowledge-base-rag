import { describe, expect, it } from "vitest"
import type { RetrievedSource } from "@/api/types"
import { answerReportHtml } from "@/lib/report"
import type { ResearchTurn } from "@/lib/research"

const source = { rank: 1, source_id: "report.pdf", source_type: "filesystem", page_number: 4, snippet: "A 120 cm; B 2 m", heading_path: [], document_version: "a".repeat(64) } as unknown as RetrievedSource
const turn = {
  question: "Total <length>?", answer: "The total is 3.20 m [E1.S1].", streaming: false, errorMessage: null,
  sources: [source], validation: { passed: true, abstain: false, validator_failure_codes: [] }, grounding: null,
  metadata: {
    trace_id: "t", prompt_version: "v3",
    support_units: [{ support_id: "E1.S1", source_rank: 1, source_type: "filesystem", source_id: "report.pdf", section_label: "Lengths", text: "A 120 cm; B 2 m" }],
    calculations: [{ id: "c", expression: "a+b", result: "3.20", unit: "m", support_ids: ["E1.S1"], inputs: [{ name: "a", label: "A", value: "120", unit: "cm", support_id: "E1.S1", page: 4 }] }],
  },
} as unknown as ResearchTurn

describe("answerReportHtml", () => {
  it("is a self-contained page with escaped text, footnoted citations, the calculation and page images", () => {
    const html = answerReportHtml(turn, [{ sourceId: "report.pdf", page: 4, dataUrl: "data:image/png;base64,AA==", highlighted: true }], new Date("2026-10-22T00:00:00Z"))
    expect(html).toContain("<h1>Total &lt;length&gt;?</h1>")
    expect(html).toContain('<sup><a href="#ref-1">1</a></sup>')
    expect(html).toContain("<code>a+b</code> = <strong>3.20 m</strong>")
    expect(html).toContain("Answer checked against the cited sources")
    expect(html).toContain('src="data:image/png;base64,AA=="')
    expect(html).not.toMatch(/<script/i)
  })

  it("leaves the calculation out of an unverified answer", () => {
    const html = answerReportHtml({ ...turn, validation: { passed: true, abstain: true, validator_failure_codes: [] } })
    expect(html).toContain("Sufficient evidence could not be verified")
    expect(html).not.toContain("How this was calculated")
  })
})
