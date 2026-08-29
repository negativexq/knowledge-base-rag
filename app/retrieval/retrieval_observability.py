# ruff: noqa: E501

"""Pure future-facing retrieval observability serializers.

This module intentionally does not invoke retrieval.  It gives future runs a
stable shape for authorized Top20/reranked/topN provenance.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def serialize_ranked_item(item: dict[str, Any], *, rank: int, score: float | None = None) -> dict[str, Any]:
    text = str(item.get("text", item.get("content", "")))
    metadata = item.get("metadata") or {}
    return {
        "chunk_id": str(item.get("chunk_id", "")),
        "source_id": str(item.get("source_id", metadata.get("source_id", ""))),
        "document_version": item.get("document_version", metadata.get("document_version")),
        "rank": int(rank),
        "score": score if score is not None else item.get("score"),
        "fused_score": item.get("fused_score"),
        "bge_score": item.get("bge_score"),
        "text_hash": _text_hash(text),
        "text_snapshot_ref": item.get("text_snapshot_ref"),
    }


def serialize_retrieval_observation(
    authorized_top20: list[dict[str, Any]],
    reranked_top20: list[dict[str, Any]],
    selected_top_n: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "retrieval-observability-v1",
        "authorized_top20": [serialize_ranked_item(item, rank=i + 1) for i, item in enumerate(authorized_top20)],
        "reranked_top20": [serialize_ranked_item(item, rank=i + 1) for i, item in enumerate(reranked_top20)],
        "selected_top_n": [serialize_ranked_item(item, rank=i + 1) for i, item in enumerate(selected_top_n)],
    }
