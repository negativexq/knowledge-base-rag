# Proposed canonical occurrence model

This is a design contract only; it is not implemented by this checkpoint.

## Immutable extraction object

```text
CriticalValueOccurrence (immutable)
  occurrence_id: str
  source_text_span_start: int
  source_text_span_end: int
  raw_literal: str
  normalized_value: str
  lexical_type: CriticalValueType
  unit: str | None
  claim_unit_id: str
  extraction_source: str
  overlap_group_id: str | None
  parent_occurrence_id: str | None
```

`occurrence_id` is a deterministic local ID for one exact extractor-owned
span. It is never derived solely from normalized value or type. Identity
fields are frozen after extraction. `claim_unit_id` is an association, not a
replacement for the span identity.

## Role decision object

```text
OccurrenceRoleDecision (separate object)
  occurrence_id: str
  role: VALIDATE | SKIP_REJECTED_PREMISE | AMBIGUOUS_KEEP_VALIDATING
  reason_code: SUPPORTED_ASSERTION | QUERY_ECHO_REJECTED_PREMISE |
               AMBIGUOUS_ROLE | NON_INDEPENDENT_NESTED_MATCH |
               NO_POLARITY_EXCEPTION
  confidence_class: DETERMINISTIC | AMBIGUOUS
```

Role classification cannot mutate the occurrence. Runtime filtering maps both
`VALIDATE` and `AMBIGUOUS_KEEP_VALIDATING` to validation; only a
deterministically established `SKIP_REJECTED_PREMISE` can be excluded.

## Lexical ownership

The extractor owns complete lexical extents: `-204`, `+42`, `8.1.2`,
`30 days`, `10%`, `CVE-2025-1234`, and `2026-08-31`. Numeric subparts are not
independent unless the extractor explicitly emits a separate non-overlapping
occurrence. A later standalone `204` in `-204, not 204` is independent.

## Overlap policy

An extractor-owned full typed literal wins over a contained candidate. The
contained candidate is recorded as non-independent diagnostic evidence, not a
role-bearing occurrence. Non-overlapping siblings are retained. If overlap
cannot be resolved deterministically, both remain validation obligations or
the occurrence is marked ambiguous; it is never skipped by polarity.

## Role inputs

The role classifier may inspect the exact occurrence, bounded local clause
context, query occurrence context, evidence occurrence context, supported
alternatives, and claim-local ordering. It must not rediscover occurrences
from raw text, perform global value masks, or use an LLM/NLI classifier.
