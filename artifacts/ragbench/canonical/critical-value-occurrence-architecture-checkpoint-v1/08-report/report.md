# Critical Value Occurrence Architecture Checkpoint V1

## Decision

**OCCURRENCE_ARCHITECTURE_REDESIGN_SUPPORTED**

The audit establishes that V4, V5, and V6 are incremental debug helpers over a
temporary token-dictionary and mask/re-extract design. V6 solved the specific
signed/nested lexical boundary, but its diagnostic IDs do not cross the
validation boundary and the inherited V5 role classifier still rejoins values
by normalized value/type context. The remaining V6 metrics therefore support a
canonical occurrence ledger rather than another isolated regex patch.

## Evidence-backed progression

- V4 loses equal-value sibling role separation at role classification.
- V5 loses C57 identity at extraction because `204` inside `-204` is emitted as
  a separate candidate; masking/re-extraction propagates the error.
- V6 restores sign and typed lexical ownership, reducing spurious nested and
  signed-boundary errors from 34 to 0.
- V6 still reports 4 global-collapse, 4 type-mismatch, and 12 role errors.
  The global and type-mismatch counters overlap on S03, S14, P02, and P06.
  The remaining eight role misses are conservative inherited V5 role misses.
- Three version-slice expected spans are not extractor-owned. They are a
  mixed test-annotation/contract finding; frozen history is not rewritten.

## Proposed ownership boundary

`EXTRACTION -> immutable occurrence ledger -> occurrence-local role
classification -> structured VALIDATE filter -> frozen V3 value validation`.

Extraction decides what exact lexical occurrences exist. Role classification
decides what that occurrence means. Value validation checks only occurrences
whose role requires validation. No downstream layer re-searches the answer or
reconstructs a global role from normalized values.

## Complexity direction

The proposed dataflow is simpler despite adding explicit types: one canonical
claim extraction, one role pass, one structured filter, and one V3 comparison
pass. It removes the current mask and re-extraction boundary and avoids
repeated sibling/value remapping. Support extraction remains a separate
evidence-side operation; no retrieval or evidence-selection behavior changes.

## Production and history

No production source or selector was changed by this checkpoint. V3 remains
the validated frozen candidate, but not primary. V4 and V5 remain closed; V6
remains closed after its failed debug gate. The corrected HOLDOUT remains
consumed and unused. The BGE verdict remains
`BGE_REMOVAL_NOT_SUPPORTED`.
