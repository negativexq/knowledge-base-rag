# Sprint 23 Plan — Security Boundary & Tenant-Aware Retrieval

## Goal

Close Phase 1 of the original roadmap: make "which tenant is authorized
to see this chunk" a mandatory, server-owned question the retrieval
layer answers BEFORE a candidate ever reaches a reranker or generation
— not a prompt instruction, not a post-hoc citation check.

## Security model

`UserContext(user_id, tenant_id, roles)` — built exclusively from a
validated `Authorization: Bearer <token>` via
`app/security/auth.py::TokenAuthenticator`, never from request body/
query data. Three linear roles: `USER < OPERATOR < ADMIN`.
`RetrievalContext(tenant_id, is_system)` is a DELIBERATELY separate type
— `RetrievalContext.system()` is the only way to get cross-tenant
retrieval, and it's never constructed from a real request anywhere in
this codebase.

## Mandatory ACL enforcement

`app/retrieval/search.py::search()` gained a REQUIRED `context:
RetrievalContext` parameter (no default). `app/retrieval/filters.py::
build_acl_filter` builds the `tenant_id == ...` condition from it —
returning `None` only for an explicit system context, raising
`MissingTenantContextError` for anything else missing a tenant_id (fail
closed, never "return everything"). `combine_filters()` ANDs the ACL
with any user-supplied filter — a malicious filter naming another
tenant only narrows results, never widens them.

## Chunk/registry/point-identity changes

- `Chunk` gained `tenant_id: str = "default"` — set via
  `dataclasses.replace()` in `ingest_connector` immediately after
  chunking (chunker functions themselves stay tenant-agnostic).
- Qdrant payload gained `tenant_id` + `visibility` ("tenant" for now).
- `QdrantStore.point_id_for` folds `tenant_id` into its canonical key —
  `CURRENT_INDEX_SCHEMA_VERSION` bumped 3→4 (every existing point ID
  changes).
- `DocumentRegistry`'s primary key widened from `(source_type,
  source_id)` to `(tenant_id, source_type, source_id)` via a real
  rename-rebuild-copy-drop migration (`_migrate_add_tenant_id_and_rebuild_pk`),
  backfilling every pre-existing row to `tenant_id="default"`.
- Every per-document Qdrant maintenance method (`delete_by_source`,
  `delete_stale_versions`, `delete_version`, `has_document_version`,
  `count_for_document_version`, `list_point_ids_for_version`,
  `list_source_ids`) gained a `tenant_id` parameter.

## Endpoint authorization

- `/chat`: USER+, `RetrievalContext.for_user()` built from the resolved
  token — never from the request body.
- `/sources`: USER+, tenant-scoped (a source_type owned by another
  tenant doesn't appear at all).
- `/sync/{source_type}` and `/sync/{source_type}/history`: OPERATOR+ AND
  ownership of that source_type by the caller's tenant
  (`app/api/sync.py::_require_owned_source_type`).

## Tenant ownership at ingest time

One connector instance per source_type (this app's existing
architecture) = one tenant per source_type, configured server-side
(`FILESYSTEM_TENANT_ID`, `NOTION_TENANT_ID`). `SyncManager` gained a
`tenant_ids: dict[str, str]` mapping, threaded into every
`ingest_connector()` call it makes.

## Verification strategy

- Hermetic unit tests for auth, RBAC, ACL filter construction/
  composition, registry/point-identity isolation — no real services
  needed.
- `tests/test_cross_tenant_e2e.py` — REAL Qdrant server (required:
  `:memory:` silently drops filters on hybrid prefetch+fusion queries),
  two real tenants sharing one collection, dense/sparse/hybrid isolation,
  filter-override attack, reranker-input isolation, citation leakage.
- A real local script (not committed — throwaway) driving the actual
  `app.main.create_app()` FastAPI app with real tokens, real Ollama
  embeddings, and real Qdrant — producing
  `artifacts/security-sprint23/{security-validation.json,report.md}`.

## Explicitly out of scope

Prompt injection / untrusted-context defenses, a real IdP/OAuth/OIDC,
multilingual reranker changes, chunker redesign, vLLM/PostgreSQL
migrations, distributed job queues — see `docs/security.md`'s Known
limitations.
