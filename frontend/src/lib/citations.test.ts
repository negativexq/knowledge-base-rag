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
