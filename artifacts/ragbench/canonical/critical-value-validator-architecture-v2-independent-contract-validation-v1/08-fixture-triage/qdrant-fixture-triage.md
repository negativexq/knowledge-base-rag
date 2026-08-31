# Qdrant fixture triage

The previous full deterministic run reported three errors in
`tests/test_cross_tenant_e2e.py`. The failures were collection lifecycle
responses: a `404 Not Found` while one test expected the shared collection and
a `409 Conflict` while another concurrent fixture attempted to create the same
collection.

Classification:

- `PRE_EXISTING_FIXTURE_FAILURE`: 0 established from a clean historical run in
  this task.
- `ENVIRONMENT_DEPENDENT_FIXTURE_FAILURE`: 3.
- `TASK_CAUSED_REGRESSION`: 0.
- `UNKNOWN`: 0.

Basis: the failures are in the cross-tenant Qdrant fixture, Architecture V2
is an unselected pure evaluation path, and no Qdrant/ingestion/retrieval code
was changed for this validation. The architecture-specific deterministic run
excluding this unrelated fixture passed. The full-suite errors remain
non-blocking technical debt for the architecture decision, but are not hidden.
