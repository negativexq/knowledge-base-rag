# Artifacts

This directory keeps compact evidence summaries, reports, metrics, manifests,
and integrity records that are useful for reviewing the project. Raw per-run
retrieval, generation, scoring, and capture outputs are intentionally not
committed: they are reproducible with the scripts and workflows documented in
the repository.

The raw output paths are ignored by Git so local runs can still write them
under `artifacts/` without adding large dumps to future commits. Summary files
referenced by `README.md` or `docs/` remain tracked.
