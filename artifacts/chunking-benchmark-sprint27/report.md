# Sprint 27 — Token-aware chunking benchmark

Decision rule was fixed before running the benchmark: quality must stay within the baseline floor (Recall@5 -0.01, cross-lingual Recall@5 -0.01, MRR -0.02), hard-max violations must be zero, and efficiency is a secondary preference. No weighted score is used.

Dataset: `tests/fixtures/embedding_benchmark_golden_v2.json` · questions: 220 · historical fingerprint: `55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691`
Controls: Qwen3-Embedding-4B@1024 · BM25 sparse · Qdrant RRF · BAAI/bge-reranker-v2-m3 · candidate 20 → top 5 · same corpus/parser/ACL.
Hard-max rule: target + 64 tokens (320, 448, 576, 832) for token-aware candidates; the baseline has no enforced hard max.

## Cross-lingual retrieval

| Config | TR→EN R@5 | EN→TR R@5 | Cross MRR | Cross nDCG@5 |
|---|---:|---:|---:|---:|
| baseline | 1.0000 | 1.0000 | 0.9558 | 0.9672 |
| 384-48 | 1.0000 | 1.0000 | 0.9569 | 0.9681 |
| 256-32 | 1.0000 | 1.0000 | 0.9569 | 0.9681 |
| 512-64 | 1.0000 | 1.0000 | 0.9569 | 0.9681 |
| 768-96 | 1.0000 | 1.0000 | 0.9569 | 0.9681 |

## Chunk/context efficiency

| Config | chunks | avg tokens | p95 context tokens | envelope overhead | storage |
|---|---:|---:|---:|---:|---:|
| baseline | 51 | 68.745 | 412 | 263.603% | 3670016 |
| 384-48 | 51 | 68.745 | 414 | 263.573% | 3702784 |
| 256-32 | 51 | 68.745 | 412 | 263.705% | 3702784 |
| 512-64 | 51 | 68.745 | 412 | 264.403% | 3670016 |
| 768-96 | 51 | 68.745 | 412 | 264.403% | 3670016 |

## Paired bootstrap

Seed: `2701` · iterations: `5000` · 95% CI · deltas are baseline minus candidate.

### baseline_vs_256-32
- recall_at_5: Δ=0.00000, CI [0.00000, 0.00000]
- mrr: Δ=-0.00080, CI [-0.00240, 0.00000]
- ndcg_at_5: Δ=-0.00063, CI [-0.00189, 0.00000]
### baseline_vs_384-48
- recall_at_5: Δ=0.00000, CI [0.00000, 0.00000]
- mrr: Δ=-0.00080, CI [-0.00240, 0.00000]
- ndcg_at_5: Δ=-0.00063, CI [-0.00189, 0.00000]
### baseline_vs_512-64
- recall_at_5: Δ=0.00000, CI [0.00000, 0.00000]
- mrr: Δ=-0.00080, CI [-0.00240, 0.00000]
- ndcg_at_5: Δ=-0.00063, CI [-0.00189, 0.00000]
### baseline_vs_768-96
- recall_at_5: Δ=0.00000, CI [0.00000, 0.00000]
- mrr: Δ=-0.00080, CI [-0.00240, 0.00000]
- ndcg_at_5: Δ=-0.00063, CI [-0.00189, 0.00000]

Production recommendation: **KEEP_CURRENT**

This benchmark does not claim production-scale storage behavior for the tiny four-document fixture corpus. Its measured average chunk is approximately 69 Qwen tokens and its maximum is 100, so none of the 256–768 targets is exercised by this fixture. Qwen tokenizer/model and BGE reranker are served locally; reranker inference remains synchronous in the async retrieval path.

## Controlled reranker timing correction

The original per-config reranker timing table was not causally interpretable:
it varied with runtime/order conditions even though the payloads were reported
as equivalent. Those values are retained only as `historical_first_run` in
`results.json` and are not used for the decision.

A follow-up loaded one `BAAI/bge-reranker-v2-m3` model once on CPU, warmed it
twice, used the same 20 candidate texts and batch size 20, and timed only
`CrossEncoder.predict()`. Five repetitions per config used a fixed seeded
balanced order. Every reconstructed config had the same candidate fingerprint
`4bef6918d9d461d4597220e402c6ce2635780c8cfca7038e1ff537efafb9ceca` and the
same 20 token lengths (1172 total).

| Config | controlled p50 | controlled p95 | mean | stddev |
|---|---:|---:|---:|---:|
| baseline | 2570 ms | 4054 ms | 2782 ms | 767 ms |
| 256-32 | 2237 ms | 2483 ms | 2229 ms | 190 ms |
| 384-48 | 2254 ms | 3631 ms | 2579 ms | 623 ms |
| 512-64 | 2265 ms | 2857 ms | 2374 ms | 313 ms |
| 768-96 | 2354 ms | 5931 ms | 3090 ms | 1630 ms |

The residual spread, including one 768 outlier, is unexplained runtime/order
variance on a shared CPU input, not evidence that chunk target caused reranker
cost. Reranker latency is therefore excluded from the chunking quality
decision. The full controlled artifact is `reranker-latency.json`.

## Generation sanity closure

The real local production chat path was exercised on 26 requests using the
legacy 500/50 chunking, Qwen3-Embedding-4B@1024, BM25, RRF, BGE m3, tenant-a
ACL, `answer_v3`, strict validation, and canonical citations. The sample had
5 each for TR→TR, EN→EN, TR→EN, and EN→TR, 4 not-found controls, and 2
security controls.

| Metric | Result |
|---|---:|
| citation integrity pass rate | 100% (26/26) |
| not-found accuracy | 100% (4/4) |
| strict/security validation pass rate | 100% (26/26) |
| security control pass rate | 100% (2/2) |
| generation success rate | 100% (26/26) |
| answer relevancy judge | not measured |

Both security controls were safely validated and released no unsafe tokens;
neither produced a validator violation requiring a withheld-answer path. The
existing strict violation tests continue to cover the blocked-before-release
branch. Per-request records are in `generation-sanity.json` without raw
questions, prompts, answers, or document text.
