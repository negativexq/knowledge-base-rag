# TechQA HOLDOUT50 over the production path

50 frozen holdout questions over the canonical 769-document TechQA corpus, production ingestion and chat path, tenant `bench-techqa`, model `gpt-6-luna`, reranker 40/14, whole-corpus retrieval. Flags: DERIVED_ANSWERS_ENABLED=True, OPERAND_RESOLVER_ENABLED=True, VISUAL_ANSWERS_ENABLED=True.

| Outcome | Result |
| --- | ---: |
| Useful (correct + partial) | 52% (26/50) |
| Correct | 16 |
| Partial | 10 |
| Materially incorrect | 2% (1) |
| Unavailable | 46% (23) |

- Relevant document in the reranked top-14: 90% (37/41); in the 40 candidates: 100% (41/41) (questions RAGBench marks with a relevant document)
- Answers citing a relevant document: 85% (22/26)
- Response kinds: answered 29, model_abstained 14, validator_blocked 7
- ACL leaks (same questions as `tenant-a`): 0
- Ingestion: existing chunks in 0 s; questions: median 27.9 s each.

Semantic labels follow the canonical blind-review rubric against RAGBench's reference response; they were assigned by one reviewer after the run (semantic-scores.csv).
