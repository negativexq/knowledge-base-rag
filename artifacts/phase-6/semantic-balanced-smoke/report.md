# Phase 6C.2 balanced semantic evaluator smoke

- Model: `qwen3.5:4b`
- Queries: `48`
- Behavioral targets: `{"SHOULD_ABSTAIN": 16, "SHOULD_ANSWER": 20, "SHOULD_CLARIFY": 12}`
- False answers: `0/48`
- False clarifications on SHOULD_ANSWER: `0.550`
- Gold-present coverage: `7/20`
- Retrieval calls during cache build: `48`
- Evaluator-only retrieval/embedding/reranker/generation calls: `0`

This is a balanced validation smoke, not a production accuracy estimate. Prompts remain ambiguity_v1/sufficiency_v1; runtime enforcement remains off.
