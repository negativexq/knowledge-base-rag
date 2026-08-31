# Readiness V2 test results

- Focused Architecture V2 integration/shadow/telemetry/forensic/failure tests:
  `51 passed`.
- Full deterministic suite: `1245 passed, 1 skipped, 6 deselected`.
- The one skip is the pre-existing Notion integration requirement for
  `NOTION_API_KEY`; Ollama E2E was not run as a test marker suite.
- No task-caused deterministic regression was observed.
- Ruff: PASS.
- Compile/import: PASS.
- `git diff --check`: PASS.
- Secret scan: PASS.

The six primary cases were executed once through direct Chrome CDP. Each
validator-capable request produced HTTP 200, UI completion, and a corresponding
Jaeger aggregate span with the required bounded Architecture V2 fields.
