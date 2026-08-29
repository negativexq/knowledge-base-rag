"""Zero-inference sentence-level retrieval audit for the eManual Basic-50 replay.

This module is deliberately artifact-only.  It must not import the application
retrieval, embedding, reranker, or provider layers: the audit compares the
RAGBench authored relevant-sentence annotations with already persisted replay
snapshots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/ragbench/emanual-basic-50-graceful-budget"
OUT = ROOT / "artifacts/ragbench/emanual-basic-50-semantic-audit"
PARQUET = Path(
    "/Users/ofk/.cache/huggingface/hub/datasets--galileo-ai--ragbench/"
    "snapshots/97808f3e5fd16ede40bbff6c2949af8139b2eb7b/emanual/"
    "test-00000-of-00001.parquet"
)
RAGBENCH_REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
SAMPLE_HASH = "d65d578dcc1f88bb4df71451dfae5f923b2e56bf4fa60e331e6297b2b317cdf3"
CORPUS_FINGERPRINT = "241dae67feae5733026d9a50cf2640979f141b8a7c7c016c5dc8173bfb6f3ae2"
REPLAY_CONFIG = "bba1d9164e5eb36dc056c8b3843e42b175764b542976d83bb5dadf93f9bee8ce"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[\u2010-\u2015\u2212]", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def row_id(row: dict[str, Any]) -> str:
    return f"{row['id']}#row-{int(row['_row_index']):04d}"


def load_rows() -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(PARQUET).to_pylist()
    for index, row in enumerate(rows):
        row["_row_index"] = index
    return sorted(rows, key=lambda row: str(row["id"]))


def relevant_sentence_objects(row: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = [str(key) for key in (row.get("all_relevant_sentence_keys") or [])]
    wanted_set = set(wanted)
    # The pinned parquet has two equivalent key spellings in selected rows
    # (for example ``0b.`` in the annotation and ``0b`` in the sentence
    # table).  This is schema-key punctuation normalization, not text fuzzy
    # matching; the original annotation key is retained in the output.
    by_canonical_key: dict[str, tuple[str, str, int]] = {}
    for document_index, sentences in enumerate(row.get("documents_sentences") or []):
        for key, text in sentences or []:
            key = str(key)
            by_canonical_key[key.rstrip(".")] = (key, str(text), document_index)
    result: list[dict[str, Any]] = []
    for document_index, sentences in enumerate(row.get("documents_sentences") or []):
        for key, text in sentences or []:
            key = str(key)
            if key in wanted_set:
                result.append(
                    {
                        "key": key,
                        "document_index": document_index,
                        "text": str(text),
                        "text_hash": hashlib.sha256(str(text).encode()).hexdigest(),
                    }
                )
    resolved = {item["key"] for item in result}
    for requested_key in wanted:
        if requested_key in resolved:
            continue
        found = by_canonical_key.get(requested_key.rstrip("."))
        if found is not None:
            source_key, text, document_index = found
            result.append(
                {
                    "key": requested_key,
                    "source_sentence_key": source_key,
                    "document_index": document_index,
                    "text": text,
                    "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
    result.sort(key=lambda item: wanted.index(item["key"]) if item["key"] in wanted else 10**9)
    return result


def stage_texts(retrieval: dict[str, Any], stage: str) -> list[str]:
    if stage == "hybrid_top5":
        records = retrieval.get("authorized_top20", [])[:5]
    elif stage == "hybrid_top10":
        records = retrieval.get("authorized_top20", [])[:10]
    elif stage == "hybrid_top20":
        records = retrieval.get("authorized_top20", [])
    elif stage == "bge_top5":
        records = retrieval.get("reranked_top20", [])[:5]
    elif stage == "sectionaware":
        records = retrieval.get("section_aware_blocks", [])
    else:
        raise ValueError(f"unknown stage: {stage}")
    return [str(record.get("text", "")) for record in records]


def sentence_presence(sentences: list[dict[str, Any]], texts: list[str]) -> dict[str, Any]:
    # Joining stage text allows a sentence split by an artifact formatting
    # boundary to be recovered without fuzzy matching.
    haystack = normalize_text("\n".join(texts))
    present = [item["key"] for item in sentences if normalize_text(item["text"]) in haystack]
    keys = [item["key"] for item in sentences]
    return {
        "present_keys": present,
        "missing_keys": [key for key in keys if key not in present],
        "any_present": bool(present),
        "all_present": bool(keys) and len(present) == len(keys),
        "recall": len(present) / len(keys) if keys else None,
    }


def metric_summary(rows: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    values = [
        row["stages"][stage]["recall"]
        for row in rows
        if row["stages"][stage]["recall"] is not None
    ]
    return {
        "query_count": len(rows),
        "any_count": sum(row["stages"][stage]["any_present"] for row in rows),
        "all_count": sum(row["stages"][stage]["all_present"] for row in rows),
        "any_rate": round(sum(row["stages"][stage]["any_present"] for row in rows) / len(rows), 6),
        "all_rate": round(sum(row["stages"][stage]["all_present"] for row in rows) / len(rows), 6),
        "mean_recall": round(statistics.mean(values), 6) if values else None,
        "median_recall": round(statistics.median(values), 6) if values else None,
        "any_display": f"{sum(row['stages'][stage]['any_present'] for row in rows)}/{len(rows)}",
        "all_display": f"{sum(row['stages'][stage]['all_present'] for row in rows)}/{len(rows)}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    sample = read_json(SOURCE / "sample.json")
    observed_sample_hash = sha256_file(SOURCE / "sample.sha256")
    sample_hash_file_value = (SOURCE / "sample.sha256").read_text().strip()
    if sample_hash_file_value != SAMPLE_HASH:
        raise SystemExit(
            f"SOURCE_SAMPLE_MISMATCH expected={SAMPLE_HASH} actual={sample_hash_file_value}"
        )
    if len(sample["selected_query_ids"]) != 50:
        raise SystemExit("SOURCE_SAMPLE_MISMATCH expected=50")

    config = read_json(SOURCE / "config.json")
    corpus = (SOURCE / "corpus-fingerprint.txt").read_text().strip()
    if config.get("config_fingerprint") != REPLAY_CONFIG or corpus != CORPUS_FINGERPRINT:
        raise SystemExit("SOURCE_IDENTITY_MISMATCH")

    rows = load_rows()
    by_id = {row_id(row): row for row in rows}
    selected = [by_id[query_id] for query_id in sample["selected_query_ids"]]
    retrieval_records = read_jsonl(SOURCE / "retrieval-results.jsonl")
    scored_records = read_jsonl(SOURCE / "scored-results.jsonl")
    retrieval_by_id = {str(item["query_id"]): item for item in retrieval_records}
    scored_by_id = {str(item["query_id"]): item for item in scored_records}
    if set(retrieval_by_id) != set(sample["selected_query_ids"]):
        raise SystemExit("SOURCE_IDENTITY_MISMATCH retrieval query set")

    stages = ["hybrid_top5", "hybrid_top10", "hybrid_top20", "bge_top5", "sectionaware"]
    relevant_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    loss_rows: list[dict[str, Any]] = []
    schema_fields = list(selected[0].keys()) if selected else []
    usable_annotations = 0
    resolved_annotations = 0

    for row in selected:
        query_id = row_id(row)
        sentences = relevant_sentence_objects(row)
        keys = [str(key) for key in (row.get("all_relevant_sentence_keys") or [])]
        if keys:
            usable_annotations += 1
        if len(sentences) == len(keys):
            resolved_annotations += 1
        relevant_rows.append(
            {
                "query_id": query_id,
                "question": row["question"],
                "relevant_sentence_keys": keys,
                "relevant_sentences": sentences,
                "annotation_field": "all_relevant_sentence_keys",
                "resolution_complete": len(sentences) == len(keys),
            }
        )
        retrieval = retrieval_by_id[query_id]
        stage_stats = {
            stage: sentence_presence(sentences, stage_texts(retrieval, stage)) for stage in stages
        }
        scored = scored_by_id.get(query_id, {})
        benchmark = scored.get("benchmark", {})
        result_rows.append(
            {
                "query_id": query_id,
                "question": row["question"],
                "relevant_sentence_keys": keys,
                "relevant_sentence_count": len(keys),
                "stages": stage_stats,
                "historical": {
                    "abstained": bool(benchmark.get("abstained", False)),
                    "fully_correct": bool(benchmark.get("fully_correct", False)),
                    "grounded_supported": bool(benchmark.get("grounded_supported", False)),
                    "visible_output": scored.get("visible_output", ""),
                },
                "artifact_coverage": {
                    "top20_records": len(retrieval.get("authorized_top20", [])),
                    "reranked_records": len(retrieval.get("reranked_top20", [])),
                    "sectionaware_blocks": len(retrieval.get("section_aware_blocks", [])),
                },
            }
        )
        if not stage_stats["hybrid_top20"]["all_present"]:
            primary = "MISSING_AT_TOP20"
        elif not stage_stats["bge_top5"]["all_present"]:
            primary = "LOST_TOP20_TO_BGE_TOP5"
        elif not stage_stats["sectionaware"]["all_present"]:
            primary = "LOST_BGE_TOP5_TO_SECTIONAWARE"
        else:
            primary = "ALL_RELEVANT_VISIBLE"
        visibility = (
            "ALL_RELEVANT_VISIBLE"
            if stage_stats["sectionaware"]["all_present"]
            else "PARTIAL_RELEVANT_VISIBLE"
            if stage_stats["sectionaware"]["any_present"]
            else "NO_RELEVANT_VISIBLE"
        )
        transitions = {
            "top20_to_bge_all_loss": stage_stats["hybrid_top20"]["all_present"]
            and not stage_stats["bge_top5"]["all_present"],
            "bge_to_sectionaware_all_loss": stage_stats["bge_top5"]["all_present"]
            and not stage_stats["sectionaware"]["all_present"],
        }
        loss_rows.append(
            {
                "query_id": query_id,
                "question": row["question"],
                "visibility_class": visibility,
                "primary_stage_loss": primary,
                "stage_loss_flags": transitions,
            }
        )

    write_jsonl(out / "relevant-sentences.jsonl", relevant_rows)
    write_jsonl(out / "retrieval-sentence-results.jsonl", result_rows)
    write_jsonl(out / "retrieval-stage-loss.jsonl", loss_rows)

    summary = {
        "schema_version": "ragbench-emanual-sentence-audit-v1",
        "query_count": len(result_rows),
        "annotation_field": "all_relevant_sentence_keys",
        "annotation_resolution": {
            "rows_with_nonempty_annotation": usable_annotations,
            "rows_with_all_keys_resolved": resolved_annotations,
        },
        "stages": {stage: metric_summary(result_rows, stage) for stage in stages},
        "matching": {
            "method": (
                "NFKC/casefold/whitespace/conservative hyphen normalization "
                "plus deterministic containment"
            ),
            "fuzzy_matching": False,
            "embedding_or_reranker_inference": False,
        },
    }
    write_json(out / "retrieval-sentence-summary.json", summary)
    write_json(
        out / "retrieval-stage-loss-summary.json",
        {
            "query_count": len(loss_rows),
            "primary_stage_loss_counts": dict(
                sorted(
                    {key: sum(row["primary_stage_loss"] == key for row in loss_rows) for key in {
                        row["primary_stage_loss"] for row in loss_rows
                    }}.items()
                )
            ),
            "visibility_class_counts": dict(
                sorted(
                    {key: sum(row["visibility_class"] == key for row in loss_rows) for key in {
                        row["visibility_class"] for row in loss_rows
                    }}.items()
                )
            ),
            "transition_counts": {
                "top20_to_bge_all_loss": sum(
                    row["stage_loss_flags"]["top20_to_bge_all_loss"] for row in loss_rows
                ),
                "bge_to_sectionaware_all_loss": sum(
                    row["stage_loss_flags"]["bge_to_sectionaware_all_loss"] for row in loss_rows
                ),
            },
        },
    )

    write_json(
        out / "ragbench-relevance-schema.json",
        {
            "dataset": "galileo-ai/ragbench",
            "revision": RAGBENCH_REVISION,
            "split": "test",
            "parquet": str(PARQUET),
            "selected_row_count": len(selected),
            "fields": schema_fields,
            "relevance_fields": {
                "primary": "all_relevant_sentence_keys",
                "sentence_lookup": "documents_sentences",
                "related_fields": ["all_utilized_sentence_keys", "sentence_support_information"],
            },
            "observed_types": {
                "all_relevant_sentence_keys": (
                    type(selected[0].get("all_relevant_sentence_keys")).__name__
                )
                if selected
                else None,
                "documents_sentences": type(selected[0].get("documents_sentences")).__name__
                if selected
                else None,
            },
            "usable_rows": usable_annotations,
            "fully_resolved_rows": resolved_annotations,
            "resolution_rule": (
                "key equality against documents_sentences; "
                "no fuzzy or semantic matching"
            ),
        },
    )
    write_json(
        out / "source-integrity.json",
        {
            "source_run": str(SOURCE),
            "dataset_revision": RAGBENCH_REVISION,
            "sample_hash_expected": SAMPLE_HASH,
            "sample_hash_file_observed": sample_hash_file_value,
            "sample_sha256_file_observed": observed_sample_hash,
            "sample_size": len(sample["selected_query_ids"]),
            "corpus_fingerprint_expected": CORPUS_FINGERPRINT,
            "corpus_fingerprint_observed": corpus,
            "replay_config_expected": REPLAY_CONFIG,
            "replay_config_observed": config.get("config_fingerprint"),
            "retrieval_artifact_count": len(retrieval_records),
            "scored_artifact_count": len(scored_records),
            "zero_inference": {
                "openai_calls": 0,
                "ollama_calls": 0,
                "generation_calls": 0,
                "retrieval_calls": 0,
                "embedding_calls": 0,
                "reranker_calls": 0,
            },
            "historical_artifacts_modified": False,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
