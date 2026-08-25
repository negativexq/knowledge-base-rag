from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.migration.aliasing import (
    atomic_switch_alias,
    get_alias_target,
    resolve_active_collection_name,
)
from app.shared.config import Settings


def _client_with_collections(*names: str) -> QdrantClient:
    client = QdrantClient(":memory:")
    for name in names:
        client.create_collection(
            name, vectors_config=qmodels.VectorParams(size=4, distance=qmodels.Distance.COSINE)
        )
    return client


def test_get_alias_target_is_none_when_alias_does_not_exist():
    client = _client_with_collections("a")

    assert get_alias_target(client, "kb_active") is None


def test_resolve_active_collection_name_falls_back_to_literal_when_no_alias_exists():
    """Pre-Sprint-22 / never-migrated deployment: no alias exists yet, so
    the resolved name must be the literal settings.qdrant_collection_name
    — today's exact behavior, unaffected by this sprint.
    """
    client = _client_with_collections("kb_chunks")
    settings = Settings(qdrant_collection_name="kb_chunks")

    assert resolve_active_collection_name(client, settings) == "kb_chunks"


def test_resolve_active_collection_name_uses_the_alias_once_it_exists():
    client = _client_with_collections("kb_chunks", "kb_qwen3_4b_1024_abc")
    settings = Settings(qdrant_active_alias="kb_active")
    atomic_switch_alias(client, "kb_active", "kb_qwen3_4b_1024_abc")

    assert resolve_active_collection_name(client, settings) == "kb_active"


def test_atomic_switch_alias_first_activation_has_no_delete_error():
    client = _client_with_collections("target")

    atomic_switch_alias(client, "kb_active", "target")

    assert get_alias_target(client, "kb_active") == "target"


def test_atomic_switch_alias_repoints_from_one_collection_to_another():
    client = _client_with_collections("old", "new")
    atomic_switch_alias(client, "kb_active", "old")

    atomic_switch_alias(client, "kb_active", "new")

    assert get_alias_target(client, "kb_active") == "new"
    # old collection itself must still exist — switching an alias never
    # deletes the collection it used to point at.
    assert client.collection_exists("old")


def test_qdrant_serves_search_through_the_alias_transparently():
    """The load-bearing property this whole architecture depends on:
    Qdrant treats an alias exactly like a real collection name for a
    search call, with zero special-casing needed anywhere else in this
    app. Concrete proof, not just an assumption.
    """
    client = _client_with_collections("physical")
    client.upsert(
        "physical",
        points=[qmodels.PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"tag": "x"})],
    )
    atomic_switch_alias(client, "kb_active", "physical")

    results = client.query_points("kb_active", query=[1.0, 0.0, 0.0, 0.0], limit=1).points

    assert results[0].payload["tag"] == "x"
