# Phase 6B — Answerability calibration

Status: **INCONCLUSIVE**

Status rationale: Zero answerable coverage in critical slices: multi_document, injection_bearing.

## Policy contract

- Binary target: `answerable → ANSWER`; `unanswerable` and `ambiguous` → `ABSTAIN`.
- Deterministic safety reasons override any statistical candidate: `NO_RETRIEVAL_CANDIDATES, NO_AUTHORIZED_EVIDENCE, EMPTY_RERANK_RESULT`.
- Fit and threshold selection: `development`; confirmation: `calibration`.
- Frozen test used: **NO**. Runtime gate changed: **NO**.
- BGE scores remain raw ranking signals, not probabilities.
- No post-hoc Platt or isotonic calibration was used; the logistic output is
  evaluated as a model probability, while single-feature scores remain raw.
- Unavailable across both exports and therefore excluded: `pre_acl_candidate_count, top1_fused_rank, top1_dense_rank, top1_sparse_rank, dense_sparse_agreement, fused_rerank_agreement`.

## Selected candidate

- Method: `logistic_authorized_candidate_count_reranked_count_top1_score_top2_score_top3_score_top1_top2_margin_top1_top3_margin_mean_top3_score_mean_top5_score_min_top5_score_max_top5_score_std_top5_score_distinct_source_count_top5_distinct_document_count_top5_duplicate_source_chunk_count_top5_source_score_concentration`
- Features: `authorized_candidate_count, reranked_count, top1_score, top2_score, top3_score, top1_top2_margin, top1_top3_margin, mean_top3_score, mean_top5_score, min_top5_score, max_top5_score, std_top5_score, distinct_source_count_top5, distinct_document_count_top5, duplicate_source_chunk_count_top5, source_score_concentration`
- Locked threshold: `0.0159425355925`
- Model serialization: `model.json` (portable coefficients/scaler when applicable)

| Metric | Result |
|---|---:|---:|
| False answers | 0/50 (0/29 calibration) |
| False-answer rate | 0.000000 / 0.000000 calibration |
| False abstentions | 111/150 (64/83 calibration) |
| Answerable coverage | 0.260000 / 0.228916 calibration |
| AUROC | 0.896667 / 0.683008 calibration |
| AUPRC | 0.780812 / 0.384516 calibration |
| Family answerable coverage | 0.284188 / 0.353175 calibration |

## Leakage and reproducibility

Excluded from model input: `expected_source_ids, required_source_ids, answerability_label, category, case_family, query_id, split, tenant, query_language, evidence_language, language_pair`.

Corpus fingerprint: `0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7`  
Dataset fingerprint: `17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f`  
Collection: `kb_eval_phase55_0175aa4a2f9b`  
Reference candidate_k/top_n:
`20/5`

The policy artifact is evidence only. It is not wired into chat generation.

The selected operating point is deliberately safety-first. Its answerable
coverage is reported without an arbitrary acceptance threshold; the policy
remains **INCONCLUSIVE** when a critical slice has zero answerable coverage.
