# V7 scope preview

## Proposed candidate scope

`CANONICAL_OCCURRENCE_LEDGER + OCCURRENCE_LOCAL_ROLE_FILTERING`

The challenger should implement one canonical extraction pass, immutable
occurrence identity, occurrence-local role decisions, structured filtering,
and delegation to frozen V3 value validation. This is a preview only; no V7
candidate, population, or execution is created in this checkpoint.

## Intended exclusions

- T4 boolean normalization
- T6 unit equivalence
- T10 version semantics
- `INDETERMINATE` policy
- new normalization rules
- new broad polarity semantics
- retrieval/reranking/evidence changes
- production selector/default changes

## Preregistration requirements for the next task

The next task must freeze the source manifest, occurrence contract, extraction
ownership rules, overlap policy, fresh occurrence-level population, and hard
safety gates before implementation results are inspected. It must score
extraction identity separately from role decisions and must preserve all V3,
V4, V5, and V6 history.
