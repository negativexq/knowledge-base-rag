# Validation checks

- Focused Architecture V2 tests: 45 passed.
- Architecture-specific deterministic suite: passed (`1218 passed, 1 skipped,
  6 deselected` in the prior filtered run).
- Full deterministic suite, current run: `1230 passed, 1 skipped, 6
  deselected, 5 warnings`; no current Qdrant errors.
- Prior three Qdrant fixture errors: triaged as environment-dependent and
  non-task-caused; see `08-fixture-triage/qdrant-fixture-triage.md`.
- Targeted Ruff: passed.
- Targeted compile/import: passed.
- `git diff --check`: passed.
- Secret scan over the task artifact root: zero hits.
- Ollama E2E: not run.
- OpenAI/Ollama/embedding/BGE/retrieval calls: zero.
