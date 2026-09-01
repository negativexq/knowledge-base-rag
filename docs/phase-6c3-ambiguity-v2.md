# Phase 6C.3 — Ambiguity v2 scope/authority comparison

Phase 6C.3 compares a narrower ambiguity definition against the existing
`ambiguity_v1` prompt. The v2 evaluator marks a query `AMBIGUOUS` only when an
additional user-supplied constraint is required to select one grounded
interpretation. Multiple retrieved documents, multi-document questions,
version history, or resolvable authority conflicts are not ambiguity by
themselves. Missing evidence remains a sufficiency concern.

The comparison uses the immutable 48-query authorized cache from the balanced
Phase 6C.2 smoke. It does not rerun retrieval, embeddings, ACL filtering, or
reranking. `sufficiency_v1`, the qwen3.5:4b model, and the structured schemas
remain fixed. Retrieved text is still untrusted evidence and cannot provide
instructions to the evaluator.

Run the evaluator-only comparison with:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.experiments.compare_ambiguity_versions \
  --cache-dir artifacts/phase-6/semantic-balanced-smoke \
  --output-dir artifacts/phase-6/ambiguity-v2 \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --model qwen3.5:4b
```

The v1 prompt remains the runtime/default prompt. The command produces a
comparison artifact only; it does not enable runtime enforcement, change
generation behavior, or run calibration/frozen-test evaluation. Use
`--report-only` to rebuild derived comparison files from an existing v2
result file without calling Ollama.

The observed smoke result is not a production accuracy claim. In the current
run v2 preserved all 12 genuine ambiguous cases and zero false answers, but
reduced false clarifications only once at the `SHOULD_ANSWER` action level;
the broader false-clarify count increased from 19 to 20. Therefore v2 is not
promoted by this comparison and remains an explicit experimental prompt.
