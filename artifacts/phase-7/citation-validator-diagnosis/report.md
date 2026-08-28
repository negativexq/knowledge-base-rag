# Phase 7.3 Citation / Validator Diagnosis

Offline analysis only. No inference, retrieval, reranker, embedding, semantic evaluator, or external judge call was made.

## Identity
- Generator: qwen3.5:4b; prompt: v3; think: False.
- Corpus: 0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7; dataset: 17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f.
- Retrieval cache identity validated: candidate_k 20, top_n 5, 36 records.

## Validator and observability
- Validator rejections: 7/36; codes: {'CITATION_SUPPRESSION': 4, 'UNAUTHORIZED_CITATION_ID': 3}.
- Historical raw candidate observable: 29/36; rejected content unassessable: 7/7.
- Strict rejection remains user-visible suppression; opt-in capture does not alter delivery.

## Citation diagnosis
- Citation-bearing records: 28/36; occurrences: 77.
- Invalid identity occurrences: 4; duplicate excess occurrences: 12.
- Definite citation support: 26 occurrences; review-required: 17.
- Source-level required-fact citation completeness: 17/22; claim-level support remains manual.
- Source-alignment proxy: 16 occurrences in 10 records.

## Critical slices
- Multi-document: Phase 6 semantic gate answer was 0/3; all required evidence was present, but generation did not reliably synthesize and cite complete answers.
- Authority/version summary: {'current_rule_selected': 1, 'stale_or_noncanonical_mixed': 1}.
- Injection control: INJECTION_CONTROL_SAFE; raw capture remains evaluation-only.
- Cross-lingual: Cross-lingual failures are mixed: valid citations can accompany content/authority issues, while one EN-to-TR case is unobservable after invalid citation rejection.

## Decision
- OBSERVABILITY_READY_CONTEXT_BUILDER_NEXT.
- Validator and citation identity failures are separable, raw/validated/user-visible boundaries are instrumentable, and remaining source-alignment/context issues can be tested without weakening strict validation.
- Context Builder A/B is safe to begin as a separate measurement experiment; strict citation validation, ACL, model, prompt, and retrieval remain unchanged.
