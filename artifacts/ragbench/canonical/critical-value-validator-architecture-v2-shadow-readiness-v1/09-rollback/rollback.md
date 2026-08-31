# Rollback proof

Selector parsing and configuration tests passed for:

- `architecture_v2` -> `baseline`
- `architecture_v2` -> `v3`
- shadow true -> shadow false

These are configuration-only transitions. Settings are loaded at process
startup, so an environment change requires the normal controlled process
restart/redeploy; hot reload is not claimed. No DB, Qdrant, reindex, embedding,
or stored-data migration is involved.
