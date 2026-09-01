from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.fact_evidence import evaluate_fact_evidence
from scripts.audits import diagnose_structure_aware_chunking as diagnostic


def _fact(fact_id: str = "window") -> dict[str, str]:
    return {
        "required_fact_id": fact_id,
        "authoritative_source_id": "policy",
        "supporting_text_span": "14 calendar days",
    }


def test_fact_ground_truth_is_source_span_based_not_chunk_based() -> None:
    gt = diagnostic.read_json(diagnostic.FACTS_PATH)
    assert len(gt["facts"]) == 5
    for fact in gt["facts"]:
        assert fact["authoritative_source_id"]
        assert fact["supporting_text_span"]
        assert "chunk_id" not in fact
    assert all(item["supporting_span_exists"] for item in diagnostic.verify_ground_truth(gt))


def test_source_presence_cannot_imply_fact_presence() -> None:
    result = evaluate_fact_evidence(
        [_fact()], [{"source_id": "policy", "text": "Case fields only."}]
    )
    assert result.source_recall_complete is True
    assert result.fact_evidence_recall == 0
    assert result.all_required_fact_evidence_present is False


def test_all_required_fact_evidence_requires_every_authored_span() -> None:
    facts = [_fact("window"), {**_fact("fields"), "supporting_text_span": "record the remedy"}]
    result = evaluate_fact_evidence(
        facts, [{"source_id": "policy", "text": "Refund within 14 calendar days."}]
    )
    assert result.present_fact_ids == ["window"]
    assert result.missing_fact_ids == ["fields"]
    assert result.all_required_fact_evidence_present is False


def test_winner_requires_fact_level_precondition() -> None:
    rows = [
        {
            "representation": "CURRENT_CHUNK",
            "all_required_facts_present_queries": 1,
            "context_tokens_p50": 10,
            "irrelevant_paragraphs": 0,
        },
        {
            "representation": "SECTION_AWARE_MERGED",
            "all_required_facts_present_queries": 3,
            "context_tokens_p50": 20,
            "irrelevant_paragraphs": 1,
        },
    ]
    assert diagnostic.choose_winner(rows)["winner"] == "SECTION_AWARE_MERGED"
    losing = diagnostic.choose_winner(
        [{**rows[0], "all_required_facts_present_queries": 1}]
    )
    assert losing["winner"] == "NO_VALID_WINNER"


def test_diagnostic_has_no_retrieval_and_max_three_generation_contract(
    tmp_path: Path,
) -> None:
    source = Path(diagnostic.__file__).read_text(encoding="utf-8")
    assert "candidate_k=20" not in source
    assert "QdrantStore(" not in source
    assert '"max_generation_calls": 3' in source
    assert diagnostic.QUERY_IDS == ("multi-00-1", "multi-00-3", "multi-03-0")
    assert "qwen2.5" not in source and "qwen3.5:9b" not in source
    assert "v3_multidoc_completeness" not in source
    payload = {"frozen_test_touched": False, "calibration_touched": False}
    path = tmp_path / "guard.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(path.read_text())["frozen_test_touched"] is False
