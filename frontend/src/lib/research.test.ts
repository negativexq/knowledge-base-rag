import { describe, expect, it } from "vitest"

import type { Identity } from "@/api/types"
import { newResearchSession, readResearchSessions, researchMarkdown, researchOutcome, researchScope, resolvePin, type ResearchSession, type ResearchTurn } from "@/lib/research"

const identity: Identity = { tenant_id: "tenant-a", user_id: "user-a", roles: ["USER"], is_admin: false, can_sync: false, auth_enabled: true }
export function researchFixture(): ResearchSession {
  return { ...newResearchSession(), title: "Deployment research", pins: [{ turnIndex: 0, sourceRank: 1, supportId: "E1.S2" }], turns: [{
    question: "Why did deployment fail?", answer: "A configuration mismatch. [E1.S2] Again [E1.S2] Unknown [E9.S9]", streaming: false, errorMessage: null,
    sources: [{ rank: 1, source_type: "filesystem", source_id: "incident.pdf", citation_location: "4/0", page_number: 4, paragraph_index: 0, heading_path: ["Root cause"], snippet: "Full source excerpt.", score: 0.3, document_version: "v2", tenant_id: "tenant-a", visibility: "tenant" }],
    metadata: { prompt_version: "v1", trace_id: "trace-1", support_units: [{ support_id: "E1.S2", source_rank: 1, source_type: "filesystem", source_id: "incident.pdf", section_label: "Root cause", text: "Configuration drift was observed." }] },
    report: null, grounding: null, validation: { passed: false, abstain: false, validator_failure_codes: ["UNKNOWN_SUPPORT_ID"] }, firstTokenAt: null, lastTokenAt: null, groundingAt: null, askStartedAt: null,
  }] }
}

describe("Local research data", () => {
  it("partitions snapshots by tenant, user and role context", () => {
    const scope = researchScope(identity)
    expect(researchScope({ ...identity, tenant_id: "tenant-b" })).not.toBe(scope)
    expect(researchScope({ ...identity, user_id: "other-user" })).not.toBe(scope)
    expect(researchScope({ ...identity, roles: ["ADMIN"] })).not.toBe(scope)
    expect(researchScope({ ...identity, roles: ["USER", "ADMIN"] })).toBe(researchScope({ ...identity, roles: ["ADMIN", "USER"] }))
    localStorage.setItem(scope, JSON.stringify([researchFixture()]))
    expect(readResearchSessions(researchScope({ ...identity, tenant_id: "tenant-b" }))).toEqual([])
  })

  it("ignores malformed storage and unusable saved sessions", () => {
    localStorage.setItem("test", "not json")
    expect(readResearchSessions("test")).toEqual([])
    localStorage.setItem("test", JSON.stringify([{ ...researchFixture(), turns: [{}] }, researchFixture()]))
    expect(readResearchSessions("test")).toHaveLength(1)
  })

  it("exports citation locations, passages and exact validation outcomes", () => {
    const markdown = researchMarkdown(researchFixture())
    expect(markdown).toContain("Page 4")
    expect(markdown).toContain("Version v2")
    expect(markdown).toContain("Configuration drift was observed.")
    expect(markdown).toContain("Validation: Citation validation failed")
    expect(markdown).toContain("unresolved citation")
    expect(markdown.match(/\[\^a1r1\]:/g)).toHaveLength(1)
    expect(markdown).toContain("## Pinned evidence")
    expect(markdown).not.toContain("Factually verified")
  })

  it("does not export unfinished answers or resolve pins to another source", () => {
    const session = researchFixture()
    session.turns[0].streaming = true
    session.pins = []
    expect(researchMarkdown(session)).not.toContain("A configuration mismatch")
    expect(resolvePin(session, { turnIndex: 0, sourceRank: 99, supportId: "E1.S2" })).toBeNull()
  })
})

it("exports comparison aspects and clarification replies with resolved footnotes", () => {
  const session = researchFixture()
  const turn = session.turns[0]
  turn.clarificationReply = { question: "Which environment?", answer: "Production" }
  turn.comparison = [{ aspect: "Root cause", cells: [{ source_id: "incident.pdf", text: "Configuration drift", support_ids: ["E1.S2"] }] }]
  const output = researchMarkdown(session)
  expect(output).toContain("Clarification: Which environment? — Production")
  expect(output).toContain("| Aspect | incident.pdf |")
  expect(output).toContain("| Root cause | Configuration drift [^a1r1] |")
})

it("keeps saved answers whose research timeline has stage events", () => {
  const session = researchFixture()
  session.turns[0].steps = [
    { id: "stage-1", kind: "stage", stage: "retrieval", status: "completed", message: "Searching the documents", duration_ms: 12 },
    { id: "op-1", operation: "search", status: "completed" },
  ] as ResearchTurn["steps"]
  expect(readResearchSessions("scope", JSON.stringify([session]))[0]?.turns[0].steps).toHaveLength(2)
  session.turns[0].steps = [{ id: "stage-1", kind: "stage", status: "completed" }] as unknown as ResearchTurn["steps"]
  expect(readResearchSessions("scope", JSON.stringify([session]))).toEqual([])
})

it("rejects malformed saved workflow payloads instead of crashing the workspace", () => {
  const session = researchFixture()
  const malformed = { ...session, turns: [{ ...session.turns[0], comparison: [{ cells: "invalid" }] }] }
  expect(readResearchSessions("workflow", JSON.stringify([malformed]))).toEqual([])
  const valid = { ...session, turns: [{ ...session.turns[0], steps: [{ id: "s", operation: "search", status: "completed" }] }] }
  expect(readResearchSessions("workflow", JSON.stringify([valid]))).toHaveLength(1)
})

describe("researchOutcome", () => {
  const turn = (patch: Partial<ResearchTurn>) => ({ streaming: false, errorMessage: null, validation: null, grounding: null, metadata: null, ...patch }) as ResearchTurn
  it("never calls an abstention or failed check a completed answer", () => {
    expect(researchOutcome(turn({ streaming: true }))).toBeUndefined()
    expect(researchOutcome(turn({}))).toBe("answered")
    expect(researchOutcome(turn({ errorMessage: "Cancelled." }))).toBe("stopped")
    expect(researchOutcome(turn({ validation: { passed: true, abstain: true } as ResearchTurn["validation"] }))).toBe("unverified")
    expect(researchOutcome(turn({ validation: { passed: false, abstain: false } as ResearchTurn["validation"] }))).toBe("unverified")
  })
})
