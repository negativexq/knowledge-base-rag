import type { CalculationSummary, RetrievedSource, SupportUnitRef } from "@/api/types"

export interface FollowUpInput {
  question: string
  outcome: "answered" | "unverified" | "stopped" | undefined
  sources: RetrievedSource[]
  citedUnits: SupportUnitRef[]
  calculations: CalculationSummary[]
}

const MAX_SUGGESTIONS = 3

function shorten(text: string, limit = 60): string {
  const clean = text.replace(/\s+/g, " ").trim()
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean
}

// Follow-up questions built from what this answer actually used: its cited
// section, its calculation and the other documents it found. No model call.
export function followUpQuestions({ question, outcome, sources, citedUnits, calculations }: FollowUpInput): string[] {
  if (!outcome || outcome === "stopped") return []
  const suggestions: string[] = []
  const cited = citedUnits[0]
  const citedSource = cited ? sources.find((source) => source.rank === cited.source_rank) : undefined
  const document = citedSource?.source_id ?? cited?.source_id
  if (outcome === "answered") {
    const calculation = calculations[0]
    if (calculation) {
      const labels = calculation.inputs.map((input) => input.label).filter(Boolean)
      if (labels.length) suggestions.push(`Show ${labels.slice(0, 3).join(", ")} side by side in a table`)
    }
    if (cited?.section_label && document) suggestions.push(`Summarize the "${shorten(cited.section_label, 50)}" section of ${document}`)
  }
  const others = [...new Set(sources.map((source) => source.source_id).filter((id): id is string => Boolean(id) && id !== document))]
  if (others[0]) {
    suggestions.push(outcome === "answered"
      ? `Does ${others[0]} say anything different about: ${shorten(question)}`
      : `Look only in ${others[0]}: ${shorten(question)}`)
  }
  return [...new Set(suggestions)].slice(0, MAX_SUGGESTIONS)
}
