# Proposed API contract

Design-only interfaces for a future V7 implementation.

```text
extract_critical_occurrences(
    text: str,
) -> tuple[CriticalValueOccurrence, ...]
```

The extractor is the sole owner of lexical spans, type ownership, overlap
resolution, raw literal capture, and deterministic occurrence IDs. It returns
an immutable tuple. It emits no nested substring occurrence unless the
contract declares the nested text independently lexical.

```text
classify_occurrence_roles(
    occurrences: tuple[CriticalValueOccurrence, ...],
    query_context: QueryOccurrenceContext,
    evidence_context: EvidenceOccurrenceContext,
) -> tuple[OccurrenceRoleDecision, ...]
```

The classifier receives occurrence objects, not a raw answer to scan. Bounded
context may be sliced using the occurrence's original span, but no new
occurrence may be created. Same normalized values remain separate IDs.

```text
validate_occurrences(
    occurrences: tuple[CriticalValueOccurrence, ...],
    evidence: EvidenceOccurrenceContext,
) -> CriticalValueValidationResult
```

Only decisions with role `VALIDATE` or `AMBIGUOUS_KEEP_VALIDATING` enter this
operation. The validator consumes occurrence objects or an occurrence-aware
view; it does not receive a masked string and re-run extraction. Its
normalization, version, identifier/sign, locale, numeric, and
`INDETERMINATE` semantics remain the frozen V3 responsibility.

## Contract rules

1. A role decision must reference an existing occurrence ID.
2. Every occurrence ID maps to exactly one `(start, end)` span in one source
   text.
3. Validation results attach to IDs and do not mutate identity fields.
4. Unknown role is represented by `AMBIGUOUS_KEEP_VALIDATING`, never SKIP.
5. The application can audit extraction, role, validation, and final outcome
   without reconstructing spans from normalized values.
