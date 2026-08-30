# TECHQA_RERANKER_REMOVAL_DEBUG_V1

This is a DEBUG50 paired challenger with no promotion authority. Terra was not
used and semantic scorecard fields are blank. HOLDOUT50 was not inspected or
executed.

## Frozen protocol

- ON: persisted RRF Top20 → persisted BGE Top5 → SectionAware @2400 → V4 policy
- OFF: persisted RRF Top20 → RRF Top5 → SectionAware @2400 → V4 policy
- Retrieval, embeddings, BGE inference and Terra calls: `0`.
- Official Luna calls: `100` (`50` per arm); technical preflight calls: `2`.
- Config diff is limited to `ranking_source` and `reranker_enabled`.

## Evidence-only comparison (annotated38)

- ON: ANY `36/38`, ALL `29/38`, mean recall `87.95%`.
- OFF: ANY `37/38`, ALL `32/38`, mean recall `92.05%`.
- Evidence verdict: `OFF_EVIDENCE_BETTER`.
- State transitions: `{'ALL_TO_ALL': 27, 'PARTIAL_TO_ALL': 4, 'PARTIAL_TO_PARTIAL': 3, 'NONE_TO_NONE': 13, 'ALL_TO_PARTIAL': 2, 'NONE_TO_ALL': 1}`.
- BGE-harmed downgrades: `['techqa_DEV_Q043#row-0015', 'techqa_DEV_Q168#row-0149']`.
- OFF-helped upgrades: `['techqa_DEV_Q015#row-0065', 'techqa_DEV_Q019#row-0089', 'techqa_DEV_Q063#row-0083', 'techqa_DEV_Q066#row-0086', 'techqa_DEV_Q069#row-0073']`.

## Generation and safety

- ON visible `30/50`; OFF visible `38/50`.
- ON/OFF application contracts: `50/50` / `50/50`.
- Unknown, cross-request, hidden and unauthorized IDs accepted: `0 / 0 / 0 / 0`.
- Critical-value rejects: `14` ON, `17` OFF.

Semantic judgment remains pending human review in `manual-scorecard.csv`; no
semantic verdict was assigned automatically. Historical BGE latency (~64.34
seconds/query) is not a new measurement. The candidate status is
`RERANKER_OFF_READY_FOR_HUMAN_REVIEW`; production removal is not authorized.
