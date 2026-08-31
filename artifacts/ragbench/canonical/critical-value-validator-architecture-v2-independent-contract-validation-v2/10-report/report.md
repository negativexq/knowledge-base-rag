# CRITICAL VALUE VALIDATOR ARCHITECTURE V2 — INDEPENDENT CONTRACT VALIDATION V2

This is a second, fresh, independently authored occurrence-level contract
validation. It is not a new TechQA HOLDOUT. The V1 failed verdict and its
`TEST_ANNOTATION_DEFECT` classification were preserved unchanged; `CORR13` was
not edited or rescored.

## Frozen execution

- Candidate: `CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1`
- 118 cases and 221 critical-value occurrences.
- Reviewer A and Reviewer B completed before candidate execution.
- Extraction, span, role, and corrective-pair labels were frozen before the
  single canonical execution.
- No provider, retrieval, BGE, or HOLDOUT calls.

## Review quality

- Extraction-label agreement: 100% (221/221).
- Role-label agreement: 100% (221/221).
- Exact-span agreement: 100% (221/221).
- Disagreements: 0.
- Disputed/excluded primary occurrences: 0.
- Corrective-pair inversions before freeze: 0.
- Non-extractor-owned scored spans: 0.
- Missing rationales: 0.

## Result

Architecture V2 observed all 221 expected occurrences. Missing, spurious,
nested, boundary, ID-collision, global-collapse, sibling-contamination,
type-identity, claim-association, and role-to-value-rejoin errors were all
zero. No real factual assertion or ambiguous occurrence was skipped.

There were 49 correct rejected-premise skips and 8 missed skips out of 57
rejected-premise occurrences: 86.0% corrective recovery, above the frozen
80% threshold. V3 semantic equivalence mismatches were zero across numeric,
duration, percentage, date, locale, version, identifier/sign, and
INDETERMINATE outcomes.

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_INDEPENDENT_CONTRACT_VALIDATION_V2_PASSED`

All L1-L5, A1-A10, S1-S8, and I-G1-I-G7 gates passed. The stopping rule is
satisfied. Architecture V2 is eligible for a separate production-integration
review, but it was not integrated, activated, or added to the selector.

## Full suite

Focused occurrence/role/V3 tests passed: 45 passed. The full deterministic
run completed with `1230 passed, 1 skipped, 6 deselected, 5 warnings`; no
Qdrant errors returned in this run. The three Qdrant errors from the prior V1
full run remain separately documented as environment-dependent fixture
failures with zero task-caused regressions.

## Scope discipline

T4 boolean normalization, T6 unit equivalence, T10 version semantics,
INDETERMINATE policy, retrieval, BGE, and the consumed corrected HOLDOUT were
not changed or reopened. BGE remains
`BGE_REMOVAL_NOT_SUPPORTED`.
