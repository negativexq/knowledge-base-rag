# V7 migration plan

This plan is intentionally limited to occurrence identity and role filtering.

1. Introduce a small immutable canonical occurrence model and a separate role
   decision model.
2. Make one canonical extractor return an immutable occurrence ledger with
   exact extractor-owned spans, raw literals, normalized values, types, and
   overlap metadata.
3. Port the existing V4/V5 polarity decisions to occurrence IDs and bounded
   claim-local context. Preserve the existing conservative fallback.
4. Eliminate global/value masks and any role decision keyed only by value or
   value plus type.
5. Eliminate mask → re-extract. If a temporary compatibility adapter is
   unavoidable, require length-preserving span mapping and prove no identity
   loss before use; preferred V7 path is structured filtering.
6. Delegate only `VALIDATE` and ambiguous/unknown occurrences to frozen V3
   value validation. Do not alter V3 normalization, version, identifier/sign,
   locale, numeric, or `INDETERMINATE` semantics.
7. Add compact reusable tests for signed ownership, nested suppression,
   same-value siblings, type-mismatch siblings, reversed role order, and
   ambiguous overlap fail-safe behavior.
8. Run a fresh DEBUG population after the architecture and tests are frozen.
   Do not use the consumed HOLDOUT and do not activate V7 in production.

## Explicit exclusions

T4 boolean normalization, T6 unit equivalence, T10/version policy,
`INDETERMINATE` policy, new semantic polarity heuristics, retrieval, BGE,
Top-N, SectionAware, evidence budget, prompts, provider, and production
selector changes are outside V7.

## Safety gates for the future implementation

Require zero real-assertion skips, zero ambiguous skips, zero global-value
collapse, zero nested collisions, zero type-mismatch identity loss, zero
same-value sibling contamination, zero query-echo unsafe skips, and zero V3
semantic regression.
