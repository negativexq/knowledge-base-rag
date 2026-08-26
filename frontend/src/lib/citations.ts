import type { RetrievedSource } from "@/api/types"

// Mirrors app/llm/grounding.py's _CITATION_RE exactly:
// r"\[s\.([\w\-]+):([^/\]]+)/([^\]]+)\]"
const CITATION_RE = /\[s\.([\w-]+):([^/\]]+)\/([^\]]+)\]/g

export interface AnswerSegment {
  type: "text" | "citation"
  text: string
  source?: RetrievedSource
  valid: boolean
}

/** Splits a streamed answer into text/citation segments, matching each
 * citation tag to its source card by EXACT (source_type, source_id,
 * citation_location) identity — the same triple
 * app/llm/grounding.py::check_grounding validates against. A tag with
 * no matching authorized source is marked invalid (never silently
 * dropped) so the UI can render Sprint 24's citation-integrity warning.
 */
export function splitAnswerIntoSegments(
  answer: string,
  sources: RetrievedSource[],
): AnswerSegment[] {
  const segments: AnswerSegment[] = []
  let lastIndex = 0
  CITATION_RE.lastIndex = 0

  for (const match of answer.matchAll(CITATION_RE)) {
    const [full, sourceType, sourceId, location] = match
    const start = match.index ?? 0
    if (start > lastIndex) {
      segments.push({ type: "text", text: answer.slice(lastIndex, start), valid: true })
    }
    const source = sources.find(
      (s) => s.source_type === sourceType && s.source_id === sourceId && s.citation_location === location,
    )
    segments.push({ type: "citation", text: full, source, valid: Boolean(source) })
    lastIndex = start + full.length
  }
  if (lastIndex < answer.length) {
    segments.push({ type: "text", text: answer.slice(lastIndex), valid: true })
  }
  return segments
}
