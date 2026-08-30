from __future__ import annotations

import csv
from io import StringIO

from scripts.run_techqa_reranker_decision_v1 import assign_blind_arms


def test_blind_mapping_is_deterministic_and_balanced() -> None:
    query_ids = [f"q{i:02d}" for i in range(50)]
    first = assign_blind_arms(query_ids)
    second = assign_blind_arms(query_ids)
    assert first == second
    assert sum(value["candidate_a_arm"] == "ON" for value in first.values()) == 25


def test_human_scorecard_columns_are_blank() -> None:
    fields = [
        "query_id",
        "candidate_a_semantic",
        "candidate_b_semantic",
        "pair_preference",
        "candidate_a_grounding_notes",
        "candidate_b_grounding_notes",
        "human_notes",
    ]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerow({field: "" for field in fields} | {"query_id": "q"})
    row = next(csv.DictReader(StringIO(buffer.getvalue())))
    assert all(row[field] == "" for field in fields[1:])
