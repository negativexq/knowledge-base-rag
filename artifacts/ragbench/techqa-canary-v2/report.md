# TechQA HOLDOUT50 over the production path

18 frozen holdout questions over the canonical 769-document TechQA corpus, production ingestion and chat path, tenant `bench-techqa`, model `gpt-6-luna`, reranker 40/14, whole-corpus retrieval. Flags: DERIVED_ANSWERS_ENABLED=True, OPERAND_RESOLVER_ENABLED=True, VISUAL_ANSWERS_ENABLED=True.

- Relevant document in the reranked top-14: 100% (16/16); in the 40 candidates: 100% (16/16) (questions RAGBench marks with a relevant document)
- Answers citing a relevant document: 82% (9/11)
- Response kinds: answered 11, model_abstained 5, validator_blocked 2
- ACL leaks (same questions as `tenant-a`): 0
- Ingestion: existing chunks in 0 s; questions: median 31.3 s each.

Semantic labels follow the canonical blind-review rubric against RAGBench's reference response; they were assigned by one reviewer after the run (not yet graded).
