# Phase 6A — Answerability shadow features

Phase 6A records deterministic retrieval signals after the existing security
boundary:

```text
hybrid retrieval → tenant ACL → BGE rerank → top 5 → shadow features → generation
```

The layer is observational only. It does not select a threshold, calibrate a
probability, abstain, or alter the answer/error behavior. BGE values are raw
reranker scores; they are not confidence percentages.

## Reference configuration

Offline export uses `Settings.benchmark_reference()` and therefore keeps the
Phase 6 reference `candidate_k=20`, Qwen3-Embedding-4B at 1024 dimensions,
BM25 + dense + RRF, BAAI/bge-reranker-v2-m3, and `top_n=5`. `DEV_FAST` remains
the interactive profile with `candidate_k=15`; it is not used to create the
Phase 6 reference observations.

The additive feature schema also includes finite structural signals derived
from the authorized top-five list: relative score decay/ratios, score range
and IQR, unique/duplicate source ratios, source chunk concentration, stable
rank/score entropy, and source-level top scores/margin. These are descriptive
signals only; they do not make an answerability decision.

## Export

The development split is the default and the export contains no query text or
document content:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.calibration.export_answerability_features \
  --split development \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --output artifacts/phase-6/answerability-features/development.jsonl
```

The command validates the collection against the canonical corpus fingerprint
before loading models. `--allow-calibration` is required for calibration and
`--allow-frozen-test` is required for frozen test; frozen test is not part of
Phase 6A.

## Signals and limitations

Features include pre-ACL/authorized candidate and reranked counts, raw top-score and
margin signals, top-k score aggregates, source/document diversity, duplicate
source chunk count, and score concentration. The current single Qdrant RRF
query exposes only the fused result. Dense rank, sparse rank, fused rank,
dense/sparse agreement, and fused/rerank agreement are therefore nullable
rather than estimated. Retrieval makes one bounded raw candidate query,
records its integer count, then applies the server-owned tenant ACL before
reranking. No second query is made, and unauthorized source IDs/content
cannot enter the observation.

When the raw count is positive and authorized candidates are zero, the
deterministic reason is `NO_AUTHORIZED_EVIDENCE`; when both are zero it is
`NO_RETRIEVAL_CANDIDATES`.

## Descriptive analysis

`development-summary.json` and `development-distributions.csv` provide counts
and descriptive percentiles by answerability label and category. They do not
contain threshold recommendations or calibration output. Phase 6B may use
development/calibration observations later; it must not tune on frozen test.
