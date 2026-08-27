# Phase 6B — Answerability calibration

Phase 6B evaluates a small, interpretable answerability policy without wiring
it into chat. The statistical target is binary for safety analysis:

- `answerable` → `ANSWER`
- `unanswerable` and `ambiguous` → `ABSTAIN`

The original three labels remain in every report. The deterministic safety
reasons `NO_RETRIEVAL_CANDIDATES`, `NO_AUTHORIZED_EVIDENCE`, and
`EMPTY_RERANK_RESULT` always map to `ABSTAIN` and override statistical
predictions. No threshold or calibrated probability is exposed at runtime by
this phase.

## Data and fitting policy

The reference retrieval configuration is fixed at candidate k=20, top-n=5,
Qwen3-Embedding-4B at 1024 dimensions, BM25+dense+RRF, and BAAI/bge-reranker-
v2-m3. Development is the only split used to fit logistic candidates and
select thresholds. Calibration is read only for confirmation. Frozen test is
not loaded by the calibration script.

Model inputs are retrieval-derived features only. Dataset labels, source IDs,
categories, case families, tenant and language metadata are excluded from the
feature matrix and retained only for supervision, slicing, and audit output.
Raw BGE scores are ranking signals, not probabilities. Brier and ECE are
reported only for the logistic model's probability output; they are not
computed for raw score baselines. No Platt or isotonic post-hoc calibration is
used.

## Reproduction

First export the independent calibration features with the Phase 6A exporter:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.export_answerability_features \
  --split calibration --allow-calibration \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --output artifacts/phase-6/answerability-features/calibration.jsonl
```

Then run the deterministic development-fit/calibration-confirmation pass:

```bash
PYTHONPATH=. .venv/bin/python scripts/calibrate_answerability.py
```

The script reads the committed feature exports and writes derived evidence to
`artifacts/phase-6/calibration/`: distributions, threshold curves, method and
ablation comparisons, a portable logistic model description, slice metrics,
and `final-policy.json`. It does not call Ollama, generation, Qdrant
benchmarking, or frozen-test evaluation.

## Current evidence

The current safety-first development operating point has zero false answers
on both development and calibration, but only 26.0% and 22.9% answerable
coverage respectively. Calibration also has zero answerable coverage in the
multi-document and injection-bearing slices. Therefore the current
`final-policy.json` status is `INCONCLUSIVE`; it is evidence for Phase 6C,
not a runtime promotion.

The next phase must review the coverage/safety trade-off and critical slices
before connecting any policy to generation. Frozen test remains reserved for
that later, locked final evaluation.

Phase 6B.1 failure analysis is available through:

```bash
PYTHONPATH=. .venv/bin/python scripts/analyze_answerability_failures.py
```

It separates retrieval failures from false abstentions where all required
sources are already in the authorized top five, and evaluates additive
source-level/relative features without re-running retrieval. Its current
result is `RETRIEVAL_FEATURES_INSUFFICIENT` for calibration: redesigned
features improve coverage but introduce unacceptable false-answer rates.
