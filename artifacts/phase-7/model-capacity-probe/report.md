# Phase 7.3 qwen3.5 capacity probe

Status: **CAPACITY_PROBE_INCONCLUSIVE**.

The locked Phase 7 cache was validated and the deterministic 12-query selection was written. Existing qwen3.5:4b outputs were reused; no 4B generation was rerun. The exact qwen3.5:9b model was locally available, but its first generation call did not complete before the operator stopped the probe. Therefore no 9B quality or latency claim is made.

- Cache: `0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7` / `17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f`
- Retrieval calls: `0`; embedding/reranker/semantic evaluator calls: `0`
- 4B generation calls: `0`; 9B completed generation calls: `0`
- Prompt: `v3`; think: `false`; retrieval cache reused: `true`
- Selection: `{'multi_document': 3, 'hard_answerable': 3, 'cross_lingual': 2, 'version_conflict': 2, 'standard_answerable': 1, 'injection_bearing': 1}`
- Full 36/development 200/calibration/frozen test: not run

The probe remains safe to resume with the same selection and cache after a bounded-generation/latency decision. Runtime defaults remain unchanged.
