"""Offline integrity checks for the corrected TechQA HOLDOUT execution."""

import csv
import hashlib
import json
from pathlib import Path

from scripts.run_techqa_reranker_corrected_holdout_execution_v2 import (
    AMENDMENT_HASH,
    OUT,
    config_diff,
    verify_amendment,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_amendment_v2_is_exact_and_authorized() -> None:
    _, digest = verify_amendment()
    assert digest == AMENDMENT_HASH


def test_only_reranker_diff_is_declared() -> None:
    assert config_diff()["different_fields"] == ["ranking_source", "reranker_enabled"]


def test_corrected_run_artifacts_are_complete_and_semantic_blank() -> None:
    scorecard = OUT / "08-blind-review/blind-scorecard.csv"
    rows = list(csv.DictReader(scorecard.open(encoding="utf-8", newline="")))
    assert len(rows) == 50
    assert len({row["query_id"] for row in rows}) == 50
    semantic_fields = {"candidate_a_semantic", "candidate_b_semantic", "pair_preference"}
    assert all(not any(row[field] for field in semantic_fields) for row in rows)
    assert len((OUT / "03-retrieval/shared-rrf-top20.jsonl").read_text().splitlines()) == 50
    assert len((OUT / "04-evidence/on-evidence.jsonl").read_text().splitlines()) == 50
    assert len((OUT / "04-evidence/off-evidence.jsonl").read_text().splitlines()) == 50
    assert len((OUT / "05-generation/paired-generation.jsonl").read_text().splitlines()) == 100


def test_arm_map_sidecar_is_mechanical_only() -> None:
    arm_map = OUT / "08-blind-review/corrected-arm-map.json"
    sidecar = OUT / "08-blind-review/corrected-arm-map.sha256"
    assert _sha256(arm_map) == sidecar.read_text(encoding="utf-8").strip()


def test_pre_retrieval_and_final_status_are_frozen() -> None:
    gate = json.loads((OUT / "02-preflight/pre-retrieval-gate.json").read_text())
    status = json.loads((OUT / "09-report/experiment-status.json").read_text())
    assert gate["PRE_RETRIEVAL_GATE"] == "PASS"
    assert gate["debug_overlap"] == 0
    assert status["semantic_status"] == "PENDING_BLIND_REVIEW"
    assert status["semantic_unblind"] is False
    assert status["terra_calls"] == 0
