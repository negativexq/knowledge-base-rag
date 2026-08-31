# Rollback proof

Architecture V2 stores no state and changes no external schema. Rollback is a
server configuration change:

`architecture_v2 → baseline`

or:

`architecture_v2 → v3`

Both paths use the existing validator interface. No Alembic/DB migration,
Qdrant schema change, reindex, embedding regeneration, document rewrite, or
cache migration is required.

The checked-in/default runtime remains baseline. A validator infrastructure
exception fails closed through the existing application-abstain path, so
rollback is not being used as a hidden semantic fallback.
