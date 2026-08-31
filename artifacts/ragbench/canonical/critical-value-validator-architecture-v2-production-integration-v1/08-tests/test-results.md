# Test results

Focused integration, selector, shadow, validator, and forensic tests: **47
passed**.

Full deterministic suite (`pytest -m "not ollama_e2e"`): **1241 passed, 1
skipped, 6 deselected**. The skip is the pre-existing Notion E2E guard for a
missing `NOTION_API_KEY`; Ollama E2E was not run. No task-caused regression was
observed.

Ruff passed for the application and test tree. Python compilation passed.
`git diff --check` passed. A focused gitleaks scan over the integration source,
tests, config, and rollout documentation found no leaks. A repository-wide
scan was not used as the gate because the existing historical artifact tree is
large and unbounded for this local review.

The focused suite includes explicit tests for the three selectors, default
baseline, invalid-selector failure, authoritative V2 fail-closed behavior,
baseline/V3 shadow isolation, shadow errors, bounded OTel redaction, and
forensic metadata handling.
