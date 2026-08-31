# Current architecture versus Architecture V2

## Audit finding

The legacy experimental path is `extract -> normalize/type-match -> sibling
re-search -> raw-text masking -> re-extract -> value/type rejoin -> V3`.
V4 and V5 make the masking decision from value/type or span-derived records,
but validation re-enters the V3 extractor. V6 improves lexical ownership and
removes nested candidates, but still delegates through `_v6_mask_rejected_premises`
and a masked-answer re-extraction. V6 occurrence IDs are diagnostic; they are
not the identity passed to V3.

This explains the historical `VALUE_LEVEL_COLLAPSE`, C57 signed-subspan
collision, and remaining role-to-value rejoin/sibling contamination classes.

## Architecture V2

Architecture V2 introduces `CriticalValueOccurrence` as an immutable,
span-owned object. `extract_critical_occurrences()` performs the one
identity-bearing extraction. `classify_occurrence_roles()` receives those
objects and only uses each known span plus bounded context. It cannot discover
new literals, build a value mask, or mutate the ledger. `validate_occurrences_v3()`
adapts the selected occurrence objects to the frozen V3 comparison primitives;
support text is separately extracted once per support unit, not by re-extracting
a masked answer.

The V2 path is experimental/debug-only. The production selector remains
`baseline|v3`; no default, retrieval, prompt, provider, or V3 comparison rule
is changed.

## Ownership boundary

Architecture V2 owns extraction, lexical ownership/overlap resolution,
occurrence identity, claim association, occurrence-local role classification,
and structured filtering. Frozen V3 owns normalization/comparison, locale
ambiguity, version specificity, signed identifier behavior, and final
critical-value result semantics.
