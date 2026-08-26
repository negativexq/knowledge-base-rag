# Sprint 27 — Token-aware chunking

## Existing behavior

The production baseline remains the legacy whitespace-word window: target
500, overlap 50, sentence-end extension, Markdown heading/block grouping, and
PDF page boundaries. Its “token” count is an approximation and is not a model
tokenizer count. Markdown citations use heading paths and occurrence numbers;
PDF citations retain page and paragraph metadata.

## Tokenizer-aware design

Candidates use the tokenizer compatible with the production embedding model,
`Qwen/Qwen3-Embedding-4B`, revision `main`. The model card documents the
tokenizer loading contract and multilingual scope: <https://huggingface.co/Qwen/Qwen3-Embedding-4B>.

`ChunkingConfig` is the single source of truth for target, overlap, hard max,
tokenizer, revision, and boundary strategy. The token-aware chunker counts
real tokenizer offsets, prefers sentence/paragraph boundaries, retains
Markdown heading metadata, and starts a new PDF chunk at every page. The
pre-committed hard-max rule is `target + 64`: 320, 448, 576, and 832 tokens.
The hard max is never exceeded in the benchmarked candidates.

The full pipeline fingerprint includes all chunking fields. Changing target,
overlap, tokenizer revision, hard max, boundary strategy, or parser/index schema
makes an unchanged document stale and requires re-indexing.

## Benchmark controls

The primary dataset is the existing 220-question multilingual set with its
historical fingerprint unchanged. All configs use Qwen3-Embedding-4B@1024,
BM25 sparse retrieval, Qdrant RRF, BAAI/bge-reranker-v2-m3, candidate k=20,
output n=5, the same corpus, parser, tenant ACL, and query set. Each config
has an isolated Qdrant collection.

The fixed configurations were:

| Config | Target | Overlap | Hard max |
|---|---:|---:|---:|
| baseline | legacy 500-word window | 50-word approximation | not enforced |
| 256-32 | 256 tokens | 32 tokens | 320 |
| 384-48 | 384 tokens | 48 tokens | 448 |
| 512-64 | 512 tokens | 64 tokens | 576 |
| 768-96 | 768 tokens | 96 tokens | 832 |

## Result and decision

The four-document benchmark corpus is smaller than production-scale content.
Its average chunk is approximately 69 Qwen tokens and its maximum is 100, so
none of the 256–768 token targets is exercised by this fixture. All
token-aware candidates produced the same 51 chunk text/location payloads;
their canonical payload signature was
`cb881602564e0692c43acc499aa824dbdb4c2eeaa5c6d5fb4b403534e04b038e`. The
larger target values therefore did not create a different chunk boundary on
this corpus. Their retrieval metrics are consequently equivalent, and the
benchmark reuses the measured reranker result only after that payload identity
is verified.

The measured retrieval result was Recall@5 1.0000 in all four language cells
for baseline and every candidate. Overall MRR was 0.9635 for baseline and
0.9643 for the token-aware payload. Overall nDCG@5 was 0.9729 and 0.9736,
respectively. Candidate average top-five context was 351.37–351.54 real Qwen
tokens versus 351.33 for baseline; p95 was 412–414 versus baseline 412.
Chunk count was 51 in every configuration and no candidate exceeded its hard
max. Exact evidence spans are absent from the golden set, so citation
precision/evidence density is **not measured**, not inferred.

Because no token-aware candidate Pareto-dominates the current baseline on
quality plus context, chunk count, or storage, the pre-committed decision rule
selects **KEEP_CURRENT**. Production remains on the legacy baseline; no
destructive migration or active-index switch is performed. The token-aware
implementation and isolated collections remain available for a larger corpus
benchmark.

## Context envelope and operational cost

The real tokenizer measurement for the untrusted-context envelope is roughly
263.7% overhead on the token-aware payload in this fixture (the baseline is
roughly 263.6%). This replaces the earlier whitespace estimate; the security
envelope is not removed or weakened.

The first per-config reranker timing table was not causally interpretable: it
varied with runtime/order conditions even though the payloads were reported as
equivalent. A controlled follow-up loaded one BGE m3 model once on CPU, warmed
it twice, timed only `CrossEncoder.predict()` over the same 20 candidate texts,
and ran five repetitions/config in a fixed seeded balanced order. All configs
had the same input fingerprint
`4bef6918d9d461d4597220e402c6ce2635780c8cfca7038e1ff537efafb9ceca`, with 20
candidate texts and 1172 total Qwen tokens. Corrected p50/p95 values were:

| Config | p50 / p95 |
|---|---:|
| baseline | 2570 / 4054 ms |
| 256-32 | 2237 / 2483 ms |
| 384-48 | 2254 / 3631 ms |
| 512-64 | 2265 / 2857 ms |
| 768-96 | 2354 / 5931 ms |

The residual spread, including one 768 outlier, is unexplained runtime/order
variance, not a demonstrated chunking-cost causal chain. These timings are
not used to select a chunk config. Memory/VRAM was not measured; reranker
inference remains synchronous in the async retrieval path.

Storage uses Qdrant's block-based `du -sk` measurement. The fixture is too
small to predict production-scale storage or indexing behavior. Boundary
quality is measured where metadata permits: token-aware candidates had zero
sentence-middle splits, full heading preservation, and zero page crossing;
the legacy baseline does not carry equivalent structural flags.

## Known limitations

- The corpus has only four documents and many candidate sizes are therefore
  structurally equivalent: average chunk size is ~69 and maximum is 100 Qwen
  tokens. Revisit the decision when substantially longer documents or sections
  exercise the 256–768 token boundaries.
- The dataset has expected source locations but no exact evidence spans;
  citation precision proxy and evidence density are not measured.
- Reranker inference is synchronous in the async retrieval path; Sprint 27 does
  not refactor serving or event-loop scheduling.
- The benchmark measures retrieval/candidate and context efficiency, not
  claim-level semantic grounding or answer relevancy.
- No production migration was performed because KEEP_CURRENT won the
  pre-committed Pareto decision rule.
- A 26-request real local generation sanity subset was run after the benchmark,
  using legacy 500/50 chunking, answer_v3, strict validation, canonical
  citations, and tenant ACL. Its result is
  `artifacts/chunking-benchmark-sprint27/generation-sanity.json`.

The generation sanity result was 100% citation integrity (26/26), 100%
not-found accuracy (4/4), 100% strict/security validation (26/26), 100%
generation success (26/26), and 100% security-control success (2/2).
Answer relevancy was not measured because no reliable judge was used. The two
security controls were safely validated with no unsafe token release; neither
triggered a violation requiring the withheld-answer branch. That branch is
covered by the existing strict output-policy tests.
