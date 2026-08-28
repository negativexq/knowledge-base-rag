# Phase 7.11 Reranker Ablation

The exact historical candidate artifact contained source IDs but not chunk payloads. To preserve the locked candidate identity, the three forensic candidate sets were rebuilt with the unchanged embedding, hybrid retrieval, ACL, and candidate_k=20 configuration. Both rerankers then scored those identical 20-chunk sets.

The first completed scoring pass exposed a fact-GT aggregation bug and was not used for metrics. After correction, the same three candidates were rerun and the corrected outputs below are canonical. The execution record includes both passes and one single-pair model-load/score preflight.

BGE retained the known 14-day supporting chunk outside Top-5 for multi-00-1 and multi-00-3. Qwen3 did not recover either chunk and additionally dropped the fact-bearing regional chunk for multi-03-0. BGE fact-passage recall@5 is 5/7 and all-required-facts-present@5 is 1/3; Qwen3 is 4/7 and 0/3.

Qwen3 is also substantially slower on this local CPU run. The development=200 benchmark was correctly skipped after the forensic regression; no generation was run. No reranker was promoted or wired into runtime.
