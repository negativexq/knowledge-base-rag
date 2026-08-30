from __future__ import annotations

# ruff: noqa: E501
import json
from pathlib import Path

from scripts.audit_techqa_phase0 import HOLDOUT, OUT, chash, norm


def test_holdout_is_frozen_and_disjoint() -> None:
    integrity = json.loads((HOLDOUT / "integrity.json").read_text())
    sample = json.loads((HOLDOUT / "sample-identities.json").read_text())
    assert sample["sample_size"] == 50
    assert len(set(sample["selected_query_ids"])) == 50
    assert integrity["intersection_count"] == 0
    assert integrity["holdout_retrieval_calls"] == 0
    assert integrity["holdout_generation_calls"] == 0


def test_phase0_targets_and_accounting_are_artifact_derived() -> None:
    parse = json.loads((OUT / "parse-schema-summary.json").read_text())
    critical = json.loads((OUT / "critical-summary.json").read_text())
    section = json.loads((OUT / "sectionaware-summary.json").read_text())
    accounting = json.loads((OUT / "output-contract-accounting.json").read_text())
    assert parse["target_count"] == 11
    assert parse["application_state_conflict"] == 11
    assert critical["affected"] == 17
    assert critical["blocking"] == 8
    assert section["target_count"] == 10
    assert accounting["visible"] == 24
    assert accounting["fully_valid_support_id_visible"] == 14


def test_state_machine_is_not_provider_schema_encoded() -> None:
    provider = json.loads((OUT / "provider-structured-output-audit.json").read_text())
    contract = json.loads((OUT / "application-contract.json").read_text())
    assert provider["native_json_schema"] is True
    assert provider["strict"] is True
    assert provider["state_machine_encoded"] is False
    assert contract["mutual_exclusion_enforced_in_parser"] is True


def test_strict_anchor_replay_never_claims_recovery_when_anchors_do_not_fit() -> None:
    section = json.loads((OUT / "sectionaware-summary.json").read_text())
    target = section["target"]
    assert target["strict_anchor_preserving"]["all"] <= target["anchors_only"]["all"]
    assert target["strict_anchor_preserving"]["all"] == 0
    assert all(row["modes"]["strict_anchor_preserving"]["full_anchors_exceed_budget"] for row in jsonl(OUT / "sectionaware-replays.jsonl"))


def test_forensic_scripts_have_no_provider_or_retrieval_imports() -> None:
    for path in (Path("scripts/freeze_techqa_holdout.py"), Path("scripts/audit_techqa_phase0.py"), Path("scripts/finalize_techqa_phase0.py")):
        source = path.read_text()
        imports = [line.strip().lower() for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
        assert not any(any(name in line for name in ("openai", "ollama", "qdrant", "reranker")) for line in imports)


def test_text_normalization_and_hash_are_deterministic() -> None:
    assert norm("A\n  Cafe\u0301 value") == norm("A Café value")
    assert chash({"b": 2, "a": 1}) == chash({"a": 1, "b": 2})


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]
