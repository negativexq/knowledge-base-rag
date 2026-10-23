# Reranker batch size

23 October 2026. Offline and free: no model API calls, no re-ingest.

## Why

In 27 traced research runs, rerank took 21% of the wall time. Per call it ranged from 2.3 s to 10 s. sentence-transformers sorts the (query, chunk) pairs by length, then pads each batch to its longest pair. Production passed no `batch_size`, so the library default of 32 put all 15 candidates in one batch. One long chunk (for example 1,476 tokens next to a median of about 590) made every pair cost as much as the longest one. Across the recorded searches, 44% of the tokens computed were padding. Rerank time tracked the padded size (correlation 0.84) much more closely than the real text length (0.57).

## Method

- **Inputs:** the reranker inputs recorded in saved MMLongBench traces. That is 120 questions, one search each, 15 candidates per search, with the exact chunk texts.
- **Scoring:** `BAAI/bge-reranker-v2-m3` on MPS (Apple M2, 16 GB), sentence-transformers 5.6.1, the same `CrossEncoder.predict` call as production, with only `batch_size` changed.
- **Run order:** one process, warmed up for every batch size first. The order of the sizes rotated per search to spread drift, with an MPS sync around each timing.
- **Scores:** each search's 15 scores were compared with the batch-32 scores.

## Result

| Batch size | Mean s | Median s | p90 s | Total s (120 searches) | Identical full ranking | Max score difference |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 (old default) | 10.05 | 8.27 | 17.51 | 1,205.9 | — | — |
| 8 | 7.21 | 6.79 | 11.04 | 865.6 | 120 / 120 | 1.2e-7 |
| 4 | 6.04 | 5.95 | 9.01 | 725.1 | 120 / 120 | 1.2e-7 |
| 2 | 5.07 | 5.23 | 7.33 | 608.2 | 120 / 120 | 1.2e-7 |

Batch 2 halves the mean rerank time, and the slowest tail improves most (p90 17.5 s → 7.3 s). All 15 candidates keep exactly the same order in every search. The score differences are float rounding. Batch 2 beat batch 4 on 112 of 120 searches. It was more than 0.3 s slower on only 3, by at most 0.62 s, and up to 10.6 s faster.

The absolute times here are higher than the rerank times inside the traced runs (mean 5.5 s), so read the result as a ratio. Batch size 1 was not measured.

## Change

`RERANKER_BATCH_SIZE` now defaults to 2. It was already a setting, so other hardware can retune it; a CPU or a CUDA GPU may prefer a different value. `report.json` has the summary and the per-search timings.
