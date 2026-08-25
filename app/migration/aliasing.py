"""Sprint 22: Qdrant alias indirection — the blue/green mechanism itself.

Qdrant treats an alias exactly like a real collection name for every
read/write operation (search, upsert, delete, scroll) — the alias is
resolved to its physical collection transparently, server-side, on every
call. That means NONE of app/ingestion/qdrant_store.py or
app/retrieval/hybrid_search.py needs to know an alias is even involved:
once `settings.qdrant_active_alias` ("kb_active" by default) exists as a
real Qdrant alias, passing that string as a "collection_name" everywhere
those modules already expect one is sufficient to get atomic, zero-
extra-code blue/green serving.

Qdrant's own update_collection_aliases call accepts a LIST of alias
operations applied together — a delete + a create for the same alias
name in one call never produces an intermediate state where the alias
doesn't exist at all (see atomic_switch_alias below), which is the
"no ‘hiç collection yok' ara state" requirement from the Sprint 22 spec.
"""

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.shared.config import Settings


def get_alias_target(client: QdrantClient, alias_name: str) -> str | None:
    """The physical collection alias_name currently points to, or None if
    the alias doesn't exist at all (pre-migration, or after a rollback
    that intentionally never re-created it — not this app's own rollback
    path, which always repoints rather than deletes, but a defensive
    case worth handling honestly regardless).
    """
    aliases = client.get_aliases().aliases
    for entry in aliases:
        if entry.alias_name == alias_name:
            return entry.collection_name
    return None


def resolve_active_collection_name(client: QdrantClient, settings: Settings) -> str:
    """What app/wiring.py should actually pass as "collection_name" to
    QdrantStore/search() right now. If settings.qdrant_active_alias
    exists as a real alias (a migration has activated at least once),
    that alias name itself is returned — Qdrant will keep resolving it to
    whichever physical collection is currently active, including across
    a later rollback/re-activation, with zero further code changes here.
    Otherwise (no migration has ever run) this falls back to the literal
    settings.qdrant_collection_name — today's exact pre-Sprint-22
    behavior, so an unmigrated deployment is entirely unaffected.
    """
    if get_alias_target(client, settings.qdrant_active_alias) is not None:
        return settings.qdrant_active_alias
    return settings.qdrant_collection_name


def atomic_switch_alias(client: QdrantClient, alias_name: str, target_collection: str) -> None:
    """Repoints alias_name at target_collection in ONE Qdrant call — a
    DeleteAliasOperation (a no-op if the alias didn't exist yet, e.g. the
    very first activation) followed by a CreateAliasOperation for the
    same alias name, batched into a single update_collection_aliases
    request so Qdrant applies both together rather than as two
    independently-observable writes.
    """
    client.update_collection_aliases(
        change_aliases_operations=[
            qmodels.DeleteAliasOperation(delete_alias=qmodels.DeleteAlias(alias_name=alias_name)),
            qmodels.CreateAliasOperation(
                create_alias=qmodels.CreateAlias(
                    alias_name=alias_name, collection_name=target_collection
                )
            ),
        ]
    )
