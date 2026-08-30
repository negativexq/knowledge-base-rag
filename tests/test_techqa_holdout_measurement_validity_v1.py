"""Focused zero-inference tests for the HOLDOUT measurement-validity audit."""

import csv
import json
from pathlib import Path

from scripts.audit_techqa_holdout_measurement_validity_v1 import state


def test_state_classification_is_deterministic() -> None:
    assert state({"all": True, "any": True}) == "ALL"
    assert state({"all": False, "any": True}) == "PARTIAL"
    assert state({"all": False, "any": False}) == "NONE"


def test_audit_artifacts_prove_arm_independent_corpus_scope_failure() -> None:
    root = Path("artifacts/ragbench/canonical/techqa-holdout-measurement-validity-audit-v1")
    summary = json.loads((root / "03-holdout-corpus-coverage/coverage-summary.json").read_text())
    status = json.loads((root / "06-report/audit-status.json").read_text())
    assert summary["gold_doc_in_corpus"] == 0
    assert summary["annotation_mapped_to_corpus"] == 0
    assert summary["first_failure_stage"]["CORPUS_MISSING"] == 41
    assert status["verdict"] == "HOLDOUT_RUN_INVALID_CORPUS_SCOPE"


def test_debug_replay_reproduces_canonical_metrics_and_preserves_raw_denominator() -> None:
    root = Path("artifacts/ragbench/canonical/techqa-holdout-measurement-validity-audit-v1")
    summary = json.loads(
        (root / "01-debug-scorer-replay/debug-replay-summary.json").read_text()
    )
    assert summary["ON"]["any"] == 36
    assert summary["ON"]["all"] == 29
    assert summary["ON"]["mean_recall"] == 0.8794661023953517
    assert summary["OFF"]["any"] == 37
    assert summary["OFF"]["all"] == 32
    assert summary["OFF"]["mean_recall"] == 0.9205004473285319
    assert summary["ON"]["mapping_difference_rows"] == 0
    assert summary["OFF"]["mapping_difference_rows"] == 0


def test_zero_inference_audit_has_no_provider_or_retrieval_execution_path() -> None:
    source = Path("scripts/audit_techqa_holdout_measurement_validity_v1.py").read_text()
    forbidden_calls = (
        "QdrantClient(",
        "OpenAIGeneratorClient(",
        "OllamaClient(",
        "CrossEncoder(",
        "hybrid_search(",
    )
    assert all(call not in source for call in forbidden_calls)


def test_audit_does_not_read_or_fill_blind_scorecard() -> None:
    scorecard = Path(
        "artifacts/ragbench/canonical/techqa-reranker-holdout-oneshot-v1/07-blind-review/blind-scorecard.csv"
    )
    rows = list(csv.DictReader(scorecard.open()))
    assert len(rows) == 50
    assert all(not row["candidate_a_semantic"] for row in rows)
    assert all(not row["candidate_b_semantic"] for row in rows)
    assert all(not row["pair_preference"] for row in rows)
