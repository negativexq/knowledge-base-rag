# Phase 6B.1 — Answerability failure analysis

Static analysis of existing authorized top-five exports. Runtime behavior, retrieval configuration, and final-policy.json were not changed.

## Failure taxonomy

| Split | Answerable | Retrieval failure | Gate failure with gold | Multi-document partial | Deterministic |
|---|---:|---:|---:|---:|---:|
| Development | 150 | 14 | 95 | 2 | 0 |
| Calibration | 83 | 12 | 52 | 0 | 0 |

Development gold-present coverage: 0.263566.
Calibration gold-present coverage: 0.257143.
Unsafe ANSWER with gold absent: 6 development, 1 calibration.

## Feature stability

Most stable: top2_score, mean_top5_score, score_iqr_top5, mean_top3_score, top3_score, source_mean_score, max_top5_score, source_top1_score.
Most unstable: score_range_top5, std_top5_score, top2_to_mean_top5_ratio, top1_top3_margin, source_score_entropy, top1_top2_margin, max_chunks_from_same_source, top_source_chunk_share.

## Redesigned candidates

- current_compact: development coverage 0.826667, calibration coverage 0.722892, calibration false answers 21/29.
- source_level_compact: development coverage 0.926667, calibration coverage 0.891566, calibration false answers 23/29.
- relative_structural_compact: development coverage 0.846667, calibration coverage 0.843373, calibration false answers 25/29.
- hybrid_compact: development coverage 0.853333, calibration coverage 0.759036, calibration false answers 22/29.

No redesigned candidate is recommended yet. Critical-slice coverage and cross-split stability require another development iteration.
Final diagnosis: RETRIEVAL_FEATURES_INSUFFICIENT.

Corpus fingerprint: 0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7
Dataset fingerprint: 17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f
Frozen test used: NO; generation invoked: NO.
