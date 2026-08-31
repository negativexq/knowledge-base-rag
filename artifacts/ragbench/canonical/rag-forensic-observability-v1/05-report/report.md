# RAG forensic observability V1 report

## Decision

`RAG_FORENSIC_OBSERVABILITY_V1_PASSED`

The opt-in local recorder covers the required pipeline boundaries without
changing validator, retrieval, BGE, evidence-builder, generation, support-ID,
or citation semantics when disabled. A synthetic controlled capture answered
all 13 forensic questions.

## Scope

This is controlled forensic capture for local/debug/evaluation replay. It is
not normal production logging. Defaults are disabled:

- `RAG_FORENSIC_CAPTURE_ENABLED=false`
- `RAG_FORENSIC_CAPTURE_RAW_TEXT=false`

Raw text is written only to a server-controlled local directory when both
switches are explicitly enabled. OTel receives bounded metadata only.

## Covered stages

The record covers RRF candidates, BGE output, EvidenceBuildResult metadata and
final blocks, support units, raw structured generation result in explicit raw
mode, model support IDs, support-ID validation, critical-validator inputs and
results, forced-abstain transition, citation resolution, and visible outcome.

## Privacy and failure behavior

Raw query/evidence/model text is not sent to OTel. Secret-like fields are
redacted before local serialization. Capture write failures are warnings and
do not fail answer delivery. The capture directory is not request-controlled.

## Replay status

T3, T4, T5, T6, and T10 were **not replayed**. This task only establishes and
verifies the capture contract. No HOLDOUT or external provider was used.
