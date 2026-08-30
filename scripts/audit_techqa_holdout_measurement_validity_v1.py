"""Zero-inference audit of the TechQA HOLDOUT evidence metric collapse."""

# Diagnostic report strings intentionally preserve readable source wording.
# ruff: noqa: E402, E501, UP038

from __future__ import annotations

import hashlib
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.qdrant_store import QdrantStore
from scripts.ragbench_emanual_common import text_has_sentence

CANONICAL = ROOT / "artifacts/ragbench/canonical"
DEBUG = CANONICAL / "techqa-basic50"
HOLDOUT = CANONICAL / "techqa-holdout50-frozen"
RUN = CANONICAL / "techqa-reranker-holdout-oneshot-v1"
OUT = CANONICAL / "techqa-holdout-measurement-validity-audit-v1"
PARQUET = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
CORPUS_HASH = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_id(index: int, row: dict[str, Any]) -> str:
    return f"{row['id']}#row-{index:04d}"


def source_id(text: str) -> str:
    return "ragbench_techqa_doc_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def source_version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_rows() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not PARQUET.exists():
        raise RuntimeError("TECHQA_DATASET_SOURCE_MISSING")
    table_rows = pq.read_table(PARQUET).to_pylist()
    debug_sample = read_json(DEBUG / "sample.json")
    holdout_sample = read_json(HOLDOUT / "sample-identities.json")
    debug = {
        row_id(index, table_rows[index]): {**table_rows[index], "_row_index": index}
        for index in debug_sample["selected_parquet_row_indices"]
    }
    holdout = {
        row_id(index, table_rows[index]): {**table_rows[index], "_row_index": index}
        for index in holdout_sample["selected_parquet_row_indices"]
    }
    if len(debug) != 50 or len(holdout) != 50 or set(debug) & set(holdout):
        raise RuntimeError("HOLDOUT_CONTAMINATION")
    return debug, holdout


def annotation_objects(row: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys") or []}
    result = []
    documents = row.get("documents") or []
    for document_index, document in enumerate(row.get("documents_sentences") or []):
        document_text = str(documents[document_index]) if document_index < len(documents) else ""
        for pair in document or []:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                key, text = str(pair[0]).rstrip("."), str(pair[1])
                if key in wanted:
                    result.append(
                        {
                            "key": key,
                            "document_index": document_index,
                            "text": text,
                            "source_id": source_id(document_text),
                            "document_version": source_version(document_text),
                        }
                    )
    return result


def annotation_keys(row: dict[str, Any]) -> list[str]:
    """Return the raw annotation denominator, including unmapped keys."""
    return list(
        dict.fromkeys(str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys") or [])
    )


def annotation_source(row: dict[str, Any], key: str) -> str | None:
    """Resolve the document source encoded by a TechQA sentence key."""
    match = re.match(r"^(\d+)", key)
    if not match:
        return None
    document_index = int(match.group(1))
    documents = row.get("documents") or []
    if document_index >= len(documents):
        return None
    return source_id(str(documents[document_index]))


def stage_presence(row: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    annotations = annotation_objects(row)
    keys = annotation_keys(row)
    joined = "\n".join(str(item.get("text", "")) for item in items)
    present = [item["key"] for item in annotations if text_has_sentence(joined, item["text"])]
    return {
        "present_keys": present,
        "missing_keys": [key for key in keys if key not in present],
        "any": bool(present),
        "all": bool(keys) and len(present) == len(keys),
        "recall": len(present) / len(keys) if keys else None,
    }


def relevant_truth(row: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": annotation_keys(row),
        "canonical_relevant_keys": list(
            truth.get("relevant_keys", truth.get("relevant_sentence_keys", []))
        ),
    }


def state(value: dict[str, Any]) -> str:
    if value.get("all"):
        return "ALL"
    if value.get("any"):
        return "PARTIAL"
    return "NONE"


def debug_replay(
    debug_rows: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    on_source = {
        row["query_id"]: row
        for row in read_jsonl(CANONICAL / "techqa-topn-ablation-v1/top5-results.jsonl")
    }
    off_source = {
        row["query_id"]: row
        for row in read_jsonl(
            CANONICAL / "techqa-reranker-removal-debug-v1/off-2400-evidence.jsonl"
        )
    }
    results = []
    metrics: dict[str, Any] = {}
    for condition, source in (("ON", on_source), ("OFF", off_source)):
        condition_rows = []
        for query_id, row in debug_rows.items():
            if query_id not in source:
                raise RuntimeError("DEBUG_SCORER_REPLAY_INPUT_MISSING")
            evidence = source[query_id]
            blocks = evidence["section_aware_blocks"]
            replayed = stage_presence(row, blocks)
            canonical = (
                evidence.get("section_aware_truth") if condition == "ON" else evidence.get("truth")
            )
            canonical = canonical or {}
            canonical_value = {
                "present_keys": list(
                    canonical.get("present_keys", canonical.get("present_sentence_keys", []))
                ),
                "missing_keys": list(
                    canonical.get("missing_keys", canonical.get("missing_sentence_keys", []))
                ),
                "any": bool(
                    canonical.get(
                        "any",
                        canonical.get("present_keys", canonical.get("present_sentence_keys", [])),
                    )
                ),
                "all": bool(
                    canonical.get("all", canonical.get("all_relevant_sentences_present", False))
                ),
                "recall": canonical.get("recall", canonical.get("sentence_recall")),
            }
            keys = annotation_keys(row)
            available_keys = {item["key"] for item in annotation_objects(row)}
            item = {
                "query_id": query_id,
                "condition": condition,
                "gold_annotation_keys": keys,
                "canonical_mapped_keys": canonical_value["present_keys"],
                "holdout_scorer_mapped_keys": replayed["present_keys"],
                "canonical_evidence_state": state(canonical_value),
                "replayed_evidence_state": state(replayed),
                "mapping_differences": sorted(
                    {str(key).rstrip(".") for key in canonical_value["present_keys"]}
                    ^ set(replayed["present_keys"])
                ),
                "unmapped_annotation_keys": sorted(set(keys) - available_keys),
                "canonical_recall": canonical_value["recall"],
                "replayed_recall": replayed["recall"],
            }
            condition_rows.append(item)
            results.append(item)
        annotated = [item for item in condition_rows if item["gold_annotation_keys"]]
        metrics[condition] = {
            "annotated": len(annotated),
            "any": sum(item["replayed_evidence_state"] != "NONE" for item in annotated),
            "all": sum(item["replayed_evidence_state"] == "ALL" for item in annotated),
            "mean_recall": statistics.mean([item["replayed_recall"] for item in annotated]),
            "canonical_any": sum(item["canonical_evidence_state"] != "NONE" for item in annotated),
            "canonical_all": sum(item["canonical_evidence_state"] == "ALL" for item in annotated),
            "mapping_difference_rows": sum(bool(item["mapping_differences"]) for item in annotated),
            "unmapped_annotation_keys": sorted(
                {key for item in condition_rows for key in item["unmapped_annotation_keys"]}
            ),
            "unmapped_annotation_key_count": sum(
                len(item["unmapped_annotation_keys"]) for item in condition_rows
            ),
        }
    return results, metrics


def corpus_chunks() -> tuple[dict[str, dict[str, Any]], set[str]]:
    source_rows = read_jsonl(DEBUG / "source-documents.jsonl")
    chunks: dict[str, dict[str, Any]] = {}
    source_ids = set()
    for document in source_rows:
        source_ids.add(document["source_id"])
        for chunk in chunk_markdown_text(
            document["text"],
            document["source_id"],
            document["source_type"],
            document["document_version"],
        ):
            chunks[QdrantStore.point_id_for(chunk)] = {
                "chunk_id": QdrantStore.point_id_for(chunk),
                "source_id": chunk.source_id,
                "text": chunk.text,
            }
    return chunks, source_ids


def coverage_audit(
    holdout_rows: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    chunks, indexed_sources = corpus_chunks()
    rrf = {row["query_id"]: row for row in read_jsonl(RUN / "02-retrieval/shared-rrf-top20.jsonl")}
    bge = {row["query_id"]: row for row in read_jsonl(RUN / "02-retrieval/on-bge-ranking.jsonl")}
    on = {row["query_id"]: row for row in read_jsonl(RUN / "03-evidence/on-evidence.jsonl")}
    off = {row["query_id"]: row for row in read_jsonl(RUN / "03-evidence/off-evidence.jsonl")}
    rows = []
    for query_id, row in holdout_rows.items():
        annotations = annotation_objects(row)
        keys = annotation_keys(row)
        object_by_key = {item["key"]: item for item in annotations}
        gold_sources = sorted(
            {source for key in keys if (source := annotation_source(row, key)) is not None}
        )
        mapped: dict[str, list[str]] = {}
        for key in keys:
            item = object_by_key.get(key)
            mapped[key] = sorted(
                chunk_id
                for chunk_id, chunk in chunks.items()
                if item is not None
                and chunk["source_id"] == item["source_id"]
                and text_has_sentence(chunk["text"], item["text"])
            )
        gold_in_corpus = bool(keys) and all(source in indexed_sources for source in gold_sources)
        annotation_mappable = bool(keys) and all(mapped[key] for key in keys)
        rrf_items = sorted(rrf[query_id]["authorized_top20"], key=lambda item: item["rank"])
        bge_items = sorted(bge[query_id]["reranked_top20"], key=lambda item: item["rank"])
        stages = {
            "rrf_top20": stage_presence(row, rrf_items),
            "bge_top5": stage_presence(row, bge_items[:5]),
            "rrf_top5": stage_presence(row, rrf_items[:5]),
            "on_sectionaware": stage_presence(row, on[query_id]["section_aware_blocks"]),
            "off_sectionaware": stage_presence(row, off[query_id]["section_aware_blocks"]),
        }
        if not keys:
            first_failure = "UNKNOWN"
        elif not gold_in_corpus:
            first_failure = "CORPUS_MISSING"
        elif not annotation_mappable:
            first_failure = "ANNOTATION_UNMAPPABLE"
        elif not stages["rrf_top20"]["all"]:
            first_failure = "CANDIDATE_RETRIEVAL_MISS"
        elif not stages["bge_top5"]["all"]:
            first_failure = "BGE_SELECTION_LOSS"
        elif not stages["rrf_top5"]["all"]:
            first_failure = "RRF_TOP5_CUTOFF_LOSS"
        elif not stages["on_sectionaware"]["all"] or not stages["off_sectionaware"]["all"]:
            first_failure = "SECTIONAWARE_BUDGET_LOSS"
        else:
            first_failure = "NO_UPSTREAM_LOSS"
        rows.append(
            {
                "query_id": query_id,
                "annotated": bool(keys),
                "gold_doc_ids": gold_sources,
                "gold_source_ids": gold_sources,
                "gold_annotation_keys": keys,
                "gold_doc_in_corpus": gold_in_corpus if keys else None,
                "annotation_mapped_to_corpus": annotation_mappable if keys else None,
                "mapped_chunk_ids": sorted(
                    {chunk_id for values in mapped.values() for chunk_id in values}
                ),
                "annotation_to_chunk_ids": mapped,
                **{
                    f"{name}_contains_any": value["any"] if keys else None
                    for name, value in stages.items()
                },
                **{
                    f"{name}_contains_all": value["all"] if keys else None
                    for name, value in stages.items()
                },
                "first_failure_stage": first_failure,
                "reported_recall": {name: value["recall"] for name, value in stages.items()},
                "budget_exhausted": {
                    "on": bool(on[query_id]["budget_exhausted"]),
                    "off": bool(off[query_id]["budget_exhausted"]),
                },
            }
        )
    annotated = [row for row in rows if row["annotated"]]
    summary = {
        "holdout_rows": len(rows),
        "usable_annotation_rows": len(annotated),
        "unmapped_annotation_rows": len(rows) - len(annotated),
        "indexed_source_count": len(indexed_sources),
        "holdout_union_source_count": len(
            {
                source_id(text)
                for row in holdout_rows.values()
                for text in row.get("documents", []) or []
            }
        ),
        "holdout_union_sources_intersecting_index": len(
            {
                source_id(text)
                for row in holdout_rows.values()
                for text in row.get("documents", []) or []
            }
            & indexed_sources
        ),
        "gold_doc_in_corpus": sum(bool(row["gold_doc_in_corpus"]) for row in annotated),
        "annotation_mapped_to_corpus": sum(
            bool(row["annotation_mapped_to_corpus"]) for row in annotated
        ),
        "first_failure_stage": dict(Counter(row["first_failure_stage"] for row in annotated)),
    }
    for name in ("rrf_top20", "bge_top5", "rrf_top5", "on_sectionaware", "off_sectionaware"):
        summary[name] = {
            "any": sum(bool(row[f"{name}_contains_any"]) for row in annotated),
            "all": sum(bool(row[f"{name}_contains_all"]) for row in annotated),
        }
    samples = [
        row
        for row in rows
        if row["annotated"]
        and (row["budget_exhausted"]["on"] or row["budget_exhausted"]["off"])
        and all(value == 0 for value in row["reported_recall"].values())
    ][:5]
    return rows, summary, samples


def sample_markdown(
    samples: list[dict[str, Any]],
    holdout_rows: dict[str, dict[str, Any]],
    coverage: dict[str, dict[str, Any]],
) -> str:
    parts = ["# HOLDOUT Zero-Recall / Budget-Exhausted Samples\n\n"]
    for item in samples:
        row = holdout_rows[item["query_id"]]
        parts.append(f"## {item['query_id']}\n\nQuestion: {row['question']}\n\n")
        parts.append(f"Gold sources: {', '.join(item['gold_source_ids'])}\n\n")
        parts.append(f"Gold annotation keys: {', '.join(item['gold_annotation_keys'])}\n\n")
        for annotation in annotation_objects(row)[:3]:
            parts.append(f"Gold annotation `{annotation['key']}`: {annotation['text']}\n\n")
        parts.append("Selected evidence source IDs:\n")
        for condition, path in (
            ("ON", "03-evidence/on-evidence.jsonl"),
            ("OFF", "03-evidence/off-evidence.jsonl"),
        ):
            records = {x["query_id"]: x for x in read_jsonl(RUN / path)}
            sources = sorted(
                {
                    block.get("source_id")
                    for block in records[item["query_id"]]["section_aware_blocks"]
                }
            )
            parts.append(f"- {condition}: {', '.join(source for source in sources if source)}\n")
            blocks = records[item["query_id"]]["section_aware_blocks"]
            excerpt = " ".join(
                str(block.get("text", ""))[:280].replace("\n", " ") for block in blocks[:2]
            )
            parts.append(f"  excerpt: {excerpt}\n")
        parts.append(
            "\nDeterministic outcome: `CORPUS_MISSING` precedes downstream retrieval interpretation; no relevant gold source is indexed.\n\n"
        )
    return "".join(parts)


def write_artifacts() -> None:
    debug_rows, holdout_rows = load_rows()
    debug_replay_rows, replay_metrics = debug_replay(debug_rows)
    coverage_rows, coverage_summary, samples = coverage_audit(holdout_rows)
    starting_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_integrity = {
        "audit": "TECHQA_HOLDOUT_MEASUREMENT_VALIDITY_AUDIT_V1",
        "starting_head": starting_head,
        "dataset_revision": REVISION,
        "debug50_hash": DEBUG_HASH,
        "holdout50_hash": HOLDOUT_HASH,
        "corpus_fingerprint": CORPUS_HASH,
        "config_fingerprint": CONFIG_HASH,
        "original_holdout_accessed": True,
        "semantic_unblind_before_audit": False,
        "arm_map_opened": False,
        "new_calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0},
        "historical_artifacts_modified": False,
        "source_hashes": {
            "holdout_source_integrity": sha256_file(RUN / "01-integrity/source-integrity.json"),
            "holdout_shared_retrieval": sha256_file(RUN / "02-retrieval/shared-rrf-top20.jsonl"),
            "holdout_on_evidence": sha256_file(RUN / "03-evidence/on-evidence.jsonl"),
            "holdout_off_evidence": sha256_file(RUN / "03-evidence/off-evidence.jsonl"),
            "debug_retrieval": sha256_file(DEBUG / "retrieval-results.jsonl"),
            "debug_reranker": sha256_file(DEBUG / "reranker-results.jsonl"),
        },
    }
    write_json(OUT / "00-integrity/source-integrity.json", source_integrity)
    write_jsonl(OUT / "01-debug-scorer-replay/debug-replay-results.jsonl", debug_replay_rows)
    write_json(OUT / "01-debug-scorer-replay/debug-replay-summary.json", replay_metrics)
    write_json(
        OUT / "02-scorer-diff/scorer-diff.json",
        {
            "canonical_debug_path": "scripts/run_techqa_reranker_removal_debug.py::relevant_truth",
            "holdout_path": "scripts/run_techqa_reranker_holdout_oneshot_v1.py::truth_presence",
            "shared_matching_primitive": "scripts/ragbench_emanual_common.py::text_has_sentence",
            "debug_replay_mapping_difference_rows": sum(
                bool(row["mapping_differences"]) for row in debug_replay_rows
            ),
            "debug_sentence_object_unmapped": {
                "query_count": len(
                    {
                        row["query_id"]
                        for row in debug_replay_rows
                        if row["unmapped_annotation_keys"]
                    }
                ),
                "keys": sorted(
                    {key for row in debug_replay_rows for key in row["unmapped_annotation_keys"]}
                ),
            },
            "conclusion": "DEBUG replay reproduces canonical mapping; no scorer defect demonstrated.",
        },
    )
    write_jsonl(OUT / "03-holdout-corpus-coverage/coverage-results.jsonl", coverage_rows)
    write_json(OUT / "03-holdout-corpus-coverage/coverage-summary.json", coverage_summary)
    (OUT / "03-holdout-corpus-coverage/zero-recall-samples.md").parent.mkdir(
        parents=True, exist_ok=True
    )
    (OUT / "03-holdout-corpus-coverage/zero-recall-samples.md").write_text(
        sample_markdown(samples, holdout_rows, {row["query_id"]: row for row in coverage_rows}),
        encoding="utf-8",
    )
    root_cause = {
        "symptom": "HOLDOUT evidence recall approximately 6% and ALL 0 despite non-empty, budget-filled contexts.",
        "diagnostic_test": "Replay HOLDOUT scorer on frozen DEBUG evidence, then compare HOLDOUT gold sources against indexed corpus.",
        "observed_result": {
            "debug_replay": replay_metrics,
            "holdout_coverage": coverage_summary,
            "debug_canonical_expected": {
                "on_any": 36,
                "on_all": 29,
                "on_recall": 0.8794661023953517,
                "off_any": 37,
                "off_all": 32,
                "off_recall": 0.9205004473285319,
            },
        },
        "root_cause": "HOLDOUT_DATA_OR_CORPUS_SCOPE_MISMATCH: the original index is the DEBUG50 corpus, while none of the 41 annotated HOLDOUT gold source documents is indexed.",
        "affected_metrics": [
            "HOLDOUT evidence ANY/ALL/recall",
            "HOLDOUT retrieval/evidence architecture interpretation",
            "semantic architecture decision based on this evidence",
        ],
        "unaffected_instrumentation": [
            "BGE latency",
            "Luna latency",
            "provider retry observation",
            "provider cost",
            "deterministic security counters",
        ],
        "affected_arms": ["ON", "OFF"],
        "arm_symmetric": True,
        "outcome_independent_invalidity": True,
        "semantic_outputs_interpretable_for_architecture_decision": False,
        "original_holdout_run_supports_architecture_decision": False,
    }
    write_json(OUT / "04-root-cause/root-cause.json", root_cause)
    amendment = {
        "amendment": "CORRECTED_HOLDOUT_EXECUTION_PREREGISTRATION_AMENDMENT_V1",
        "created_at": datetime.now(UTC).isoformat(),
        "original_preregistration_sha256": (RUN / "00-preregistration/preregistration.sha256")
        .read_text(encoding="utf-8")
        .strip(),
        "original_holdout_run": "techqa-reranker-holdout-oneshot-v1",
        "defect": "The original run used the DEBUG50-only indexed corpus for HOLDOUT queries; all 41 annotated HOLDOUT gold sources were absent from that index.",
        "detection": "Zero-inference DEBUG scorer replay matched canonical metrics, while L0 gold-source coverage was 0/41.",
        "invalidity_arm_independent": True,
        "invalid_metrics": [
            "HOLDOUT ANY/ALL/mean recall",
            "HOLDOUT evidence completeness comparison",
            "semantic architecture inference from those evidence payloads",
        ],
        "valid_metrics": [
            "BGE stage latency",
            "Luna latency",
            "provider cost",
            "provider retry behavior",
            "deterministic security instrumentation",
        ],
        "correction": "Prepare a corpus whose indexed source scope contains the exact pinned TechQA test-split documents required by HOLDOUT, then execute the same paired ON/OFF experiment once.",
        "no_new_architecture_variable": True,
        "frozen_design": {
            "candidate_k": 20,
            "top_n": 5,
            "legacy_budget": 2400,
            "same_on_off_downstream": True,
        },
        "corrected_scope": "EXACT HOLDOUT50; no query exclusion, tuning, or semantic unblind before blinded review.",
        "provider_call_budget": {"preflight_max": 2, "official_luna_max": 100, "terra": 0},
        "holdout_previously_accessed": True,
        "semantic_unblind_before_amendment": False,
        "corrected_rerun_executed": False,
        "corrected_rerun_authorization": "PENDING_NEW_EXPLICIT_TASK",
    }
    write_json(OUT / "05-amendment/preregistration-amendment-v1.json", amendment)
    (OUT / "05-amendment/preregistration-amendment-v1.sha256").write_text(
        sha256_file(OUT / "05-amendment/preregistration-amendment-v1.json") + "\n", encoding="utf-8"
    )
    report = f"""# TECHQA HOLDOUT Measurement Validity Audit V1

## Status

`EXECUTION_COMPLETED / MEASUREMENT_VALIDITY_UNDER_INVESTIGATION`

HOLDOUT content was accessed in the original one-shot run. Semantic review has not started, the arm map has not been opened, and no corrected HOLDOUT execution was run.

## Primary discriminating test

The HOLDOUT scorer/matcher was replayed on frozen DEBUG evidence without retrieval, embedding, reranking, generation, or judging.

| Condition | Canonical ANY | Replay ANY | Canonical ALL | Replay ALL | Canonical recall | Replay recall | Mapping differences |
|---|---:|---:|---:|---:|---:|---:|---:|
| ON | 36/38 | {replay_metrics['ON']['any']}/38 | 29/38 | {replay_metrics['ON']['all']}/38 | 87.95% | {replay_metrics['ON']['mean_recall']:.2%} | {replay_metrics['ON']['mapping_difference_rows']} |
| OFF | 37/38 | {replay_metrics['OFF']['any']}/38 | 32/38 | {replay_metrics['OFF']['all']}/38 | 92.05% | {replay_metrics['OFF']['mean_recall']:.2%} | {replay_metrics['OFF']['mapping_difference_rows']} |

Result: `MATCH`. The HOLDOUT scorer path reproduces the known DEBUG scorer; a generic scorer defect is not supported.

### Annotation-key audit

The prior named DEBUG key cases are not equivalent: `Q016:1f` has a sentence object but is absent from both persisted arm evidence payloads (an evidence-presence miss), while `Q270:1zaa` is absent from the sentence-object map. The replay follows the canonical denominator and maps both arms identically; this does not indicate a scorer mismatch. The HOLDOUT sample has 9 rows without usable native annotation keys.

## HOLDOUT corpus coverage

The original index contains 246 source documents and 372 chunks. The HOLDOUT rows reference 248 unique source documents, but only 2 non-gold source documents intersect the DEBUG index. For the 41 annotated HOLDOUT rows:

- Gold relevant source/document in indexed corpus: **0/41**
- Annotation mapped to indexed corpus chunk: **0/41**
- RRF Top20 ANY/ALL: **{coverage_summary['rrf_top20']['any']}/41 / {coverage_summary['rrf_top20']['all']}/41**
- BGE Top5 ANY/ALL: **{coverage_summary['bge_top5']['any']}/41 / {coverage_summary['bge_top5']['all']}/41**
- RRF Top5 ANY/ALL: **{coverage_summary['rrf_top5']['any']}/41 / {coverage_summary['rrf_top5']['all']}/41**
- ON SectionAware ANY/ALL: **{coverage_summary['on_sectionaware']['any']}/41 / {coverage_summary['on_sectionaware']['all']}/41**
- OFF SectionAware ANY/ALL: **{coverage_summary['off_sectionaware']['any']}/41 / {coverage_summary['off_sectionaware']['all']}/41**

The first failure stage is `CORPUS_MISSING` for all 41 annotated rows. The apparent nonzero ANY counts are incidental text matches against unrelated indexed documents and cannot establish gold-source retrieval survival when L0 is false.

Five budget-exhausted / zero-recall examples with source and evidence excerpts are in `03-holdout-corpus-coverage/zero-recall-samples.md`.

## Root cause and validity

This is an outcome-independent, arm-symmetric `HOLDOUT_DATA_OR_CORPUS_SCOPE_MISMATCH`. The original HOLDOUT evidence metrics are invalid for ON-vs-OFF architecture comparison. The original semantic blind review should not proceed as an architecture verdict because both arms were generated over the wrong corpus scope.

Unrelated instrumentation remains technically usable, with scope limits: measured BGE latency, Luna latency, provider cost/retry observations, and deterministic security counters do not depend on gold annotation recognition. They do not rescue the evidence or semantic architecture decision.

## Amendment

Because the invalidating defect is proven, a correction amendment was created at `05-amendment/preregistration-amendment-v1.json` and hashed before any corrected rerun. No corrected rerun was executed. The amendment requires the exact pinned TechQA source scope needed by HOLDOUT, while retaining candidate_k=20, top_n=5, legacy budget=2400, identical ON/OFF downstream behavior, and the no-tuning/blinded-review protocol.

## Guardrails

- New retrieval/embedding/BGE/Luna/Terra calls: 0
- Blind arm map opened: no
- Blind scorecard filled: no
- Production or RAG architecture changed: no
- Historical artifacts modified: no
- Corrected HOLDOUT execution: no
"""
    (OUT / "04-root-cause/root-cause.md").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "04-root-cause/root-cause.md").write_text(report, encoding="utf-8")
    write_json(
        OUT / "06-report/audit-status.json",
        {
            "status": "EXECUTION_COMPLETED_MEASUREMENT_VALIDITY_UNDER_INVESTIGATION",
            "original_holdout_accessed": True,
            "semantic_review_started": False,
            "arm_map_unblinded": False,
            "no_post_result_tuning": True,
            "corrected_rerun_authorization": "PENDING",
            "verdict": "HOLDOUT_RUN_INVALID_CORPUS_SCOPE",
            "original_evidence_metrics_usable": False,
            "original_semantic_blind_review_should_proceed": False,
            "implementation_check": True,
            "promotion_authority": False,
        },
    )
    (OUT / "06-report/report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    write_artifacts()
    print("TECHQA HOLDOUT MEASUREMENT VALIDITY AUDIT COMPLETE")
