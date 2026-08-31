# Validator V6 occurrence-boundary safety DEBUG report

This is a deterministic DEBUG challenger, not a production change and not a
new TechQA HOLDOUT. The primary scoring unit is
`CRITICAL_VALUE_OCCURRENCE`; the fresh population contains 76 cases, 154
independently scored occurrences, and 84 nested-match expectations.

## Integrity

V5 was verified before V6 implementation using its frozen source and helper
hashes. The V5 helper region, V4 helper region, V5 artifacts, and C57 history
were not modified. V6 source was frozen before execution and its source hash
was unchanged after execution. No provider, retrieval, embedding, or BGE
calls were made.

## Boundary results

| metric | V5 | V6 |
|---|---:|---:|
| expected occurrences | 154 | 154 |
| observed exact occurrences | 120 | 151 |
| missing expected occurrences | 34 | 3 |
| spurious nested occurrences | 34 | 0 |
| signed boundary collision errors | 34 | 0 |
| prefix collision errors | 0 | 0 |
| global collapse errors | 4 | 4 |
| type-mismatch role errors | 23 | 4 |

V6 removed the signed/nested boundary collisions and preserved the standalone
siblings. Three expected spans were not emitted because the frozen population
used non-extractor-owned spans (`version 3`, `9.x`, and `9.1.2` with prefix
handling); these remain recorded and were not relabeled after execution.

## Polarity results

| metric | V5 | V6 |
|---|---:|---:|
| real assertions incorrectly skipped | 0 | 0 |
| ambiguous incorrectly skipped | 0 | 0 |
| rejected premises not skipped | 12 | 12 |
| correct rejected-premise skips | 25 | 25 |
| corrective recovery | 67.57% | 67.57% |
| multi-occurrence role errors | 12 | 12 |

The remaining role errors are conservative misses on polarity variants that
were labeled as rejected premises but are not recognized by the frozen V5
polarity rules. They are not repaired in V6 because V6 is boundary-only.

## C57 regression

For `The signed result is -204, not 204.` V5 emitted an inner `204` span plus
the standalone span. V6 emits `-204` at span `21:25` as a positive assertion
and standalone `204` at span `31:34` as a rejected premise. No nested inner
occurrence is emitted. The C57 anchor passes.

## Decision

G1–G6 and G8–G12 pass. G7 fails because the strict frozen DEV scoring still
contains four global-collapse and four type-mismatch role errors. Since all
gates are required, no V6 candidate was selected. V6 is frozen and must not be
patched in place; future boundary/polarity work becomes V7.

T4 boolean normalization, T6 unit equivalence, T10 version semantics,
production defaults, retrieval, BGE, and the consumed HOLDOUT remain
unchanged. V6 was not added to production.
