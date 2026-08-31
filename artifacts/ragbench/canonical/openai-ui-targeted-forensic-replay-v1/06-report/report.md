# OPENAI UI TARGETED FORENSIC REPLAY V1

## Protocol

- Fixed order: `T3, T4, T5, T6, T10`.
- Original matrix SHA256: `a8f7f721d35727aea8bc304280496f7dbbf50c7dd8b12c7ec1c34041dc763ef0`.
- Replay protocol SHA256: `0128d058b6889abc760f3cf6d4d90c47cbbb270c8a1e50d4106115b539b819c9`.
- Provider/model: `openai / gpt-5.6-luna`.
- Runtime: RAG V2 and support IDs enabled; baseline authoritative; V3 shadow enabled.
- Raw forensic capture enabled only in the task-owned local directory.
- OpenAI calls: 5; technical retries: 0.

## Replay validity

All five cases produced exactly one immutable capture record. All browser requests returned 200 and completed SSE. No technical-invalid case occurred. Original matrix and prior artifacts were not modified.

## Stage transition

All five required facts were PRESENT → PRESENT → PRESENT across Top20 → Top5 → final evidence. No retrieval miss, reranker loss, or evidence-build loss was observed for the target facts.

## Attribution

- T3: `CLAIM_POLARITY_FALSE_CONFLICT` (HIGH). Corrective raw answer; 90 direct support, 30 direct conflict; validator forced abstain.
- T4: `CRITICAL_VALUE_NORMALIZATION_GAP` (HIGH). Corrective raw answer; extractor treated leading `No` as BOOLEAN and did not extract 500 in this path. Strict polarity-blindness criterion is not proven.
- T5: `CLAIM_POLARITY_FALSE_CONFLICT` (HIGH). Corrective raw answer; 120 direct support, 100 direct conflict; validator forced abstain.
- T6: `UNIT_EQUIVALENCE_GAP` (HIGH). Evidence contains 60 minutes; raw answer adds equivalent 1 hour; frozen validator has no unit conversion for this comparison.
- T10: `VERSION_SPECIFICITY_CONSERVATISM` (HIGH). V3 indeterminate is frozen-contract compliant because the model claim lacks explicit family scope; baseline pass is overly permissive.

## Boundary

This is local replay evidence only. No V4, validator change, prompt/retrieval change, production shadow, canary, or production correctness claim follows.
