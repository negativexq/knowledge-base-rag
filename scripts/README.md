# Scripts index

Run a module from the repository root with `PYTHONPATH=. .venv/bin/python -m
scripts.<group>.<module>`.

| Group | Purpose |
| --- | --- |
| `benchmarks/` | Retrieval, embedding, reranker, chunking, generation, and RAGBench measurements. |
| `experiments/` | Pipeline, TechQA, model-capacity, ablation, and provider experiments. |
| `audits/` | Offline diagnostics, integrity checks, forensic replays, and report finalization. |
| `calibration/` | Answerability features plus validator calibration and independent validation. |
| `operations/` | Corpus/artifact builds, freeze/prepare steps, indexing, migration, rendering, and service records. |

Canonical/latest entry points:

- Validator calibration: `calibration/run_validator_calibration_debug_v3.py` is
  the latest line; v2 and v1 remain as frozen reproduction oracles.
- Independent validator validation: `calibration/run_validator_v3_independent_validation_v1.py`
  supersedes the v2 independent validation runner.
- TechQA reranker holdout: `experiments/run_techqa_reranker_corrected_holdout_execution_v2.py`
  is the corrected/latest holdout runner; earlier decision, one-shot, and
  removal-debug runners are historical experiments.
- Phase 7 context builder: `benchmarks/benchmark_context_builder_full.py` is
  the full validation runner; `benchmark_context_builder.py` is the probe.
- Canonical RAGBench runs: `benchmarks/run_ragbench_techqa_canonical.py` and
  `benchmarks/run_ragbench_emanual_canonical.py` are the canonical runners.

Older versions stay available because they represent distinct, reproducible
experiments rather than duplicates.
