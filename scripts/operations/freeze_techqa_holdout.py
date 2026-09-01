"""Freeze the identity of a disjoint TechQA holdout without running RAG."""

# The selection manifest contains deliberately long, human-readable policy strings.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
OUT = ROOT / "artifacts/ragbench/canonical/techqa-holdout50-frozen"
DEBUG_SAMPLE = ROOT / "artifacts/ragbench/canonical/techqa-basic50/sample.json"
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
SEED = 4242
SIZE = 50


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def row_identifier(row: dict[str, Any]) -> str:
    return f"{row['id']}#row-{int(row['_row_index']):04d}"


def unique_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_by_id: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: int(item["_row_index"])):
        first_by_id.setdefault(str(row.get("id", "")), row)
    return sorted(first_by_id.values(), key=lambda item: str(item["id"]))


def mechanically_eligible(row: dict[str, Any], debug_ids: set[str]) -> bool:
    required = ("id", "question", "documents", "documents_sentences")
    return (
        str(row.get("id", ""))
        and str(row.get("id")) not in debug_ids
        and bool(str(row.get("question", "")).strip())
        and all(key in row and row[key] is not None for key in required)
        and isinstance(row.get("documents"), list)
        and isinstance(row.get("documents_sentences"), list)
    )


def freeze() -> dict[str, Any]:
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(DATASET_PATH)
    debug = json.loads(DEBUG_SAMPLE.read_text(encoding="utf-8"))
    if debug.get("sample_hash"):
        raise RuntimeError("DEBUG_SAMPLE_HASH_FIELD_UNEXPECTED")
    debug_ids = set(debug["selected_dataset_ids"])
    rows = pq.read_table(DATASET_PATH).to_pylist()
    for index, row in enumerate(rows):
        row["_row_index"] = index
    candidates = [row for row in unique_candidates(rows) if mechanically_eligible(row, debug_ids)]
    if len(candidates) < SIZE:
        raise RuntimeError(f"HOLDOUT_POOL_TOO_SMALL:{len(candidates)}")
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    selected = candidates[:SIZE]
    selected_ids = [row_identifier(row) for row in selected]
    debug_query_ids = set(debug["selected_query_ids"])
    overlap = sorted(set(selected_ids) & debug_query_ids)
    if overlap:
        raise RuntimeError(f"HOLDOUT_CONTAMINATION:{overlap}")
    if len(set(selected_ids)) != SIZE:
        raise RuntimeError("HOLDOUT_DUPLICATE_IDS")

    schema = list(pq.read_schema(DATASET_PATH).names)
    sample = {
        "dataset": "RAGBench TechQA",
        "repo": "galileo-ai/ragbench",
        "revision": REVISION,
        "split": "test",
        "sample_size": SIZE,
        "selection_seed": SEED,
        "selected_query_ids": selected_ids,
        "selected_dataset_ids": [str(row["id"]) for row in selected],
        "selected_parquet_row_indices": [int(row["_row_index"]) for row in selected],
    }
    selection_rule = {
        "algorithm": "sort unique first-row-per-id candidates; shuffle with random.Random(seed); take first N",
        "seed": SEED,
        "size": SIZE,
        "deduplication": "retain lowest parquet row index per duplicate id",
        "eligibility": [
            "stable id exists",
            "question is non-empty",
            "documents and documents_sentences are present lists",
            "not in DEBUG50",
        ],
        "selection_does_not_use": ["question content", "response", "relevance", "difficulty", "model outputs"],
        "debug_sample_hash": (ROOT / "artifacts/ragbench/canonical/techqa-basic50/sample.sha256").read_text(encoding="utf-8").strip(),
    }
    metadata = {
        "dataset": "RAGBench TechQA",
        "repo": "galileo-ai/ragbench",
        "revision": REVISION,
        "split": "test",
        "source_row_count": len(rows),
        "deduplicated_candidate_count": len(unique_candidates(rows)),
        "eligible_pool_count": len(candidates),
        "schema": schema,
        "source_file": str(DATASET_PATH),
        "source_file_sha256": hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
        "identity_only": True,
    }
    integrity = {
        "debug_count": len(debug_ids),
        "holdout_count": SIZE,
        "intersection_count": 0,
        "duplicate_holdout_ids": 0,
        "holdout_retrieval_calls": 0,
        "holdout_embedding_calls": 0,
        "holdout_reranker_calls": 0,
        "holdout_generation_calls": 0,
        "holdout_judge_calls": 0,
        "holdout_content_inspected_for_tuning": False,
        "sample_hash": canonical_hash(sample),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in (("dataset-metadata.json", metadata), ("selection-rule.json", selection_rule), ("sample-identities.json", sample), ("integrity.json", integrity)):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "sample.sha256").write_text(integrity["sample_hash"] + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# TechQA HOLDOUT50\n\n"
        "This is an identity-only, frozen architecture-verdict set. It was selected mechanically from the pinned test split with seed 4242, disjoint from DEBUG50. No retrieval, embedding, reranking, generation, or judging has been run on it.\n",
        encoding="utf-8",
    )
    return integrity


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
