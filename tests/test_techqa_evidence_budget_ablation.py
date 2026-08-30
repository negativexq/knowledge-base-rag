from __future__ import annotations

import json
from pathlib import Path

from scripts.run_techqa_evidence_budget_ablation import (
    BUDGETS,
    CONFIG_HASH,
    CORPUS_HASH,
    HOLDOUT_HASH,
    SAMPLE_HASH,
    OfflineQdrant,
    load_prereg,
    validate_sources,
)


def test_preregistered_budgets_and_sources_are_frozen() -> None:
    prereg = load_prereg()
    assert prereg["budgets"] == list(BUDGETS) == [1200, 2400, 4800]
    assert prereg["source"]["debug50_hash"] == SAMPLE_HASH
    assert prereg["source"]["holdout50_hash"] == HOLDOUT_HASH
    assert prereg["source"]["canonical_config_fingerprint"] == CONFIG_HASH
    assert prereg["source"]["corpus_fingerprint"] == CORPUS_HASH
    assert prereg["implementation_check"] is False
    assert prereg["promotion_authority"] is False


def test_frozen_inputs_are_debug_only_and_holdout_disjoint() -> None:
    retrieval, reranker, micro = validate_sources()
    assert len(retrieval) == len(reranker) == 50
    assert len(micro) == 11
    holdout = json.loads(
        Path("artifacts/ragbench/canonical/techqa-holdout50-frozen/sample-identities.json").read_text()
    )
    assert not set(retrieval).intersection(holdout["selected_query_ids"])


def test_offline_qdrant_exposes_scroll_only() -> None:
    client = OfflineQdrant({})
    assert hasattr(client, "scroll")
    assert not any(hasattr(client, name) for name in ("query_points", "search", "upsert"))
