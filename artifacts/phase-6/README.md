# Phase 6 artifact index

Phase 6 artifacts preserve the answerability research inputs, measurements,
and reproducible runners. They are not runtime policy. The final engineering
decision is [Phase 6 Answerability Decision](../../docs/phase-6-answerability-decision.md).

| Artifact set | Purpose |
| --- | --- |
| [answerability-features](answerability-features/) | Deterministic post-ACL/post-rerank shadow features |
| [calibration](calibration/) | Development-fit and calibration confirmation; final policy is `INCONCLUSIVE` |
| [failure-analysis](failure-analysis/) | Retrieval failure vs gate failure and structural feature analysis |
| [semantic-model-smoke](semantic-model-smoke/) | Cache-first local evaluator model comparison |
| [semantic-balanced-smoke](semantic-balanced-smoke/) | Balanced `qwen3.5:4b` semantic validation |
| [ambiguity-v2](ambiguity-v2/) | Ambiguity prompt redesign comparison |
| [query-scope-boundary](query-scope-boundary/) | Query-only vs compact-scope boundary experiment |
| [obligation-sufficiency](obligation-sufficiency/) | Combined obligation decomposition/support experiment |
| [fixed-obligation-support](fixed-obligation-support/) | Separated extraction and fixed support-mapping experiment |

All listed artifacts are historical or experimental evidence. None enables a
user-facing abstention or clarification gate. The frozen test split was not
used for this research.
