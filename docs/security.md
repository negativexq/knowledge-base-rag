# Security Model

Sprint 23 closes Phase 1 of the original roadmap's security work: making
"which tenant is allowed to see this chunk" a server-owned, mandatory
question the retrieval layer answers before a candidate ever reaches a
reranker or the generation model — not a convention, not a prompt-level
instruction, not a post-hoc citation check.

## Threat model

**In scope this sprint:**
- A user authenticated as tenant A retrieving, via any retrieval path
  (dense, sparse/BM25, or hybrid RRF fusion), content that belongs to
  tenant B.
- A user supplying a crafted retrieval filter (e.g. naming another
  tenant) attempting to widen what they can see.
- A user enumerating another tenant's document/source metadata via
  `/sources` or `/sync/*/history`.
- An operator triggering a sync for a source_type that belongs to a
  different tenant.
- Content belonging to another tenant leaking into a generated answer's
  citations.

**Explicitly out of scope this sprint** (see Known limitations):
- Prompt injection / untrusted-context attacks using content the user
  IS authorized to retrieve — that's Phase 2.
- A production-grade identity provider (OAuth/OIDC, SSO, MFA).
- Row-level "private to one user" visibility beyond the tenant boundary
  (the `visibility` payload field supports `tenant`/`private` as a
  schema, but nothing in this app produces `private` chunks yet).
- Encryption at rest, network-layer security, secrets management.

## Auth model

`Authorization: Bearer <token>` — the ONLY identity input this app
trusts. `app/security/auth.py::TokenAuthenticator` maps a token to a
`UserContext(user_id, tenant_id, roles)` server-side; nothing in a
request body, query string, or header other than this token can
influence tenant_id or role. `app/api/deps.py::get_current_user` is the
FastAPI dependency that resolves it — missing/invalid credentials are
`401`; a resolved but under-privileged identity attempting a
role-gated action is `403`.

This is intentionally NOT a full OAuth/OIDC implementation — see Known
limitations. The token→identity mapping is swappable behind
`TokenAuthenticator`'s one method without touching any call site.

## Tenant model

`UserContext.tenant_id` — a plain string, one tenant per user. Document/
chunk ownership is fixed at ingest time by SERVER-SIDE connector
configuration (`EMBEDDING_...` style env vars: `FILESYSTEM_TENANT_ID`,
`NOTION_TENANT_ID` — see `.env.example`), never chosen by a request.
This app's connector architecture is one connector instance per
source_type, so today's model is exactly "one tenant owns each
configured source_type" — not yet "many tenants share one connector."

## Roles

```
USER      — can chat (/chat)
OPERATOR  — can trigger/read syncs for their own tenant's sources
ADMIN     — OPERATOR privileges and above (linear hierarchy: ADMIN > OPERATOR > USER)
```

`app/security/models.py::role_satisfies` implements a simple linear
"at least this role" check — no permission graph.

## Retrieval enforcement point

```
authenticated user
      |
server-owned tenant/role (UserContext, from a validated token)
      |
mandatory ACL filter (app/retrieval/filters.py::build_acl_filter)
      |
Qdrant dense + sparse (BM25) retrieval, RRF-fused
      |
authorized candidates only
      |
reranker (CrossEncoderReranker)
      |
generation / citations
```

`app/retrieval/search.py::search()` takes a REQUIRED `RetrievalContext`
parameter (no default — every call site in this codebase says
explicitly whether it's a real tenant-scoped user or the internal
system context) and builds the ACL filter from it alone, ANDing it with
any user-supplied filter via `combine_filters()`. A caller passing
`filters=None` still gets the full ACL; a caller naming a different
tenant only narrows the result set further (AND semantics) — it can
never widen it. There is no "no context = return everything" path:
`build_acl_filter` raises `MissingTenantContextError` for a
non-system context with no tenant_id.

Internal, non-request-driven code (benchmark scripts, the Sprint 22
migration engine's quality gate, the evaluation CLI) explicitly
constructs `RetrievalContext.system()` — a privileged, tenant-unrestricted
context that is NEVER built from request data anywhere in this codebase.

**Verified, not just designed:** `tests/test_cross_tenant_e2e.py` proves
this against a REAL Qdrant server (not `:memory:`, which silently drops
filters on hybrid prefetch+fusion queries — see that file's own
docstring) — dense-only, sparse/BM25-only, and hybrid retrieval are all
tenant-isolated; a malicious filter naming another tenant cannot widen
access; the reranker only ever receives already-authorized candidates;
and a fabricated citation for another tenant's document is rejected by
grounding.

## Sync authorization

`POST /sync/{source_type}` and `GET /sync/{source_type}/history` require
OPERATOR+ AND ownership of that source_type by the caller's own tenant
(`app/api/sync.py::_require_owned_source_type`) — an operator for tenant
B can hold a genuinely valid OPERATOR token and still be refused (403)
for a source_type owned by tenant A.

## Sources enumeration

`GET /sources` (`app/api/sources.py`) filters the returned list to
source_types owned by the caller's own tenant AND computes
`document_count` from a tenant-scoped registry query — a source_type
belonging to another tenant doesn't appear in the response at all (not
even as a zero-count row), so its existence isn't observable.

## Registry and point identity

`app/registry/store.py`'s `documents` table primary key is
`(tenant_id, source_type, source_id)` (migrated from
`(source_type, source_id)` via `_migrate_add_tenant_id_and_rebuild_pk`,
backfilling every pre-existing row to `tenant_id="default"`). Qdrant
point IDs (`QdrantStore.point_id_for`) fold `tenant_id` into their
canonical key — two tenants sharing an otherwise-identical
`(source_type, source_id, doc_id, page, paragraph, char_range)` tuple
get genuinely different point UUIDs, never a silent overwrite. This
required bumping `CURRENT_INDEX_SCHEMA_VERSION` to 4 (every previously
indexed point's ID changes, since the old key format had no tenant
segment at all) — an existing index must be rebuilt via the Sprint 22
blue/green migration machinery, not mutated in place.

## Observability

Structured span attributes only — `acl.is_system`, `acl.tenant_scoped`
(from `search()`'s `build_acl_filter` span). No raw token, tenant_id, or
document content is logged. See Known limitations for what audit
logging does NOT yet exist.

## Local development auth

`.env.example` documents `AUTH_ENABLED` (default `true`) and
`AUTH_TOKENS_JSON` (optional override of the demo token fixture).
Setting `AUTH_ENABLED=false` is an EXPLICIT, loud local-dev-only escape
hatch — every request becomes `UserContext(user_id="dev-bypass",
tenant_id="local-dev", roles={ADMIN})`, and `app/wiring.py::build_app()`
logs a warning at startup when it's off. It is never the default and
must never be set in a real deployment.

Demo tokens (`app/security/auth.py::DEFAULT_DEV_TOKENS`) are for local
testing only — their names (`token-user-a`, `token-operator-b`, ...) are
deliberately unmistakable as non-production values.

The React console's selector is labelled **Development identity**. It is a
local/demo UX that stores one of these explicitly configured demo tokens in
browser localStorage; it is not production authentication. Production
authorization still occurs in FastAPI from the server-side token verifier and
tenant/role context.

## Browser CORS

FastAPI accepts an explicit, configurable `CORS_ORIGINS` allow-list (local
defaults are `http://localhost:5173,http://127.0.0.1:5173`). Credentialed CORS
is disabled because the console sends an Authorization header rather than
cookies. Production deployments must set their own exact frontend origin(s);
`*` is not a permitted authenticated-browser default.

## Known limitations

- **This is Phase 1 only.** Tenant ACL prevents cross-tenant retrieval,
  but retrieved content is not yet protected by the dedicated
  prompt-injection / untrusted-context controls planned for the next
  security sprint. A malicious document a tenant IS authorized to see
  could still attempt to manipulate generation — that threat is
  unaddressed here.
- **Authentication is demo/local-oriented**, not an enterprise identity
  provider. `TokenAuthenticator` is a simple in-memory dict lookup — no
  token expiry, rotation, revocation, or signature verification. A real
  deployment MUST replace `build_token_authenticator` with a real
  verifier (e.g. JWT validation against a real IdP) before handling
  real user data; the interface is designed to make that swap
  contained, but that swap has not been done here.
- **One tenant per connector instance**, not many tenants sharing one
  connector — matches this app's existing one-instance-per-source_type
  architecture. A deployment needing multiple tenants under literally
  the same source_type (e.g. two tenants each with their own
  "filesystem" root) needs a further connector-layer change, not
  addressed this sprint.
- **`visibility` payload field is schema-only.** Every chunk is written
  with `visibility="tenant"`; nothing produces or enforces a `private`
  (single-user) visibility level yet.
- **No structured audit-event persistence.** `authentication_failed`/
  `authorization_denied`/`sync_denied` are observable as HTTP status
  codes (401/403) and span attributes, but there is no dedicated,
  queryable audit log table — see the Sprint 23 report for what was and
  wasn't built here.
- **Registry tenant migration backfills everything to `"default"`.** A
  real multi-tenant deployment upgrading from a pre-Sprint-23 registry
  must manually reassign existing rows to their real tenant_id after
  the automatic migration runs — there is no way for the migration
  itself to infer the correct tenant retroactively.
