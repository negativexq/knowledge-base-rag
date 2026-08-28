"""Offline checks for the final Smoke36 checkpoint and config gate."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "artifacts/phase-7/phase7-closure"


def test_smoke36_has_complete_frozen_v22_checkpoint() -> None:
    summary = json.loads((CLOSURE / "smoke36-summary.json").read_text(encoding="utf-8"))
    integrity = json.loads(
        (CLOSURE / "smoke36-config-integrity.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "SMOKE36_COMPLETED"
    assert summary["query_count"] == 36
    assert summary["provider_failures"] == 0
    assert summary["config_fingerprint"] == integrity["config_fingerprint"]
    assert integrity["status"] == "PASS"


def test_smoke36_safe_acl_abstentions_are_not_counted_as_unsupported() -> None:
    summary = json.loads((CLOSURE / "smoke36-summary.json").read_text(encoding="utf-8"))
    safety = summary["safety"]
    assert safety["acl_unauthorized_leakage"] == 0
    assert safety["acl_visible_unsupported"] == 0
    assert summary["safe_abstention"] >= 3
