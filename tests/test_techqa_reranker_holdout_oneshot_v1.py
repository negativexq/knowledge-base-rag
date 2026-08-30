from __future__ import annotations

import csv
from pathlib import Path

from scripts.run_techqa_reranker_holdout_oneshot_v1 import (
    OUT,
    config_diff,
    pair_execution_order,
)


def test_only_reranker_differs() -> None:
    diff = config_diff()
    assert diff["different_fields"] == ["ranking_source", "reranker_enabled"]
    common_keys = set(diff["on"]) & set(diff["off"])
    assert {key for key in common_keys if diff["on"][key] != diff["off"][key]} == {
        "ranking_source",
        "reranker_enabled",
    }
    assert diff["on"]["top_n"] == diff["off"]["top_n"] == 5
    assert diff["on"]["section_aware_budget"] == diff["off"]["section_aware_budget"] == 2400


def test_paired_order_is_deterministic_and_balanced() -> None:
    ids = [f"Q{i:03d}" for i in range(50)]
    first = pair_execution_order(ids)
    second = pair_execution_order(ids)
    assert first == second
    assert all(set(item["order"]) == {"ON", "OFF"} for item in first)
    assert 20 <= sum(item["order"][0] == "ON" for item in first) <= 30


def test_blind_scorecard_template_has_blank_semantic_fields() -> None:
    path = OUT / "07-blind-review/blind-scorecard.csv"
    if not path.exists():
        return
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    assert len(rows) == 50
    assert len({row["query_id"] for row in rows}) == 50
    for row in rows:
        assert row["candidate_a_semantic"] == ""
        assert row["candidate_b_semantic"] == ""
        assert row["pair_preference"] == ""


def test_no_holdout_content_is_imported_by_template() -> None:
    source = Path("scripts/run_techqa_reranker_holdout_oneshot_v1.py").read_text()
    assert "sample-identities.json" in source
    assert "record_holdout_access" in source
    assert source.index("record_holdout_access") < source.index("load_holdout_rows")
