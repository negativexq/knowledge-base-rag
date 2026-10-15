import type { AnswerValidation, ChatMetadata, GroundingResult } from "@/api/types"

export type AnswerStatusKind = "verified" | "unverified" | "not_found" | "no_evidence"

export interface AnswerStatus {
  kind: AnswerStatusKind
  title: string
  reasons: string[]
}

// Validator failure codes (app/llm/structured_output.py and the critical-
// value validators) in plain words. Unknown codes are shown as-is.
const CODE_EXPLANATIONS: Record<string, string> = {
  OUTPUT_TRUNCATED: "The model ran out of room before finishing the answer.",
  TOP_LEVEL_SCHEMA_INVALID: "The model's answer was not in the expected format.",
  CRITICAL_VALUE_INDETERMINATE: "A number or value in the answer could not be matched to the cited text.",
  CRITICAL_VALUE_DIRECT_CONFLICT: "A number or value in the answer contradicts the cited text.",
  CRITICAL_VALIDATOR_INFRASTRUCTURE_FAILURE: "The answer could not be checked because the validator failed.",
  UNKNOWN_SUPPORT_ID: "The answer cited a passage it was not given.",
  HIDDEN_SUPPORT_ID: "The answer cited a passage that may not be shown.",
  UNAUTHORIZED_SUPPORT_ID: "The answer cited a passage outside your access.",
  EMPTY_SUPPORT_LIST: "Part of the answer cited no passage.",
  ANSWER_PART_SCHEMA_INVALID: "Part of the answer was empty or malformed.",
  NO_VALID_SUPPORT_BACKED_CLAIMS: "No part of the answer was backed by a cited passage.",
}

// Why the model was not called (app/api/chat.py::_generation_skip_reason).
const SKIP_EXPLANATIONS: Record<string, string> = {
  EMPTY_RERANK_RESULT: "Retrieval found no authorized passages for this question, so the model was not called.",
  NO_EVIDENCE_BLOCKS: "No evidence was left after evidence building, so the model was not called.",
}

export function explainCode(code: string): string {
  return CODE_EXPLANATIONS[code] ?? code
}

export function explainSkip(reason: string): string {
  return SKIP_EXPLANATIONS[reason] ?? `The model was not called (${reason}).`
}

export function describeDoneReason(reason: string | null | undefined): string {
  if (reason === "stop") return "Finished normally"
  if (reason === "length") return "Stopped at the length limit"
  return reason ? `Ended: ${reason}` : "End reason not reported"
}

/** The answer's verdict for the status line under it. The legacy path
 * reports citation integrity in a `grounding` event; the support-ID path in
 * the answer-level `security` event. Null while streaming or before any
 * verdict arrives. */
export function answerStatus(input: {
  streaming: boolean
  grounding?: GroundingResult | null
  validation?: AnswerValidation | null
  metadata?: ChatMetadata | null
  citesUnits: boolean
}): AnswerStatus | null {
  const { streaming, grounding, validation, metadata, citesUnits } = input
  if (streaming) return null
  if (grounding) {
    return grounding.grounded
      ? { kind: "verified", title: "Citation integrity verified", reasons: [] }
      : {
          kind: "unverified",
          title: "Citation validation failed",
          reasons: ["A citation did not match an authorized source."],
        }
  }
  if (metadata?.generation_skipped) {
    return { kind: "no_evidence", title: "No matching evidence", reasons: [explainSkip(metadata.generation_skipped)] }
  }
  if (!validation) return null
  if (!validation.passed) {
    return {
      kind: "unverified",
      title: "Citation validation failed",
      reasons: validation.validator_failure_codes.map(explainCode),
    }
  }
  if (validation.abstain || !citesUnits) {
    return { kind: "not_found", title: "Not found in the documents", reasons: [] }
  }
  return { kind: "verified", title: "Citation integrity verified", reasons: [] }
}
