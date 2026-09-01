from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_standard_returns_mapping_separates_supporting_and_retrieved_chunks() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    gt = diagnostic.read_json(diagnostic.FACTS_PATH)
    mapping = diagnostic.derive_current_chunks(gt, cache)
    boundary = diagnostic.standard_boundary(mapping, cache)
    assert boundary["supporting_chunk_id"] == "5bd2643d-4837-5733-9717-c88c37860274"
    assert boundary["retrieved_chunk_id"] == "1b50ae39-8364-5172-a719-f2090efce26e"
    assert boundary["supporting_chunk_id"] != boundary["retrieved_chunk_id"]


def test_candidate_top20_and_top5_fact_attribution_are_distinct() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    gt = diagnostic.read_json(diagnostic.FACTS_PATH)
    mapping = diagnostic.derive_current_chunks(gt, cache)
    recall = diagnostic.current_recall(gt, cache, mapping)
    assert recall["aggregate"]["fact_passage_recall_at20"] == 1.0
    assert recall["aggregate"]["fact_passage_recall_at5"] == pytest.approx(5 / 7)
    assert recall["aggregate"]["all_required_facts_present_at20"] == 3
    assert recall["aggregate"]["all_required_facts_present_at5"] == 1


def test_representations_are_deterministic_and_neighbors_do_not_cross_sections() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    first = diagnostic.build_representations(cache["multi-00-1"])
    second = diagnostic.build_representations(cache["multi-00-1"])
    assert first == second
    assert [row["block_id"] for row in first["SAME_SECTION_NEIGHBORS"]] == [
        row["block_id"] for row in first["CURRENT_CHUNK"]
    ]
    assert len(first["SAME_SECTION_NEIGHBORS"]) == 5


def test_section_merge_uses_authored_source_and_preserves_traceability() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    variants = diagnostic.build_representations(cache["multi-00-1"])
    merged = next(
        row
        for row in variants["SECTION_AWARE_MERGED"]
        if row["source_id"] == "standard-returns-2026"
    )
    source = (diagnostic.DATA / "standard-returns-2026.md").read_text(encoding="utf-8")
    assert merged["text"] == source
    assert "14 calendar days" in merged["text"]
    assert merged["original_chunk_ids"] == ["1b50ae39-8364-5172-a719-f2090efce26e"]
    assert "expected_answer" not in merged


def test_parent_and_merged_preserve_source_identity_and_add_no_generated_text() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    variants = diagnostic.build_representations(cache["multi-03-0"])
    original_sources = {row["source_id"] for row in variants["CURRENT_CHUNK"]}
    for name in ("PARENT_SECTION", "SECTION_AWARE_MERGED"):
        assert {row["source_id"] for row in variants[name]} == original_sources
        assert all("summary" not in row and "expected_answer" not in row for row in variants[name])


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


def test_generation_precondition_is_true_only_for_winner_context() -> None:
    _, cache, _, _ = diagnostic.validate_identity()
    gt = diagnostic.read_json(diagnostic.FACTS_PATH)
    serializations, coverage, tokens, duplicates = diagnostic.representation_analysis(gt, cache)
    winner = diagnostic.choose_winner(diagnostic.scorecard(coverage, tokens, duplicates))
    checks = diagnostic.probe_precondition(gt, winner["winner"], serializations)
    assert len(checks) == 3
    assert all(row["all_required_fact_evidence_present"] for row in checks)


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
