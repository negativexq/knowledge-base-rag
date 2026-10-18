# TechQA HOLDOUT50 over the production path

2 frozen holdout questions over the canonical 769-document TechQA corpus, production ingestion and chat path, tenant `bench-techqa`, model `gpt-6-luna`, reranker 40/14, whole-corpus retrieval. Flags: AGENTIC_RAG_ENABLED=True, AGENTIC_MODE=escalate, DERIVED_ANSWERS_ENABLED=True, OPERAND_RESOLVER_ENABLED=True, VISUAL_ANSWERS_ENABLED=True.

- Relevant document in the reranked top-14: 100% (2/2); in the 40 candidates: 100% (2/2) (questions RAGBench marks with a relevant document)
- Answers citing a relevant document: 100% (1/1)
- Response kinds: answered 1, model_abstained 1
- ACL leaks (same questions as `tenant-a`): 0
- Ingestion: existing chunks in 0 s; questions: median 128.3 s each.

Semantic labels follow the canonical blind-review rubric against RAGBench's reference response; they were assigned by one reviewer after the run (not yet graded).
