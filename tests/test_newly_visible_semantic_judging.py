"""Provider-free checks for the five-output semantic judging artifact."""

from __future__ import annotations

import json
from pathlib import Path


def test_newly_visible_population_is_exactly_five() -> None:
    root = Path(__file__).resolve().parents[1]
    post = root / "artifacts/ragbench/canonical/basic50-post-validator-fix/replay-results.jsonl"
    rows = [json.loads(line) for line in post.read_text().splitlines() if line]
    target = [row for row in rows if not row["old_visible"] and row["new_visible"]]
    assert len(target) == 5
    assert len({row["query_id"] for row in target}) == 5


def test_judge_aggregation_denominators_are_frozen() -> None:
    root = Path(__file__).resolve().parents[1]
    post = root / "artifacts/ragbench/canonical/basic50-post-validator-semantic"
    if not (post / "final-semantic-summary.json").exists():
        return
    final = json.loads((post / "final-semantic-summary.json").read_text())
    assert final["visible"] == 38
    assert final["unavailable"] == 12
    assert final["correct"] + final["partial"] + final["incorrect"] == 38


def test_judge_runner_has_no_generation_or_retrieval_calls() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/judge_newly_visible_canonical.py").read_text().lower()
    assert "chat_json" in source
    assert "generate_one" not in source
    assert "qdrant.search" not in source
    assert "from app.reranker" not in source
    assert "embedding_model" not in source
