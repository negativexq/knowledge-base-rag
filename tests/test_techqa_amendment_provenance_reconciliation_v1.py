from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.reconcile_techqa_amendment_provenance_v1 import (
    EXPECTED,
    SIDECAR,
    V1,
    hash_variants,
)


def test_raw_file_sha_helper_and_sidecar_match() -> None:
    raw_hash = hashlib.sha256(V1.read_bytes()).hexdigest()
    sidecar_hash = SIDECAR.read_text(encoding="utf-8").strip().split()[0]
    assert raw_hash == sidecar_hash


def test_no_legitimate_variant_matches_historical_expected_hash() -> None:
    variants = hash_variants()
    assert variants["any_legitimate_representation_matches_expected"] is False
    assert EXPECTED not in variants["variants"].values()


def test_v1_has_no_self_referential_hash_field() -> None:
    value = json.loads(V1.read_text(encoding="utf-8"))
    assert not any("sha256" in key.lower() and "original" not in key.lower() for key in value)


def test_reconciliation_does_not_include_holdout_execution_inputs() -> None:
    source = Path(__file__).parents[1] / "scripts/reconcile_techqa_amendment_provenance_v1.py"
    text = source.read_text(encoding="utf-8")
    assert "sample-identities.json" not in text
    assert "holdout-arm-map.json" in text
