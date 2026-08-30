from __future__ import annotations

from scripts.run_techqa_reranker_removal_debug import (
    EVIDENCE_BUDGET,
    TOP_N,
    classify_evidence_transition,
    select_rrf_top5,
)


def test_reranker_off_uses_frozen_rrf_top5_and_legacy_budget() -> None:
    assert TOP_N == 5
    assert EVIDENCE_BUDGET == 2400
    ranked = [{"rank": rank, "chunk_id": f"c{rank}"} for rank in range(1, 21)]
    assert [item["chunk_id"] for item in select_rrf_top5(ranked)] == [
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
    ]


def test_evidence_transition_detects_regression() -> None:
    assert classify_evidence_transition("ALL", "PARTIAL") == "ALL_TO_PARTIAL"


def test_semantic_scorecard_columns_are_blank() -> None:
    from scripts.run_techqa_reranker_removal_debug import scorecard_row

    row = scorecard_row("q", "ALL", "ALL", True, False)
    assert row["human_semantic_on"] == ""
    assert row["human_semantic_off"] == ""
    assert row["human_pair_preference"] == ""
    assert row["human_notes"] == ""
