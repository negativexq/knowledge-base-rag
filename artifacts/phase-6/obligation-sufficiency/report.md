# Phase 6C.5 obligation-based evidence sufficiency

The exact 48-query Phase 6C.4 cache and the existing
`query_scope_query_only_v1` decisions were reused. Retrieval, embeddings,
reranking, and generation were not called. Only the sufficiency evaluator
changed: `sufficiency_v1` versus `obligation_sufficiency_v2`.

| Metric | sufficiency_v1 | obligation v2 |
|---|---:|---:|
| Precision | 1.000 | 0.750 |
| Recall | 0.538 | 0.600 |
| F1 | 0.700 | 0.667 |
| False sufficient | 0 | 1 |
| False insufficient | 6 | 2 |
| End-to-end gold-present coverage | 7/20 | 3/20 |

The final v2 decision is deterministically aggregated from obligation statuses:
all `SUPPORTED` means `SUFFICIENT`; any `UNSUPPORTED` means `INSUFFICIENT`.
The model is not allowed to turn partial evidence into a sufficient result.
Obligation descriptions are limited to the user request and no more than six
obligations. Supporting chunk IDs are validated against the authorized top-k.

Complete multi-document records and all v1 false-insufficient transitions are
listed in the accompanying JSON artifacts. Runtime defaults and enforcement
remain unchanged.
