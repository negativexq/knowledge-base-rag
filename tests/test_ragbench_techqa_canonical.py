from __future__ import annotations

from app.llm.openai_client import canonical_hash
from scripts.run_ragbench_techqa_canonical import (
    DATASET_REVISION,
    RERANKER_MODEL,
    SAMPLE_SIZE,
    SEED,
    load_rows,
    sample_rows,
    unique_candidates,
)


def test_techqa_pinned_pool_and_sample_are_deterministic() -> None:
    rows = load_rows()
    selected, sample = sample_rows(rows)

    assert len(rows) == 314
    assert len(unique_candidates(rows)) == 157
    assert len(selected) == SAMPLE_SIZE == 50
    assert len({row["id"] for row in selected}) == 50
    assert sample["dataset_revision"] == DATASET_REVISION
    assert sample["seed"] == SEED == 42
    assert canonical_hash(sample) == (
        "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
    )


def test_techqa_deduplication_retains_first_pinned_parquet_row() -> None:
    rows = load_rows()
    candidates = unique_candidates(rows)
    first_indices: dict[str, int] = {}
    for row in rows:
        first_indices[str(row["id"])] = min(
            first_indices.get(str(row["id"]), int(row["_row_index"])),
            int(row["_row_index"]),
        )

    assert all(int(row["_row_index"]) == first_indices[str(row["id"])] for row in candidates)
    assert all(row["generation_model_name"] == "gpt-3.5-turbo-0125" for row in candidates)


def test_techqa_runner_uses_frozen_canonical_model_settings() -> None:
    from scripts.run_ragbench_techqa_canonical import GENERATOR_MODEL

    assert GENERATOR_MODEL == "gpt-5.6-luna"
    assert RERANKER_MODEL == "BAAI/bge-reranker-v2-m3"
