import { describe, expect, it } from "vitest"

import { answerStatus, describeDoneReason, explainCode, explainSkip } from "@/lib/answerStatus"

const passed = { passed: true, abstain: false, validator_failure_codes: [] }

describe("answer status", () => {
  it("is verified when the answer passed and cites passages", () => {
    expect(answerStatus({ streaming: false, validation: passed, citesUnits: true })).toEqual({
      kind: "verified",
      title: "Citation integrity verified",
      reasons: [],
    })
  })

  it("explains why an answer was not verified", () => {
    const status = answerStatus({
      streaming: false,
      validation: {
        passed: false,
        abstain: true,
        validator_failure_codes: ["CRITICAL_VALUE_INDETERMINATE", "NO_VALID_SUPPORT_BACKED_CLAIMS"],
      },
      citesUnits: false,
    })

    expect(status?.kind).toBe("unverified")
    expect(status?.title).toBe("Citation validation failed")
    expect(status?.reasons).toEqual([
      explainCode("CRITICAL_VALUE_INDETERMINATE"),
      explainCode("NO_VALID_SUPPORT_BACKED_CLAIMS"),
    ])
  })

  it("separates a clean not-found answer from a skipped generation", () => {
    expect(
      answerStatus({
        streaming: false,
        validation: { ...passed, abstain: true },
        citesUnits: false,
      })?.kind,
    ).toBe("not_found")

    const skipped = answerStatus({
      streaming: false,
      validation: { ...passed, abstain: true },
      metadata: { prompt_version: "v1", trace_id: "t", generation_skipped: "EMPTY_RERANK_RESULT" },
      citesUnits: false,
    })
    expect(skipped).toEqual({
      kind: "no_evidence",
      title: "No matching evidence",
      reasons: [explainSkip("EMPTY_RERANK_RESULT")],
    })
  })

  it("keeps the legacy grounding verdict", () => {
    expect(
      answerStatus({
        streaming: false,
        grounding: { grounded: false, has_citations: true, citations_found: [], ungrounded_citations: [] },
        citesUnits: false,
      })?.kind,
    ).toBe("unverified")
  })

  it("says nothing while streaming or before a verdict", () => {
    expect(answerStatus({ streaming: true, validation: passed, citesUnits: true })).toBeNull()
    expect(answerStatus({ streaming: false, citesUnits: false })).toBeNull()
  })

  it("explains codes and reasons in plain words, falling back to the code", () => {
    expect(explainCode("OUTPUT_TRUNCATED")).toMatch(/ran out of room/)
    expect(explainCode("SOMETHING_NEW")).toBe("SOMETHING_NEW")
    expect(explainSkip("NO_EVIDENCE_BLOCKS")).toMatch(/evidence/)
    expect(describeDoneReason("length")).toMatch(/length limit/)
    expect(describeDoneReason("stop")).toBe("Finished normally")
  })
})
