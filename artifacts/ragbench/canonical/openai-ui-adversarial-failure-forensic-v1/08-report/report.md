# OPENAI UI adversarial failure forensic V1

## Scope and integrity

The frozen source matrix hash was verified as
`a8f7f721d35727aea8bc304280496f7dbbf50c7dd8b12c7ec1c34041dc763ef0`.
The original browser, trace, attribution, and report artifacts were not
modified. No provider, retrieval, HOLDOUT, or generation calls were made.

This report is forensic only. It does not rerun the matrix, recompute quality
metrics, or propose a fix.

## Evidence boundary

The frozen run persisted bounded UI summaries and selected Jaeger validator
attributes, but did not persist raw model output, raw model support IDs,
retrieval Top20, reranked Top5, final evidence snapshots, or internal
support-ID/citation-resolution decisions. Consequently the complete requested
chain cannot be reconstructed for any target case. Missing stages are marked
`NOT_RECOVERABLE_FROM_FROZEN_ARTIFACTS`; no inference is promoted to fact.

## Case findings

### T3, T4, T5

The visible result was unavailable and forced abstention occurred. Bounded
traces show T3/T5 `CRITICAL_VALUE_DIRECT_CONFLICT` and T4
`CRITICAL_VALUE_INDETERMINATE`, with baseline and V3 agreeing. The raw model
answer and evidence are absent. Therefore the initial polarity-blindness
attribution is not proven: zero cases confirm `CLAIM_POLARITY_FALSE_CONFLICT`,
and all three remain inconclusive.

### T6

The source corpus contains the explicit fact that OAuth tokens expire after 60
minutes. The run did not retain retrieval/evidence snapshots or raw output, so
retrieval miss, reranker loss, evidence-build loss, representation gap, and
generation behavior cannot be separated. The earlier retrieval attribution
remains a hypothesis, not a reconstructed cause.

### T8 and T12

Both had correct visible semantic answers and valid application-owned support
IDs. Additional source-like strings were present in model text. They were not
shown to be accepted by the citation resolver and did not create fake support
identity. This is model-output/UI presentation debt, not a security-boundary
failure.

### T10

The only recorded disagreement was `BASELINE_PASS_V3_IND`. The question uses
explicit family wording, but exact model claim/support specificity and the V3
reason were not retained. The disagreement is therefore
`FORENSIC_INCONCLUSIVE`; it cannot establish either safe V3 conservatism or a
V3 availability regression.

## Highest-confidence systemic finding

The highest-confidence systemic failure class is an **observability gap in
the frozen UI E2E artifact contract**: the run did not persist the bounded
intermediate records needed to attribute retrieval, evidence construction,
generation, polarity extraction, support-ID validation, and citation
resolution. This is an evidence limitation, not proof of a validator defect.

## Security

No fake citation, unauthorized support acceptance, hidden evidence leakage,
prompt injection leakage, or provider/network failure was observed. The
application-owned support IDs remained the authoritative citation identity.

## Status

- V3 primary: NO
- Production shadow: NO
- Canary: NO
- Production code modified by this task: NO
- Corrected HOLDOUT used: NO
- OpenAI/Ollama/embedding/BGE/retrieval calls: 0

## Follow-up routing

- If T3/T4/T5 need adjudication, first create a separate bounded forensic
  instrumentation plan that captures raw structured model output and evidence
  metadata without sensitive leakage. Only then consider a separately
  preregistered `VALIDATOR_V4_CLAIM_POLARITY_DEBUG_PREREGISTRATION` task.
- Route T6 to the SectionAware/evidence-selection track after evidence
  snapshots are available.
- Route T8/T12 to a separate output-contract/UI task.
- Do not tune V3 or use this incomplete attribution as canary evidence.
