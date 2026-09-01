from __future__ import annotations

from scripts.experiments.run_techqa_topn_ablation import (
    OfflineQdrant,
    evidence_state,
    select_persisted_anchors,
)


def test_persisted_top_n_slices_ranked_input_without_recomputing() -> None:
    ranked = [
        {"rank": rank, "chunk_id": f"c{rank}", "bge_score": 1 / rank}
        for rank in range(1, 21)
    ]
    assert [item["chunk_id"] for item in select_persisted_anchors(ranked, 2)] == ["c1", "c2"]
    assert [item["chunk_id"] for item in select_persisted_anchors(ranked, 3)] == ["c1", "c2", "c3"]


def test_evidence_state_is_deterministic() -> None:
    assert evidence_state({"any": False, "all": False}) == "NONE"
    assert evidence_state({"any": True, "all": False}) == "PARTIAL"
    assert evidence_state({"any": True, "all": True}) == "ALL"


def test_offline_qdrant_has_no_retrieval_surface() -> None:
    client = OfflineQdrant({})
    assert hasattr(client, "scroll")
    assert not any(hasattr(client, name) for name in ("query_points", "search", "upsert"))
