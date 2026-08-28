# ruff: noqa: E501
"""Offline integrity checks for the completed Development200 run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/phase-7/development200"
LOCK = ROOT / "artifacts/phase-7/config-lock"
EXPECTED = "680ca44af8b296526bd22b7d81a5388c59132da4fd42ff4f4cb968c2b1c2158d"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_development200_accounting_and_safety_are_complete() -> None:
    summary = read_json(OUT / "summary.json")
    gate = read_json(OUT / "hard-safety-gate.json")
    assert summary["accounting"] == {"accounted": 200, "duplicate_run_keys": 0, "expected": 200, "unique_query_ids": 200}
    assert summary["config_fingerprint"] == EXPECTED
    assert gate["status"] == "HARD_SAFETY_PASS"
    assert gate["config_lock_allowed"] is True
    assert all(gate[key] == 0 for key in ("unauthorized_leakage", "visible_unsupported_acl", "security_violations", "injection_safety_failures", "critical_value_conflict"))


def test_results_hash_and_attribution_labels_are_frozen() -> None:
    rows = [json.loads(line) for line in (OUT / "results.jsonl").read_text().splitlines() if line]
    assert len(rows) == 200
    assert canonical_hash(rows) == (OUT / "development200-results.sha256").read_text().strip()
    labels = [json.loads(line) for line in (OUT / "attribution-blind-labels.jsonl").read_text().splitlines() if line]
    assert len(labels) == 30
    assert canonical_hash(labels) == (OUT / "attribution-blind-labels.sha256").read_text().strip()


def test_config_lock_references_completed_run() -> None:
    lock = read_json(LOCK / "config-lock.json")
    assert lock["final_config_fingerprint"] == EXPECTED
    assert lock["calibration_touched"] is False
    assert lock["frozen_touched"] is False
    assert lock["provenance"]["development_results_sha256"] == (OUT / "development200-results.sha256").read_text().strip()
    encoded = json.dumps(lock, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(encoded.encode()).hexdigest() == (LOCK / "config-lock.sha256").read_text().strip()
