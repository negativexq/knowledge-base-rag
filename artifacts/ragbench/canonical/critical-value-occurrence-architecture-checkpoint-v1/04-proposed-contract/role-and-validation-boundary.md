# Extraction, role, and validation boundaries

## Layer 1 — extraction

Input is one source text. Output is the complete immutable tuple of
extractor-owned `CriticalValueOccurrence` objects plus non-scored overlap
diagnostics. This layer owns lexical boundaries for signs, versions,
durations, percentages, identifiers, and dates. It does not decide whether a
literal is a rejected premise.

## Layer 2 — role classification

Input is the immutable occurrence tuple and bounded context objects. Output is
one `OccurrenceRoleDecision` per occurrence. It may use query echo, local
clause ordering, and a supported alternative as deterministic signals. It may
not search for normalized values, create a second token population, or mutate
an occurrence. Unknown and ambiguous roles map to validation.

## Layer 3 — value validation

Input is the occurrence-aware validation subset and evidence occurrence data.
Only `VALIDATE` and `AMBIGUOUS_KEEP_VALIDATING` enter this layer. It retains
the frozen V3 responsibilities: numeric comparison, locale ambiguity,
version specificity, identifier/sign handling, and conservative
`INDETERMINATE`. It does not interpret discourse polarity.

## Why masking is not the canonical boundary

Masking is a compatibility technique that changes the text passed to V3. It
requires V3 to discover the remaining literals again, so an occurrence ID
cannot prove that a validation result refers to the original span. Structured
filtering allows the exact role decision to cross the boundary without
changing text or offsets.
