import { describe, expect, it } from "vitest"

import { splitAnswerIntoSegments } from "@/lib/citations"

describe("citation integrity rendering", () => {
  it("matches citations by the complete authorized source identity", () => {
    const source = {
      rank: 2,
      source_type: "markdown",
      source_id: "runbook",
      citation_location: "Operations/Deploy",
      page_number: null,
      paragraph_index: null,
      heading_path: ["Operations", "Deploy"],
      snippet: "restart safely",
      score: 0.24,
      document_version: "v1",
      tenant_id: "tenant-a",
      visibility: "private",
    }
    const segments = splitAnswerIntoSegments(
      "See [s.markdown:runbook/Operations/Deploy] and [s.markdown:other/Operations/Deploy].",
      [source],
    )

    expect(segments.filter((segment) => segment.type === "citation").map((segment) => segment.valid)).toEqual([
      true,
      false,
    ])
    expect(segments[1].source?.rank).toBe(2)
  })
})

describe("support-ID citations", () => {
  const source = (rank: number, sourceId: string) => ({
    rank,
    source_type: "filesystem",
    source_id: sourceId,
    citation_location: "Kimlik Doğrulama/Token Süresi",
    page_number: 1,
    paragraph_index: 0,
    heading_path: ["Kimlik Doğrulama", "Token Süresi"],
    snippet: "Nimbus CLI pip ile kurulur.",
    score: 0.9,
    document_version: "v1",
    tenant_id: "tenant-a",
    visibility: "tenant",
  })
  const units = [
    {
      support_id: "E1.S2",
      source_rank: 1,
      source_type: "filesystem",
      source_id: "nimbus_cli_md",
      section_label: "Kimlik Doğrulama > Token Süresi",
      text: "Erişim token'ları 90 gün geçerlidir.",
    },
    {
      support_id: "E2.S1",
      source_rank: 2,
      source_type: "filesystem",
      source_id: "handbook",
      section_label: "page 3",
      text: "Free accounts include 15GB of storage.",
    },
  ]

  it("resolves each support ID to its unit and its source card", () => {
    const segments = splitAnswerIntoSegments(
      "Token 90 gün geçerlidir. [E1.S2] [E2.S1]",
      [source(1, "nimbus_cli_md"), source(2, "handbook")],
      units,
    )
    const citations = segments.filter((segment) => segment.type === "citation")

    expect(citations.map((c) => [c.text, c.valid, c.source?.rank, c.unit?.section_label])).toEqual([
      ["[E1.S2]", true, 1, "Kimlik Doğrulama > Token Süresi"],
      ["[E2.S1]", true, 2, "page 3"],
    ])
    expect(segments[0]).toMatchObject({ type: "text", text: "Token 90 gün geçerlidir. " })
  })

  it("marks a support ID the model was not given as invalid", () => {
    const [, citation] = splitAnswerIntoSegments("Fact. [E9.S1]", [source(1, "nimbus_cli_md")], units)

    expect(citation).toMatchObject({ type: "citation", valid: false })
    expect(citation.unit).toBeUndefined()
  })
})
