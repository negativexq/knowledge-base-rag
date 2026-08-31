# Rollback review

Architecture V2 is pure request-local deterministic validation. It does not
own database, Qdrant, index, embedding, or document state.

Future rollback is therefore configuration-only:

`architecture_v2 → baseline` or `architecture_v2 → v3`.

Required rollback properties:

- no DB/Alembic migration;
- no Qdrant schema change;
- no reindex or embedding regeneration;
- no document rewrite;
- no cache invalidation dependency.

If an authoritative Architecture V2 invocation fails, the integration should
fail closed as validator infrastructure failure and produce an application
abstain/error according to the existing strict safety policy. It must not
silently fail open to an answer. Operator rollback is then a server-side
config change.
