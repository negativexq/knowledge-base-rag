# Document permissions

The production wiring now enforces document permissions in addition to tenant
isolation and the request's optional source selection. Policies are keyed by
`(tenant_id, source_type, source_id)` and stored independently from embeddings
in `DOCUMENT_PERMISSIONS_DB_PATH` (default `data/document-permissions.db`).
Re-ingestion/version changes retain the logical document's policy.

**Default access is restricted.** An unconfigured document is unreadable,
including by ADMIN. Existing documents need an explicit grant after this upgrade;
no permissions are guessed or backfilled from old tenant-wide visibility.
The application does not restart itself or edit the existing `.env` file.
Production app factories require a permission store; the real wiring provides
one. Pure development/test factories can still inject no store explicitly.

## Administration

Sign in as ADMIN, open **Knowledge → Document permissions**, select a document,
then choose:

- **Restricted:** grant exact user IDs and/or group IDs. A matching user OR group
  grants access within the same tenant. Empty lists deny everyone.
- **Tenant-wide:** allow all authenticated users in that tenant.

ADMIN can manage policy metadata for its own tenant, including the identifiers
of otherwise hidden documents. The role does not automatically grant document
reading. An administrator can explicitly grant itself access; this is an audited
policy change. OPERATOR cannot edit grants. Policy writes carry a revision;
a stale edit returns 409 and must be reloaded rather than silently overwriting
another administrator's change. Document policy mutations produce structured
`document_permissions_changed` audit logs with actor/tenant/document/revision,
without content or bearer tokens. The policy database stores current state and
revision, not a complete historical audit ledger.

Authenticated API:

- `GET /research/document-permissions?offset=0`: ADMIN-only, tenant registry
  documents with policies, 50 per page. Contains no document text.
- `PUT /research/document-permissions`: ADMIN-only update of an existing document
  in the caller's tenant. Body: `source_type`, `source_id`, `access`, `user_ids`,
  `group_ids`, `revision`. A client-supplied tenant field is rejected.

Group membership comes exclusively from the server's authenticated identity.
The existing `AUTH_TOKENS_JSON` mapping accepts an optional `group_ids` list:

```json
{"configured-token":{"user_id":"alice","tenant_id":"acme","roles":["USER"],"group_ids":["engineering"]}}
```

This is an example shape, not a usable production credential. The existing
local token authenticator still needs replacement by an IdP verifier for a real
enterprise deployment. Sending group IDs in a chat body or request header grants
no rights. Group names are tenant-scoped through the owning policy.

`DOCUMENT_DEFAULT_ACCESS=tenant` is an explicit compatibility choice: documents
without policies become tenant-wide. A stored restricted policy still denies
unlisted principals. It weakens the default-deny posture and must not be used
when unconfigured documents might be confidential. Deleting a policy row in
this mode would restore tenant-wide access; use the supported restricted/empty
grant update to revoke access. With the secure default, a new or empty policy
database grants nothing.

## Enforcement and revocation

The mandatory Qdrant filter includes current document grants before dense and
sparse retrieval. Post-retrieval checks verify tenant and document again before
reranking/model use. Section expansion, the evidence ledger, document navigation,
manual document reading, and page-image anchors use the same server-owned
permission view. Unknown/missing source identifiers fail closed with permissions
enabled. A failed permission-store read propagates an error; it never falls back
to tenant-wide access. Explicit internal system contexts retain their privileged
migration/benchmark behavior and are not selectable through request data.

Normal document listings, overview totals and source counts exclude documents
the user cannot read. A denied document-read request returns 404 before returning
version/index metadata. Permission administration is the separate ADMIN metadata
surface. Filesystem ingestion rejects duplicate filename slugs to prevent two
physical files from silently sharing one policy identity.

Policy views read current SQLite state, not a long-lived grant cache. Subsequent
queries/reads see revocation without re-embedding or restart. Ledger reads remove
newly denied units. Agent candidates and the chat stream recheck permissions
before releasing new content, including newly cited resolver metadata. If rights
are removed during research, pending content is withheld with
`DOCUMENT_ACCESS_REVOKED`.

Revocation cannot undo a provider request or content already delivered to a
browser. Local conversation history/exports, user-submitted feedback snapshots,
optional forensic captures and backups have separate retention/access policies;
this layer is not a DLP service and cannot prevent authorized users from sharing
text. Feedback reviewer roles still govern user-submitted reports. Operation/sync
administration metadata retains its existing role/tenant policy.

These are application-managed grants. Connector-native Notion/filesystem/IdP
permissions are **not imported or synchronized automatically**. Operators must
maintain application grants until an authoritative connector/IdP integration is
provided. Keep service ports, database files and source roots protected.
