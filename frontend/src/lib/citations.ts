import type { RetrievedSource, SupportUnitRef } from "@/api/types"

// Legacy tag, mirroring app/llm/grounding.py's _CITATION_RE exactly:
// r"\[s\.([\w\-]+):([^/\]]+)/([^\]]+)\]"
// or a support ID ("[E1.S4]"), as rendered by
// app/llm/structured_output.py::render_support_unit_answer.
const CITATION_RE = /\[s\.([\w-]+):([^/\]]+)\/([^\]]+)\]|\[(E\d+\.S\d+)\]/g

export interface AnswerSegment {
  type: "text" | "citation"
  text: string
  source?: RetrievedSource
  unit?: SupportUnitRef
  valid: boolean
}

/** Splits a streamed answer into text/citation segments. A legacy tag
 * matches its source card by EXACT (source_type, source_id,
 * citation_location) identity — the same triple
 * app/llm/grounding.py::check_grounding validates against. A support ID
 * matches only a unit the model was actually given (`supportUnits`, from
 * the metadata event) and then that unit's card by rank. A citation with
 * no match is marked invalid (never silently dropped) so the UI can
 * render the citation-integrity warning.
 */
export function splitAnswerIntoSegments(
  answer: string,
  sources: RetrievedSource[],
  supportUnits: SupportUnitRef[] = [],
): AnswerSegment[] {
  const segments: AnswerSegment[] = []
  let lastIndex = 0
  CITATION_RE.lastIndex = 0

  for (const match of answer.matchAll(CITATION_RE)) {
    const [full, sourceType, sourceId, location, supportId] = match
    const start = match.index ?? 0
    if (start > lastIndex) {
      segments.push({ type: "text", text: answer.slice(lastIndex, start), valid: true })
    }
    if (supportId) {
      const unit = supportUnits.find((u) => u.support_id === supportId)
      const source = unit && sources.find((s) => s.rank === unit.source_rank)
      segments.push({ type: "citation", text: full, source, unit, valid: Boolean(unit && source) })
    } else {
      const source = sources.find(
        (s) => s.source_type === sourceType && s.source_id === sourceId && s.citation_location === location,
      )
      segments.push({ type: "citation", text: full, source, valid: Boolean(source) })
    }
    lastIndex = start + full.length
  }
  if (lastIndex < answer.length) {
    segments.push({ type: "text", text: answer.slice(lastIndex), valid: true })
  }
  return segments
}
