# Phase 6 — Answerability Research Decision

Status: **PHASE_6_CLOSED_NOT_PROMOTED**

This decision record closes the answerability research track. The experiments
were successful as an evaluation effort: they separated retrieval failures,
scope failures, sufficiency failures, and structured-output failures. They did
not produce a sufficiently safe, useful, or operationally affordable runtime
gate.

## Problem and hypotheses

The project needed to distinguish an absent answer from a retrieved answer that
was not actually sufficient to support a grounded response. The hypotheses
tested were that reranker-derived features, calibrated classifiers, and small
semantic evaluators could provide a safe answer/abstain decision before
generation.

The canonical evaluation identity for the Phase 6 work is the Evaluation
Corpus v2 development/calibration setup: 445 questions, 112 case families,
with development 200, calibration 112, and frozen_test 133. The frozen split
was reserved for a later locked end-to-end evaluation and was never used here.

## Experiments and verified findings

### Retrieval-derived features and calibration (6A, 6B, 6B.1)

Retrieval-derived signals were useful for failure analysis, but not as a
production answerability gate. The development artifact records 150 answerable
questions, 14 retrieval failures, and 95 false abstentions despite gold
evidence being present. Calibration records 83 answerable questions, 12
retrieval failures, and 52 such gold-present false abstentions. The locked
calibration policy therefore remains `INCONCLUSIVE`.

The important distinction is:

> Reranker scores are ranking signals, not calibrated semantic sufficiency.

Zero false answers was achievable only with very low useful coverage. Gold-
present coverage is therefore a required metric; accuracy or false-answer rate
alone is not sufficient.

### Semantic ambiguity and sufficiency (6C–6C.4)

The balanced `qwen3.5:4b` smoke preserved false-answer safety (`0/48`) but
answered only `7/20` gold-present answerable cases and produced substantial
over-clarification. The full-evidence ambiguity boundary was too conservative.
The query-only scope experiment reduced evidence-driven over-clarification,
but genuine ambiguity retention fell from `12/12` to `9/12`. It was a useful
architectural finding, not a runtime promotion candidate.

Ambiguity and evidence insufficiency are separate responsibilities. Multiple
documents, multiple chunks, or a multi-part question do not by themselves
mean that the user is ambiguous.

### Obligation experiments (6C.5, 6C.6)

The combined obligation evaluator had 16/24 first-pass structured success,
14 timeout events, 8 parse failures, approximately 60 seconds p95, and still
answered `0/3` complete multi-document cases. Separating query-only obligation
extraction from support mapping improved extraction reliability to `24/24`
first-pass with no parse or timeout failures. The support-only stage was valid
on only `11/24` calls, with 13 schema/status failures; candidate coverage was
`0/20`, multi-document answers were `0/3`, and candidate p95 was approximately
44 seconds.

This isolates the failure: obligation extraction can be feasible while fixed
obligation-to-evidence support mapping remains unreliable for the local small
model. Complete multi-document evidence was present in the cached authorized
contexts; the semantic gate failed to recognize it reliably. That is not
evidence that multi-document retrieval failed. Whether the actual answer
generator can synthesize that evidence belongs to end-to-end answer-quality
evaluation.

### Model and latency conclusion

`qwen3.5:4b` was the best tested small semantic candidate among the locally
available candidates for safety and structured output. “Best tested” does not
mean production-approved: coverage, over-clarification, support-mapping
reliability, and local inference latency remained unacceptable for a runtime
gate. Model comparison was performed only on the controlled smoke; no claim of
production accuracy is made from that sample.

## Runtime decision

`SEMANTIC_ANSWERABILITY_RUNTIME_PROMOTION = REJECTED`.

The active runtime remains intentionally simple:

```text
Query
  ↓
Hybrid Retrieval
  ↓
Tenant ACL
  ↓
BGE Reranker
  ↓
Top-5 Authorized Context
  ↓
Existing Generation
  ↓
Strict Output / Citation Validation
```

The deterministic no-evidence safety behavior remains in place:

```text
NO_RETRIEVAL_CANDIDATES → safe no-evidence behavior
NO_AUTHORIZED_EVIDENCE  → safe no-evidence behavior
EMPTY_RERANK_RESULT     → safe no-evidence behavior
```

Tenant ACL still precedes reranking, semantic processing, and generation.
Unauthorized evidence is not exposed to downstream components. Prompt-injection
boundaries, buffered strict validation, deterministic citations, and existing
resilience behavior remain unchanged.

The following remain evaluation/shadow/research-only and are not user-facing
enforcement: retrieval-feature classifiers, `ambiguity_v1`, `ambiguity_v2`,
`query_scope_query_only_v1`, `query_scope_compact_v1`, `sufficiency_v1`,
`obligation_sufficiency_v2`, and fixed-obligation support.

Semantic answerability settings remain disabled by default. When explicitly
enabled for shadow observation, they add telemetry only; they do not suppress
generation or change the answer returned to the user.

## What Phase 6 learned

1. Reranker scores are ranking signals, not calibrated answerability.
2. Retrieval failure and gate failure must be measured separately.
3. Gold-present coverage is essential for answerability evaluation.
4. Ambiguity and evidence insufficiency are different failure modes.
5. Multiple documents do not imply user ambiguity.
6. Obligation extraction can be reliable while support mapping is not.
7. Zero false answers is not enough when useful coverage collapses.
8. Model-based safety gates must justify operational latency and complexity.
9. Failure attribution can be more valuable than adding another evaluator.
10. Not promoting an experimental subsystem can be the correct production decision.

## What remains useful

Phase 6A feature extraction, split-safe labels, failure-taxonomy reports,
semantic evaluator schemas, cache-first runners, and all historical artifacts
remain useful for research and future comparison. They must be treated as
versioned evaluation assets, not as active runtime policy.

The frozen split remains untouched and reserved for the final locked retrieval
plus generation configuration. Additional answerability calibration is not
warranted because no semantic runtime policy exists to calibrate.

## Next direction

The recommended next project is end-to-end grounded generation quality
evaluation on the existing retrieval + ACL + reranker + citation-safe path:

```text
authorized retrieved context
  → actual generation
  → grounded answer
  → deterministic citation/output validation
```

That work should include standard, hard, cross-lingual, multi-document,
version-conflict, and injection-bearing slices. It is intentionally not run as
part of this closure.
