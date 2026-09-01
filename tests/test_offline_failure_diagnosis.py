# ruff: noqa: E501

"""Provider-free contract tests for the Phase 7.6 offline diagnosis."""

from __future__ import annotations

import json
from pathlib import Path


def test_phase_7_6_no_inference_or_retrieval_clients_in_script() -> None:
    source = Path("scripts/audits/diagnose_offline_failure.py").read_text(encoding="utf-8")
    forbidden = ("ollama", "qdrant", "reranker", "openai", "anthropic", "deep_eval")
    lowered = source.casefold()
    assert not any(f"import {name}" in lowered or f"from {name}" in lowered for name in forbidden)


def test_phase_7_6_outputs_are_json_serializable() -> None:
    output = Path("artifacts/phase-7/offline-failure-diagnosis")
    for path in output.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in output.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
