import type { ResearchStep, ClarificationReply, Clarification, ComparisonRow, AnswerValidation, ChatMetadata, GroundingResult, Identity, RetrievalReportPayload, RetrievedSource } from "@/api/types"
import { API_BASE_URL } from "@/api/client"
import { answerStatus } from "@/lib/answerStatus"
import { splitAnswerIntoSegments } from "@/lib/citations"

export interface ResearchTurn {
  question: string
  sourceIds?: string[]
  clarificationReply?: ClarificationReply
  steps?: ResearchStep[]
  clarification?: Clarification | null
  comparison?: ComparisonRow[]
  answer: string
  sources: RetrievedSource[]
  report: RetrievalReportPayload | null
  grounding: GroundingResult | null
  validation: AnswerValidation | null
  metadata: ChatMetadata | null
  streaming: boolean
  errorMessage: string | null
  // Client-observed SSE event times, never inferred backend durations.
  firstTokenAt: number | null
  lastTokenAt: number | null
  groundingAt: number | null
  askStartedAt: number | null
}

export interface EvidencePin {
  turnIndex: number
  sourceRank: number
  supportId: string | null
}

export interface ResearchNote {
  id: string
  text: string
  evidence: EvidencePin | null
  createdAt: string
  updatedAt: string
}

export interface ResearchSession {
  id: string
  title: string
  customTitle: boolean
  starred: boolean
  pinned: boolean
  createdAt: string
  updatedAt: string
  turns: ResearchTurn[]
  pins: EvidencePin[]
  notes: ResearchNote[]
}

export function researchScope(identity: Identity): string {
  // Partition browser snapshots by deployment, identity and role context.
  // No bearer token is written into research history.
  return `kb-console.research.v1:${encodeURIComponent(JSON.stringify([API_BASE_URL, identity.tenant_id, identity.user_id, [...identity.roles].sort()]))}`
}

export function newResearchSession(): ResearchSession {
  const now = new Date().toISOString()
  return { id: crypto.randomUUID(), title: "Untitled research", customTitle: false, starred: false, pinned: false, createdAt: now, updatedAt: now, turns: [], pins: [], notes: [] }
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null
function isTurn(value: unknown): value is ResearchTurn {
  if (!record(value) || typeof value.question !== "string" || typeof value.answer !== "string" || !Array.isArray(value.sources)) return false
  if (!value.sources.every((source) => record(source) && typeof source.rank === "number" && typeof source.snippet === "string" && Array.isArray(source.heading_path))) return false
  if (value.sourceIds != null && (!Array.isArray(value.sourceIds) || !value.sourceIds.every((id) => typeof id === "string"))) return false
  if (value.steps != null && (!Array.isArray(value.steps) || !value.steps.every((step) => record(step) && typeof step.id === "string" && typeof step.operation === "string" && ["running", "completed", "retrying", "failed"].includes(String(step.status))))) return false
  if (value.clarification != null && (!record(value.clarification) || typeof value.clarification.question !== "string" || !Array.isArray(value.clarification.options) || !value.clarification.options.every((item) => typeof item === "string"))) return false
  if (value.clarificationReply != null && (!record(value.clarificationReply) || typeof value.clarificationReply.question !== "string" || typeof value.clarificationReply.answer !== "string")) return false
  if (value.comparison != null && (!Array.isArray(value.comparison) || !value.comparison.every((row) => record(row) && typeof row.aspect === "string" && Array.isArray(row.cells) && row.cells.every((cell) => record(cell) && typeof cell.source_id === "string" && typeof cell.text === "string" && Array.isArray(cell.support_ids) && cell.support_ids.every((id) => typeof id === "string"))))) return false
  if (value.report != null && (!record(value.report) || !Array.isArray(value.report.stages))) return false
  if (value.metadata != null && (!record(value.metadata) || (value.metadata.support_units != null && !Array.isArray(value.metadata.support_units)))) return false
  if (value.validation != null && (!record(value.validation) || !Array.isArray(value.validation.validator_failure_codes))) return false
  if (value.grounding != null && (!record(value.grounding) || !Array.isArray(value.grounding.citations_found))) return false
  return value.streaming === false && (value.errorMessage == null || typeof value.errorMessage === "string")
}

export function readResearchSessions(scope: string, snapshot?: string): ResearchSession[] {
  try {
    const parsed: unknown = JSON.parse(snapshot ?? localStorage.getItem(scope) ?? "[]")
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is ResearchSession => record(item)
      && typeof item.id === "string" && typeof item.title === "string"
      && typeof item.customTitle === "boolean" && typeof item.starred === "boolean"
      && typeof item.createdAt === "string" && typeof item.updatedAt === "string"
      && Array.isArray(item.turns) && item.turns.every(isTurn) && (item.turns.length > 0 || (Array.isArray(item.notes) && item.notes.length > 0))
      && Array.isArray(item.pins) && item.pins.every((pin: unknown) => record(pin)
        && Number.isInteger(pin.turnIndex) && Number.isInteger(pin.sourceRank)
        && (pin.supportId === null || typeof pin.supportId === "string")))
      .map((session) => ({ ...session, pinned: session.pinned === true, notes: Array.isArray(session.notes) ? session.notes.filter((note) => record(note)
        && typeof note.id === "string" && typeof note.text === "string"
        && typeof note.createdAt === "string" && typeof note.updatedAt === "string"
        && (note.evidence === null || (record(note.evidence) && Number.isInteger(note.evidence.turnIndex)
          && Number.isInteger(note.evidence.sourceRank) && (note.evidence.supportId === null || typeof note.evidence.supportId === "string")))) : [] }))
  } catch {
    return []
  }
}

export const samePin = (left: EvidencePin, right: EvidencePin) => left.turnIndex === right.turnIndex && left.sourceRank === right.sourceRank && left.supportId === right.supportId

export function resolvePin(session: ResearchSession, pin: EvidencePin) {
  const turn = session.turns[pin.turnIndex]
  const source = turn?.sources.find((item) => item.rank === pin.sourceRank)
  const unit = pin.supportId ? turn?.metadata?.support_units?.find((item) => item.support_id === pin.supportId && item.source_rank === pin.sourceRank) : undefined
  if (!source || (pin.supportId && !unit)) return null
  return { turn, source, unit, text: unit?.text ?? source.snippet }
}

const plain = (value: string) => value.replace(/[\\`*_{}[\]<>#|!]/g, "\\$&").replace(/\r?\n/g, " ")
const quote = (value: string) => value.split(/\r?\n/).map((line) => `> ${line}`).join("\n")

/** Resolve references using exactly the same citation mapping as the UI. */
export function researchMarkdown(session: ResearchSession): string {
  const output = [`# ${plain(session.title)}`, `Updated: ${session.updatedAt}`, "Source: browser research history"]
  session.turns.forEach((turn, index) => {
    if (turn.streaming) return
    const segments = splitAnswerIntoSegments(turn.answer, turn.sources, turn.metadata?.support_units ?? [])
    const references = new Map<string, { id: string; source: RetrievedSource; text: string; supportId?: string; section?: string | null }>()
    const answer = segments.map((segment) => {
      if (segment.type === "text") return segment.text
      if (!segment.valid || !segment.source) return `${plain(segment.text)} (unresolved citation)`
      const key = `${segment.source.rank}:${segment.unit?.support_id ?? "source"}`
      if (!references.has(key)) references.set(key, {
        id: `a${index + 1}r${references.size + 1}`,
        source: segment.source,
        text: segment.unit?.text ?? segment.source.snippet,
        supportId: segment.unit?.support_id,
        section: segment.unit?.section_label,
      })
      return `[^${references.get(key)!.id}]`
    }).join("")
    const status = answerStatus({ ...turn, citesUnits: segments.some((segment) => Boolean(segment.valid && segment.unit)) })
    output.push(`## Question ${index + 1}`, plain(turn.question))
    if (turn.clarificationReply) output.push(`Clarification: ${plain(turn.clarificationReply.question)} — ${plain(turn.clarificationReply.answer)}`)
    if (turn.clarification) output.push(`Clarification requested: ${plain(turn.clarification.question)}`)
    if (turn.comparison?.length) {
      const docs = [...new Set(turn.comparison.flatMap((row) => row.cells.map((cell) => cell.source_id)))]
      output.push("### Comparison", `| Aspect | ${docs.map(plain).join(" | ")} |`, `| --- | ${docs.map(() => "---").join(" | ")} |`)
      for (const row of turn.comparison) output.push(`| ${plain(row.aspect)} | ${docs.map((doc) => {
        const cell = row.cells.find((item) => item.source_id === doc)
        if (!cell) return "—"
        const cites = cell.support_ids.map((id) => {
          const unit = turn.metadata?.support_units?.find((item) => item.support_id === id)
          const ref = references.get(`${unit?.source_rank}:${id}`)
          return ref ? `[^${ref.id}]` : `${plain(id)} (unresolved citation)`
        }).join(" ")
        return `${plain(cell.text)} ${cites}`
      }).join(" | ")} |`)
    } else output.push("### Answer", answer || "No answer returned.")
    if (turn.errorMessage) output.push(`Request status: ${plain(turn.errorMessage)}`)
    output.push(`Validation: ${status?.title ?? "Not reported"}`)
    if (status?.reasons.length) output.push(...status.reasons.map((reason) => `- ${plain(reason)}`))
    for (const reference of references.values()) {
      const { source } = reference
      const location = [source.page_number != null ? `Page ${source.page_number}` : null, reference.section ?? source.heading_path?.join(" / "), source.citation_location, source.document_version ? `Version ${source.document_version}` : null, reference.supportId].filter(Boolean).join(" · ")
      output.push(`[^${reference.id}]: ${plain(source.source_id ?? "Unknown source")} (${plain(source.source_type ?? "unknown")})${location ? ` · ${plain(location)}` : ""}\n\n${quote(reference.text).split("\n").map((line) => `    ${line}`).join("\n")}`)
    }
  })
  const pins = session.pins.map((pin) => ({ pin, evidence: resolvePin(session, pin) })).filter((entry) => entry.evidence)
  if (pins.length) {
    output.push("## Pinned evidence")
    for (const { pin, evidence } of pins) {
      output.push(`### ${plain(evidence!.source.source_id ?? "Unknown source")}`, `Question ${pin.turnIndex + 1}${evidence!.unit?.section_label ? ` · ${plain(evidence!.unit.section_label)}` : ""}`, quote(evidence!.text))
    }
  }
  if (session.notes?.length) {
    output.push("## Personal research notes")
    for (const note of session.notes) {
      output.push(`### Note · ${note.updatedAt}`, quote(note.text))
      const evidence = note.evidence && resolvePin(session, note.evidence)
      if (evidence) output.push(`Linked evidence: ${plain(evidence.source.source_id ?? "Unknown source")} · Question ${note.evidence!.turnIndex + 1}${evidence.unit?.section_label ? ` · ${plain(evidence.unit.section_label)}` : ""}`)
    }
  }
  return `${output.join("\n\n")}\n`
}

export function downloadResearch(session: ResearchSession): void {
  const blob = new Blob([researchMarkdown(session)], { type: "text/markdown;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `${session.title.replace(/[^\p{L}\p{N}\s_-]/gu, "").trim().slice(0, 80) || "research"}.md`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
