# Phase 7.1 Grounded Generation Failure Analysis

This is an offline analysis of the existing 36-query Phase 7 smoke. No inference, retrieval, embedding, reranker, or judge calls were made.

## Identity
- Generator: `qwen3.5:4b`, prompt `v3`, think `False`
- Corpus: `0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7`; dataset: `17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f`
- Collection: `kb_eval_phase55_0175aa4a2f9b`; candidate_k `20`; top_n `5`
- Index: `20 sources / 186 chunks / 1024 dimensions`

## Reviewed correctness range
- Deterministic baseline: `3/22`
- Definitely correct after review: `10/22`
- Correct-or-plausibly-correct upper range: `20/22`; lower bound is `10/22`
- Correct but incomplete: `2/22`; partially correct: `3/22`; materially incorrect: `2/22`; cannot determine: `5/22`
- Deterministic evaluator false negatives: `7/22`

## Primary causes
- `DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE`: 7
- `CITATION_FORMAT_FAILURE`: 5
- `CROSS_LINGUAL_REASONING_FAILURE`: 2
- `EVIDENCE_SYNTHESIS_FAILURE`: 2
- `MULTIPART_COMPLETENESS_FAILURE`: 2
- `AUTHORITY_RESOLUTION_FAILURE`: 1

## Key findings
- Gold evidence was present for all 22 primary records; retrieval failure is not the explanation for these failures.
- Gold was rank 1 for 6 source occurrences and rank 2–5 for the remainder; top-1 was non-gold in 16/22 records.
- Duplicate source chunks occurred in 18/22 records (28 duplicate positions).
- The v3 prompt explicitly separates untrusted evidence, canonical citations, and unsupported answers; no prompt edit was made.
- Citation mechanics are a separate blocker: strict validation rejected 7 outputs, while citation support was only 7/25 in the original smoke scoring.
- Multi-document evidence was available, but two answers omitted/blurred a required component and one was validator-rejected; this is synthesis/contract evidence, not retrieval recall failure.
- Injection control remained safe (0 control failures); the two injection records are normal generation-quality failures, not proven prompt-injection control failures.

## Next experiment
- Recommendation: **EVALUATOR_REFINEMENT_FIRST**
- Seven clear paraphrase/language matcher misses and five validator-rejected answers make 3/22 an unreliable lower-bound for generator quality; establish a reviewed deterministic scorer before changing runtime generation.
- Keep prompt v3, qwen3.5:4b, retrieval, citation validator, and semantic gate state unchanged until the scorer/validator evidence is clarified.
