# ruff: noqa: E501
"""Artifact-only TechQA BGE Top-N ablation.

The runner reuses the persisted Hybrid Top20 and BGE-ranked Top20 records.  It
never calls a provider, retrieval backend, embedding model, or reranker.  The
only replayed application step is SectionAware evidence assembly at the fixed
2400-word budget.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.evidence.section_aware import SectionAwareEvidenceBuilder, serialize_section_aware_context
from app.evidence.support_units import SupportUnit, build_support_units, serialize_support_units
from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.qdrant_store import QdrantStore
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext
from scripts.benchmarks.ragbench_emanual_common import (
    deserialize_result,
    serialize_result,
    text_has_sentence,
)

ROOT = Path(__file__).resolve().parents[2]
DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
PHASE0 = ROOT / "artifacts/ragbench/canonical/techqa-phase0-forensics"
BUDGET_ABLATION = ROOT / "artifacts/ragbench/canonical/techqa-evidence-budget-ablation-v1"
HOLDOUT = ROOT / "artifacts/ragbench/canonical/techqa-holdout50-frozen"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-topn-ablation-v1"
PREREG = OUT / "preregistration.json"
TOP_N_VALUES = (5, 8, 12)
EVIDENCE_BUDGET = 2400
ANNOTATED_SIZE = 38
DEBUG_SIZE = 50
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
CORPUS_HASH = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_integrity(
    config: dict[str, Any],
    retrieval: dict[str, dict[str, Any]],
    reranker: dict[str, dict[str, Any]],
    annotated: list[str],
) -> dict[str, Any]:
    return {
        "dataset": config["dataset"],
        "revision": REVISION,
        "split": config["split"],
        "debug50_hash": DEBUG_HASH,
        "holdout50_hash": HOLDOUT_HASH,
        "config_fingerprint": CONFIG_HASH,
        "corpus_fingerprint": CORPUS_HASH,
        "debug_query_count": len(retrieval),
        "annotated_population_size": len(annotated),
        "retrieval_rows": len(retrieval),
        "reranker_rows": len(reranker),
        "holdout_intersection_count": 0,
        "bge_model": config["reranker"]["model"],
        "bge_rank_order_verified": True,
        "calls": {
            "retrieval": 0,
            "embedding": 0,
            "reranker": 0,
            "openai": 0,
            "ollama": 0,
            "luna": 0,
            "terra": 0,
        },
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def load_questions() -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    parquet = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
    if not parquet.exists():
        raise RuntimeError("TECHQA_DATASET_SOURCE_MISSING")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(pq.read_table(parquet).to_pylist()):
        dataset_id = str(row["id"])
        if dataset_id in result:
            continue
        sentences = []
        for doc_index, doc in enumerate(row.get("documents_sentences") or []):
            for pair in doc or []:
                if isinstance(pair, list | tuple) and len(pair) == 2:
                    sentences.append(
                        {"key": str(pair[0]), "document_index": doc_index, "text": str(pair[1])}
                    )
        keys = {str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys") or []}
        query_id = f"{dataset_id}#row-{index:04d}"
        result[query_id] = {
            "question": str(row["question"]),
            "relevant": [item for item in sentences if item["key"].rstrip(".") in keys],
        }
    return result


class OfflineQdrant:
    """Scroll-only corpus lookup; deliberately exposes no retrieval method."""

    def __init__(self, chunks: dict[str, SearchResult]) -> None:
        self.chunks = chunks

    def scroll(self, *, scroll_filter: Any, **_: Any) -> tuple[list[Any], None]:
        conditions = getattr(scroll_filter, "must", []) or []
        wanted: dict[str, Any] = {}
        for condition in conditions:
            key = getattr(condition, "key", None)
            match = getattr(condition, "match", None)
            if key and match is not None and hasattr(match, "value"):
                wanted[key] = match.value
        points = []
        for item in self.chunks.values():
            if all(item.payload.get(key) == value for key, value in wanted.items()):
                points.append(SimpleNamespace(id=item.id, payload=dict(item.payload)))
        return points, None


def source_chunks() -> dict[str, SearchResult]:
    result: dict[str, SearchResult] = {}
    for document in read_jsonl(DEBUG / "source-documents.jsonl"):
        chunks = chunk_markdown_text(
            document["text"],
            document["source_id"],
            document["source_type"],
            document["document_version"],
        )
        for chunk in chunks:
            chunk = replace(chunk, tenant_id=document["tenant_id"])
            result[QdrantStore.point_id_for(chunk)] = SearchResult(
                score=0.0, id=QdrantStore.point_id_for(chunk), payload=dict(chunk.__dict__)
            )
    return result


def frozen_rows() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    retrieval_rows = {row["query_id"]: row for row in read_jsonl(DEBUG / "retrieval-results.jsonl")}
    reranker_rows = {row["query_id"]: row for row in read_jsonl(DEBUG / "reranker-results.jsonl")}
    if len(retrieval_rows) != DEBUG_SIZE or len(reranker_rows) != DEBUG_SIZE:
        raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
    for query_id, row in retrieval_rows.items():
        ranked = row.get("reranked_top20") or []
        persisted = reranker_rows.get(query_id, {}).get("reranked_top20") or []
        if len(ranked) != 20 or len(persisted) != 20:
            raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
        retrieval_ids = [item["chunk_id"] for item in ranked]
        persisted_ids = [
            item["chunk_id"] for item in sorted(persisted, key=lambda item: item["rank"])
        ]
        if retrieval_ids != persisted_ids or [item["rank"] for item in persisted] != list(
            range(1, 21)
        ):
            raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
        selected = reranker_rows[query_id].get("selected_top5") or []
        if [item["chunk_id"] for item in selected] != persisted_ids[:5]:
            raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
    return retrieval_rows, reranker_rows


def validate_sources() -> (
    tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]
):
    config = read_json(DEBUG / "config.json")
    holdout_integrity = read_json(HOLDOUT / "integrity.json")
    holdout_ids = set(read_json(HOLDOUT / "sample-identities.json")["selected_query_ids"])
    retrieval, reranker = frozen_rows()
    debug_ids = set(retrieval)
    if (DEBUG / "sample.sha256").read_text(encoding="utf-8").strip() != DEBUG_HASH:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if config.get("dataset_revision") != REVISION or config.get("sample_hash") != DEBUG_HASH:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if (
        config.get("config_fingerprint") != CONFIG_HASH
        or config.get("corpus_fingerprint") != CORPUS_HASH
    ):
        raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
    if (
        holdout_integrity.get("sample_hash") != HOLDOUT_HASH
        or holdout_integrity.get("holdout_count") != 50
    ):
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if debug_ids & holdout_ids or holdout_integrity.get("intersection_count") != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATION")
    if config.get("reranker", {}).get("model") != RERANKER_MODEL:
        raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
    return retrieval, reranker, config


def annotated_ids(retrieval: dict[str, dict[str, Any]]) -> list[str]:
    ids = sorted(
        query_id
        for query_id, row in retrieval.items()
        if row.get("truth", {}).get("section_aware", {}).get("annotated")
    )
    if len(ids) != ANNOTATED_SIZE:
        raise RuntimeError("ANNOTATED_POPULATION_MISMATCH")
    return ids


def select_persisted_anchors(ranked: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    if top_n <= 0 or top_n > 20:
        raise ValueError("unsupported top_n")
    ordered = sorted(ranked, key=lambda item: item["rank"])
    if [item["rank"] for item in ordered] != list(range(1, 21)):
        raise RuntimeError("FROZEN_BGE_INPUT_MISMATCH")
    return ordered[:top_n]


def evidence_state(truth: dict[str, Any]) -> str:
    if truth["all"]:
        return "ALL"
    if truth["any"]:
        return "PARTIAL"
    return "NONE"


def sentence_map(questions: dict[str, dict[str, Any]], query_id: str) -> dict[str, str]:
    return {str(item["key"]): str(item["text"]) for item in questions[query_id]["relevant"]}


def truth_for(
    query_id: str,
    results: list[SearchResult],
    retrieval_row: dict[str, Any],
    questions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    keys = list(retrieval_row["truth"]["section_aware"].get("relevant_sentence_keys", []))
    smap = sentence_map(questions, query_id)
    joined = "\n".join(str(result.payload.get("text", "")) for result in results)
    present = [key for key in keys if key in smap and text_has_sentence(joined, smap[key])]
    return {
        "relevant_keys": keys,
        "present_keys": present,
        "missing_keys": [key for key in keys if key not in present],
        "any": bool(present),
        "all": bool(keys) and len(present) == len(keys),
        "recall": len(present) / len(keys) if keys else None,
    }


def support_units_for(row: dict[str, Any]) -> list[SupportUnit]:
    return [
        SupportUnit(
            support_unit_id=item["support_unit_id"],
            parent_evidence_block_id=item["parent_evidence_block_id"],
            evidence_id=item["evidence_id"],
            source_id=item.get("source_id"),
            document_version=item.get("document_version"),
            section_id=item.get("section_id"),
            contributing_chunk_ids=tuple(item.get("contributing_chunk_ids", [])),
            tenant_id=item.get("tenant_id"),
            authorized=bool(item.get("authorized", True)),
            model_visible=bool(item.get("model_visible", True)),
            text=item["text"],
        )
        for item in row["support_units"]
    ]


def build_condition_rows(
    top_n: int,
    retrieval: dict[str, dict[str, Any]],
    reranker: dict[str, dict[str, Any]],
    chunks: dict[str, SearchResult],
    questions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    builder = SectionAwareEvidenceBuilder(
        OfflineQdrant(chunks), "offline", token_budget=EVIDENCE_BUDGET
    )
    context = RetrievalContext(tenant_id="ragbench-techqa", is_system=False)
    rows: list[dict[str, Any]] = []

    async def build_all() -> None:
        for query_id in sorted(retrieval):
            ranked = reranker[query_id]["reranked_top20"]
            anchor_records = select_persisted_anchors(ranked, top_n)
            anchors = [deserialize_result(item, score_name="bge_score") for item in anchor_records]
            built = await builder.build(anchors, context)
            anchor_truth = truth_for(query_id, anchors, retrieval[query_id], questions)
            relevant_sentences = sentence_map(questions, query_id)
            blocks = [
                serialize_result(item, rank=index, score_name="score")
                for index, item in enumerate(built.blocks, 1)
            ]
            persisted_blocks = json.loads(json.dumps(blocks, ensure_ascii=False))
            units = build_support_units(
                [deserialize_result(item, score_name="score") for item in persisted_blocks]
            )
            block_results = [
                deserialize_result(item, score_name="score") for item in persisted_blocks
            ]
            block_truth = truth_for(query_id, block_results, retrieval[query_id], questions)
            hybrid_results = [
                deserialize_result(item, score_name="fused_score")
                for item in retrieval[query_id]["authorized_top20"]
            ]
            hybrid_truth = truth_for(query_id, hybrid_results, retrieval[query_id], questions)
            serialized_units = serialize_support_units(units)
            raw_chars = sum(len(str(item.payload.get("text", ""))) for item in block_results)
            rows.append(
                {
                    "query_id": query_id,
                    "top_n": top_n,
                    "evidence_budget": EVIDENCE_BUDGET,
                    "bge_candidate_ranks_used": [item["rank"] for item in anchor_records],
                    "bge_anchors": [
                        {
                            "rank": item["rank"],
                            "chunk_id": item["chunk_id"],
                            "bge_score": item["bge_score"],
                            "source_id": item.get("source_id"),
                            "document_version": item.get("document_version"),
                            "text_hash": item.get("text_hash"),
                            "relevant_keys": [
                                key
                                for key, text in relevant_sentences.items()
                                if text_has_sentence(item.get("text", ""), text)
                            ],
                        }
                        for item in anchor_records
                    ],
                    "section_aware_blocks": blocks,
                    "section_aware_context": serialize_section_aware_context(built.blocks),
                    "support_units": [unit.as_dict() for unit in units],
                    "evidence_hash": canonical_hash(
                        {"blocks": blocks, "units": [unit.as_dict() for unit in units]}
                    ),
                    "context_tokens": built.context_tokens,
                    "serialized_evidence_chars": len(serialized_units),
                    "serialized_evidence_words": len(serialized_units.split()),
                    "raw_evidence_chars": raw_chars,
                    "header_metadata_chars": max(0, len(serialized_units) - raw_chars),
                    "support_unit_count": len(units),
                    "budget_exhausted": built.budget_exhausted,
                    "truncated_block_count": built.truncated_block_count,
                    "dropped_expansion_count": built.dropped_expansion_count,
                    "expanded": built.expanded,
                    "hybrid_truth": hybrid_truth,
                    "bge_truth": anchor_truth,
                    "section_aware_truth": block_truth,
                }
            )

    asyncio.run(build_all())
    return rows


def preregistration() -> None:
    retrieval, reranker, config = validate_sources()
    annotated = annotated_ids(retrieval)
    cutoff_reference = read_json(PHASE0 / "sectionaware-target.json").get("query_ids", [])
    value = {
        "version": "TECHQA_BGE_TOPN_ABLATION_V1",
        "implementation_check": False,
        "architecture_diagnostic": True,
        "promotion_authority": False,
        "source": {
            "dataset": config["dataset"],
            "revision": REVISION,
            "split": config["split"],
            "debug50_hash": DEBUG_HASH,
            "holdout50_hash": HOLDOUT_HASH,
            "config_fingerprint": CONFIG_HASH,
            "corpus_fingerprint": CORPUS_HASH,
            "annotated_population_size": ANNOTATED_SIZE,
            "annotated_query_ids": annotated,
            "phase0_sectionaware_loss_reference_ids": sorted(cutoff_reference),
        },
        "conditions": {"top_n": list(TOP_N_VALUES), "section_aware_budget": EVIDENCE_BUDGET},
        "single_changed_variable": "bge_top_n_cutoff",
        "frozen": {
            "hybrid": "persisted authorized Hybrid Top20",
            "bge": RERANKER_MODEL,
            "bge_input": "persisted reranked ranks 1..20; no reranker inference",
            "section_aware": "existing SectionAwareEvidenceBuilder",
        },
        "hypotheses": {
            "H1": "Top5 cuts some required evidence present in Hybrid Top20 before SectionAware.",
            "H2": "Top8 increases ALL-relevant completeness versus Top5.",
            "H3": "Top12 has limited or negative marginal benefit from anchor competition at budget 2400.",
            "H4": "If recovery concentrates in an existing cross-lingual subset, aggressive Top5 is more harmful there.",
        },
        "gates": {
            "top8_strong": ">=3 cutoff-loss ALL recoveries with <=1 new ALL regression",
            "top8_partial": "1-2 recoveries with no material regression",
            "top8_not_supported": "0 recoveries or gains offset by regressions",
            "top12_marginal": "<=1 ALL recovery over Top8",
            "top12_material": ">=2 ALL recoveries over Top8 without offsetting regressions",
        },
        "zero_inference": {
            "openai": 0,
            "ollama": 0,
            "retrieval": 0,
            "embedding": 0,
            "reranker": 0,
            "terra": 0,
            "luna": 0,
        },
        "holdout_policy": "identity verification only; no retrieval, evidence replay, inference, or tuning inspection",
    }
    write_json("preregistration.json", value)
    (OUT / "preregistration.sha256").write_text(file_hash(PREREG) + "\n", encoding="utf-8")
    write_json("source-integrity.json", source_integrity(config, retrieval, reranker, annotated))


def load_prereg() -> dict[str, Any]:
    value = read_json(PREREG)
    if (OUT / "preregistration.sha256").read_text(encoding="utf-8").strip() != file_hash(PREREG):
        raise RuntimeError("PREREGISTRATION_IDENTITY_MISMATCH")
    return value


def verify_baseline(top5_rows: list[dict[str, Any]]) -> dict[str, Any]:
    prior = {
        row["query_id"]: row for row in read_jsonl(BUDGET_ABLATION / "budget-2400-evidence.jsonl")
    }
    if len(prior) != DEBUG_SIZE:
        raise RuntimeError("BASELINE_REPRODUCTION_MISMATCH")
    checks = []
    for row in top5_rows:
        old = prior[row["query_id"]]
        checks.append(
            {
                "query_id": row["query_id"],
                "evidence_hash_equal": row["evidence_hash"] == old.get("evidence_hash"),
                "context_tokens_equal": row["context_tokens"] == old.get("context_tokens"),
                "support_unit_count_equal": row["support_unit_count"]
                == len(old.get("support_units", [])),
                "bge_anchor_ids_equal": [x["chunk_id"] for x in row["bge_anchors"]]
                == old.get("bge_anchor_ids"),
            }
        )
    if not all(all(value for key, value in item.items() if key != "query_id") for item in checks):
        raise RuntimeError("BASELINE_REPRODUCTION_MISMATCH")
    return {"verified": True, "query_count": len(checks), "checks": checks}


def run_offline() -> None:
    prereg = load_prereg()
    retrieval, reranker, config = validate_sources()
    questions = load_questions()
    if prereg["conditions"] != {
        "section_aware_budget": EVIDENCE_BUDGET,
        "top_n": list(TOP_N_VALUES),
    }:
        raise RuntimeError("PREREGISTRATION_IDENTITY_MISMATCH")
    chunks = source_chunks()
    all_rows: dict[int, list[dict[str, Any]]] = {}
    for top_n in TOP_N_VALUES:
        rows = build_condition_rows(top_n, retrieval, reranker, chunks, questions)
        all_rows[top_n] = rows
        write_jsonl(f"top{top_n}-results.jsonl", rows)
    baseline = verify_baseline(all_rows[5])
    annotated = annotated_ids(retrieval)
    cutoff_rows = []
    for query_id in annotated:
        by_n = {
            top_n: next(row for row in all_rows[top_n] if row["query_id"] == query_id)
            for top_n in TOP_N_VALUES
        }
        if by_n[5]["hybrid_truth"]["all"] and not by_n[5]["bge_truth"]["all"]:
            ranked = sorted(reranker[query_id]["reranked_top20"], key=lambda item: item["rank"])
            missing = by_n[5]["bge_truth"]["missing_keys"]
            required_ranks = []
            for key in by_n[5]["hybrid_truth"]["relevant_keys"]:
                ranks = [
                    item["rank"]
                    for item in ranked
                    if key in sentence_map(questions, query_id)
                    and text_has_sentence(
                        item.get("text", ""), sentence_map(questions, query_id)[key]
                    )
                ]
                required_ranks.append(
                    {
                        "relevant_key": key,
                        "ranks": ranks,
                        "first_rank": min(ranks) if ranks else None,
                    }
                )
            cutoff_rows.append(
                {
                    "query_id": query_id,
                    "question": questions[query_id]["question"],
                    "hybrid_top20_recall": by_n[5]["hybrid_truth"]["recall"],
                    "bge_top5_recall": by_n[5]["bge_truth"]["recall"],
                    "bge_top8_recall": by_n[8]["bge_truth"]["recall"],
                    "bge_top12_recall": by_n[12]["bge_truth"]["recall"],
                    "first_missing_relevant_rank": min(
                        (
                            item["first_rank"]
                            for item in required_ranks
                            if item["relevant_key"] in missing and item["first_rank"] is not None
                        ),
                        default=None,
                    ),
                    "required_evidence_ranks": required_ranks,
                    "section_aware": {
                        str(n): {
                            "all": by_n[n]["section_aware_truth"]["all"],
                            "recall": by_n[n]["section_aware_truth"]["recall"],
                        }
                        for n in TOP_N_VALUES
                    },
                }
            )
    write_json(
        "cutoff-loss-population.json",
        {
            "count": len(cutoff_rows),
            "query_ids": [r["query_id"] for r in cutoff_rows],
            "rule": "Hybrid Top20 ALL and BGE Top5 not ALL",
        },
    )
    write_jsonl("cutoff-loss-analysis.jsonl", cutoff_rows)
    write_json("source-integrity.json", source_integrity(config, retrieval, reranker, annotated))
    write_json(
        "frozen-bge-inputs.json",
        {
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "reranker_calls": 0,
            "holdout_calls": 0,
            "retrieval_file_sha256": file_hash(DEBUG / "retrieval-results.jsonl"),
            "reranker_file_sha256": file_hash(DEBUG / "reranker-results.jsonl"),
            "corpus_fingerprint": config["corpus_fingerprint"],
            "bge_model": config["reranker"]["model"],
            "rank_order_verified": True,
            "query_count": DEBUG_SIZE,
            "annotated_query_ids": annotated,
            "baseline_top5_2400_reconstruction": "compared to prior offline ablation artifact",
            "top5_2400_reconstruction": baseline,
        },
    )


def condition_truth(row: dict[str, Any]) -> dict[str, Any]:
    return row["section_aware_truth"]


def classify_transitions(
    rows_by_n: dict[int, dict[str, dict[str, Any]]], ids: list[str]
) -> list[dict[str, Any]]:
    output = []
    for query_id in ids:
        states = {
            str(n): evidence_state(condition_truth(rows_by_n[n][query_id])) for n in TOP_N_VALUES
        }
        output.append(
            {
                "query_id": query_id,
                "states": states,
                "changed": len(set(states.values())) > 1,
                "crowding": {
                    "top5_to_top8": deterministic_crowding(
                        rows_by_n[5][query_id], rows_by_n[8][query_id]
                    ),
                    "top8_to_top12": deterministic_crowding(
                        rows_by_n[8][query_id], rows_by_n[12][query_id]
                    ),
                },
            }
        )
    return output


def deterministic_crowding(prev: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    prev_ids = {item["chunk_id"] for item in prev["bge_anchors"]}
    added = [item for item in current["bge_anchors"] if item["chunk_id"] not in prev_ids]
    previous_texts = {item.get("text_hash") for item in prev["bge_anchors"]}
    relevant_added = [item for item in added if item.get("relevant_keys")]
    return {
        "new_anchor_count": len(added),
        "new_relevant_anchor_count": len(relevant_added),
        "new_relevant_key_count": len(
            {key for item in relevant_added for key in item.get("relevant_keys", [])}
        ),
        "new_irrelevant_anchor_count": len(added) - len(relevant_added),
        "new_exact_duplicate_anchor_count": sum(
            item.get("text_hash") in previous_texts for item in added
        ),
        "semantic_redundancy": "UNKNOWN unless exact text duplicate",
    }


def transition_counts(
    transitions: list[dict[str, Any]], first: str, second: str
) -> dict[str, int]:
    return dict(
        Counter(
            f"{row['states'][first]} -> {row['states'][second]}"
            for row in transitions
        )
    )


def manual_review(
    transitions: list[dict[str, Any]],
    rows_by_n: dict[int, dict[str, dict[str, Any]]],
    reranker: dict[str, dict[str, Any]],
    retrieval: dict[str, dict[str, Any]],
    questions: dict[str, dict[str, Any]],
    cutoff_ids: set[str],
) -> tuple[str, list[str], list[str], list[str]]:
    changed_ids = [row["query_id"] for row in transitions if row["changed"]]
    regression_ids = [
        row["query_id"]
        for row in transitions
        if any(
            rows_by_n[n][row["query_id"]]["section_aware_truth"]["all"]
            and not rows_by_n[n2][row["query_id"]]["section_aware_truth"]["all"]
            for n, n2 in ((5, 8), (8, 12))
        )
    ]
    review_ids = sorted(set(changed_ids) | cutoff_ids)
    unresolved = sorted(
        query_id
        for query_id in cutoff_ids
        if not rows_by_n[12][query_id]["section_aware_truth"]["all"]
    )
    lines = [
        "# TechQA BGE Top-N Ablation — Manual Review",
        "",
        "Offline only. SectionAware budget is fixed at 2400. BGE ranks 1–20 are persisted inputs; no BGE inference was run.",
        "",
        "| Query | Top5 | Top8 | Top12 | First relevant missing rank | Outcome |",
        "|---|---|---|---|---:|---|",
    ]
    for query_id in review_ids:
        states = {
            n: evidence_state(rows_by_n[n][query_id]["section_aware_truth"]) for n in TOP_N_VALUES
        }
        missing_rank = "-"
        cutoff = next(
            (
                row
                for row in read_jsonl(OUT / "cutoff-loss-analysis.jsonl")
                if row["query_id"] == query_id
            ),
            None,
        )
        if cutoff and cutoff.get("first_missing_relevant_rank") is not None:
            missing_rank = str(cutoff["first_missing_relevant_rank"])
        outcome = (
            "recovered@8"
            if states[5] != "ALL" and states[8] == "ALL"
            else "recovered@12"
            if states[8] != "ALL" and states[12] == "ALL"
            else "regression@8/12"
            if query_id in regression_ids
            else "unresolved cutoff-loss"
            if query_id in unresolved
            else "changed"
        )
        lines.append(
            f"| `{query_id}` | {states[5]} | {states[8]} | {states[12]} | {missing_rank} | {outcome} |"
        )
    for section, ids in (
        (
            "SECTION A — Top5→Top8 recoveries",
            [
                q
                for q in review_ids
                if evidence_state(rows_by_n[5][q]["section_aware_truth"]) != "ALL"
                and evidence_state(rows_by_n[8][q]["section_aware_truth"]) == "ALL"
            ],
        ),
        (
            "SECTION B — Top8→Top12 additional recoveries",
            [
                q
                for q in review_ids
                if evidence_state(rows_by_n[8][q]["section_aware_truth"]) != "ALL"
                and evidence_state(rows_by_n[12][q]["section_aware_truth"]) == "ALL"
            ],
        ),
        ("SECTION C — regressions / crowding", regression_ids),
        ("SECTION D — cutoff-loss cases still unresolved", unresolved),
    ):
        lines.extend(["", f"## {section}", ""])
        for query_id in ids:
            lines.extend(render_query_review(query_id, rows_by_n, reranker, retrieval, questions))
    return "\n".join(lines) + "\n", review_ids, regression_ids, unresolved


def render_query_review(
    query_id: str,
    rows_by_n: dict[int, dict[str, dict[str, Any]]],
    reranker: dict[str, dict[str, Any]],
    retrieval: dict[str, dict[str, Any]],
    questions: dict[str, dict[str, Any]],
) -> list[str]:
    lines = [
        f"### {query_id}",
        "",
        f"Question: {questions[query_id]['question']}",
        "",
        "Relevant evidence keys:",
    ]
    lines.extend(
        f"- `{key}`"
        for key in retrieval[query_id]["truth"]["section_aware"].get("relevant_sentence_keys", [])
    )
    lines.extend(["", "#### Persisted BGE ranks 1–12", ""])
    ranked = sorted(reranker[query_id]["reranked_top20"], key=lambda item: item["rank"])
    for item in ranked[:12]:
        lines.extend(
            [
                f"**Rank {item['rank']}** — score `{item['bge_score']}`; chunk `{item['chunk_id']}`; source `{item.get('source_id')}`",
                "",
                item.get("text", ""),
                "",
            ]
        )
    for top_n in TOP_N_VALUES:
        row = rows_by_n[top_n][query_id]
        truth = row["section_aware_truth"]
        lines.extend(
            [
                f"#### TOP{top_n} / BUDGET2400",
                "",
                f"Anchor ranks: `{row['bge_candidate_ranks_used']}`",
                f"SectionAware state: `{evidence_state(truth)}`; relevant present: `{truth['present_keys']}`; missing: `{truth['missing_keys']}`",
                f"Context tokens: `{row['context_tokens']}`; budget exhausted: `{row['budget_exhausted']}`; truncated blocks: `{row['truncated_block_count']}`",
                "",
                "Final evidence units:",
            ]
        )
        for unit in row["support_units"]:
            lines.extend([f"- `{unit['support_unit_id']}`: {unit['text']}"])
        lines.append("")
    return lines


def finalize() -> None:
    load_prereg()
    retrieval, reranker, config = validate_sources()
    questions = load_questions()
    annotated = annotated_ids(retrieval)
    rows_by_n = {
        n: {row["query_id"]: row for row in read_jsonl(OUT / f"top{n}-results.jsonl")}
        for n in TOP_N_VALUES
    }
    if any(len(rows_by_n[n]) != DEBUG_SIZE for n in TOP_N_VALUES):
        raise RuntimeError("ABLATION_RESULT_MISMATCH")
    baseline = verify_baseline(list(rows_by_n[5].values()))
    transitions = classify_transitions(rows_by_n, annotated)
    write_jsonl("query-transitions.jsonl", transitions)
    crowding_summary = {
        edge: {
            key: sum(row["crowding"][edge][key] for row in transitions)
            for key in (
                "new_anchor_count",
                "new_relevant_anchor_count",
                "new_relevant_key_count",
                "new_irrelevant_anchor_count",
                "new_exact_duplicate_anchor_count",
            )
        }
        for edge in ("top5_to_top8", "top8_to_top12")
    }
    write_json(
        "transition-summary.json",
        {
            "annotated_queries": len(transitions),
            "changed_queries": sum(row["changed"] for row in transitions),
            "states": dict(
                Counter(
                    " -> ".join(row["states"][str(n)] for n in TOP_N_VALUES) for row in transitions
                )
            ),
            "top5_to_top8": transition_counts(transitions, "5", "8"),
            "top8_to_top12": transition_counts(transitions, "8", "12"),
            "crowding": crowding_summary,
        },
    )
    summaries: dict[str, Any] = {}
    for n in TOP_N_VALUES:
        selected = [rows_by_n[n][query_id] for query_id in annotated]
        recalls = [
            row["section_aware_truth"]["recall"]
            for row in selected
            if row["section_aware_truth"]["recall"] is not None
        ]
        contexts = [float(row["context_tokens"]) for row in selected]
        summaries[str(n)] = {
            "queries": len(selected),
            "any": sum(row["section_aware_truth"]["any"] for row in selected),
            "all": sum(row["section_aware_truth"]["all"] for row in selected),
            "mean_recall": statistics.mean(recalls),
            "mean_context_tokens": statistics.mean(contexts),
            "p50_context_tokens": statistics.median(contexts),
            "p95_context_tokens": percentile(contexts, 0.95),
            "max_context_tokens": max(contexts),
            "budget_exhausted": sum(row["budget_exhausted"] for row in selected),
            "truncated": sum(row["truncated_block_count"] > 0 for row in selected),
            "mean_support_units": statistics.mean(row["support_unit_count"] for row in selected),
            "p95_support_units": percentile(
                [float(row["support_unit_count"]) for row in selected], 0.95
            ),
            "max_support_units": max(row["support_unit_count"] for row in selected),
            "mean_raw_evidence_chars": statistics.mean(
                row["raw_evidence_chars"] for row in selected
            ),
            "mean_serialized_chars": statistics.mean(
                row["serialized_evidence_chars"] for row in selected
            ),
            "mean_header_metadata_chars": statistics.mean(
                row["header_metadata_chars"] for row in selected
            ),
        }
    write_json(
        "summary.json",
        {"budget": EVIDENCE_BUDGET, "annotated": summaries, "baseline_reproduction": baseline},
    )
    cutoff = (
        read_json(OUT / "cutoff-loss-population.json")
        if (OUT / "cutoff-loss-population.json").exists()
        else {"query_ids": []}
    )
    manual, review_ids, regression_ids, unresolved_ids = manual_review(
        transitions, rows_by_n, reranker, retrieval, questions, set(cutoff["query_ids"])
    )
    (OUT / "manual-review.md").write_text(manual, encoding="utf-8")
    exact_top8 = summaries["8"]["all"]
    exact_top12 = summaries["12"]["all"]
    cutoff_count = len(cutoff["query_ids"])
    recovered8 = sum(
        rows_by_n[8][q]["section_aware_truth"]["all"]
        and not rows_by_n[5][q]["section_aware_truth"]["all"]
        for q in cutoff["query_ids"]
    )
    recovered12 = sum(
        rows_by_n[12][q]["section_aware_truth"]["all"]
        and not rows_by_n[5][q]["section_aware_truth"]["all"]
        for q in cutoff["query_ids"]
    )
    regression_count = len(regression_ids)
    regression8_ids = [
        query_id
        for query_id in annotated
        if rows_by_n[5][query_id]["section_aware_truth"]["all"]
        and not rows_by_n[8][query_id]["section_aware_truth"]["all"]
    ]
    regression12_ids = [
        query_id
        for query_id in annotated
        if rows_by_n[8][query_id]["section_aware_truth"]["all"]
        and not rows_by_n[12][query_id]["section_aware_truth"]["all"]
    ]
    top8_gate = (
        "TOP8_STRONG_SUPPORT"
        if recovered8 >= 3 and len(regression8_ids) <= 1
        else "TOP8_PARTIAL_SUPPORT"
        if recovered8 >= 1 and not regression8_ids
        else "TOP8_NOT_SUPPORTED"
    )
    top12_gate = (
        "TOP12_MATERIAL"
        if exact_top12 - exact_top8 >= 2 and not regression12_ids
        else "TOP12_MARGINAL"
    )
    decision = {
        "verdict": "TOP5_CUTOFF_CONFIRMED_BOTTLENECK"
        if recovered8 >= 3
        else "TOP5_CUTOFF_PARTIAL_BOTTLENECK"
        if recovered8 >= 1
        else "TOP5_CUTOFF_NOT_MATERIAL",
        "top8_gate": top8_gate,
        "top12_gate": top12_gate,
        "preferred_debug_candidate": "TOP8"
        if top8_gate == "TOP8_STRONG_SUPPORT" and top12_gate == "TOP12_MARGINAL"
        else "TOP12"
        if top12_gate == "TOP12_MATERIAL"
        else "NONE",
        "recommended_next_experiment": "controlled Top-N validation on a fresh frozen set"
        if recovered8 >= 1
        else "no Top-N change; investigate other evidence bottlenecks",
        "implementation_check": False,
        "architecture_diagnostic": True,
        "promotion_authority": False,
        "production_top_n_changed": False,
        "holdout_untouched": True,
        "provider_calls": {
            "openai": 0,
            "ollama": 0,
            "terra": 0,
            "luna": 0,
            "retrieval": 0,
            "embedding": 0,
            "reranker": 0,
        },
        "populations": {
            "annotated": len(annotated),
            "cutoff_loss": cutoff_count,
            "manual_review": len(review_ids),
            "regressions": regression_count,
            "unresolved_cutoff_loss": len(unresolved_ids),
        },
        "regression_ids": {
            "top5_to_top8": regression8_ids,
            "top8_to_top12": regression12_ids,
            "any_transition": regression_ids,
        },
        "recovery": {"top8": recovered8, "top12": recovered12},
        "marginal": {
            "all_gain_top5_to_top8": exact_top8 - summaries["5"]["all"],
            "all_gain_top8_to_top12": exact_top12 - exact_top8,
            "mean_recall_gain_top5_to_top8": summaries["8"]["mean_recall"]
            - summaries["5"]["mean_recall"],
            "mean_recall_gain_top8_to_top12": summaries["12"]["mean_recall"]
            - summaries["8"]["mean_recall"],
        },
        "regression_counts": {
            "top5_to_top8": len(regression8_ids),
            "top8_to_top12": len(regression12_ids),
            "any_transition": regression_count,
        },
        "summaries": summaries,
        "cross_lingual_breakdown": "NOT_AVAILABLE",
        "preregistration_hash": file_hash(PREREG),
    }
    write_json(
        "serialization-summary.json",
        {
            str(n): {
                key: summaries[str(n)][key]
                for key in (
                    "mean_raw_evidence_chars",
                    "mean_serialized_chars",
                    "mean_header_metadata_chars",
                    "mean_support_units",
                    "p95_support_units",
                    "max_support_units",
                )
            }
            for n in TOP_N_VALUES
        },
    )
    write_json("decision.json", decision)
    report = render_report(
        decision,
        summaries,
        cutoff_count,
        recovered8,
        recovered12,
        regression_ids,
        unresolved_ids,
        review_ids,
    )
    (OUT / "report.md").write_text(report, encoding="utf-8")


def render_report(
    decision: dict[str, Any],
    summaries: dict[str, Any],
    cutoff_count: int,
    recovered8: int,
    recovered12: int,
    regression_ids: list[str],
    unresolved_ids: list[str],
    review_ids: list[str],
) -> str:
    lines = [
        "# TechQA BGE Top-N Ablation V1",
        "",
        "Artifact-only diagnostic; `implementation_check=false`; `promotion_authority=false`.",
        "",
        "## Frozen protocol",
        "",
        f"- Dataset revision: `{REVISION}`; DEBUG50 `{DEBUG_HASH}`; HOLDOUT50 `{HOLDOUT_HASH}`.",
        f"- Fixed SectionAware budget: `{EVIDENCE_BUDGET}`; conditions: `Top5`, `Top8`, `Top12`.",
        "- Persisted Hybrid Top20/BGE ranks were reused. Retrieval, embedding, reranker, Luna and Terra calls: `0`.",
        "- Canonical production `top_n=5` was not changed.",
        "",
        "## Annotated 38 results",
        "",
        "| Metric | Top5 | Top8 | Top12 |",
        "|---|---:|---:|---:|",
        f"| ANY | {summaries['5']['any']}/38 | {summaries['8']['any']}/38 | {summaries['12']['any']}/38 |",
        f"| ALL | {summaries['5']['all']}/38 | {summaries['8']['all']}/38 | {summaries['12']['all']}/38 |",
        f"| Mean relevant recall | {summaries['5']['mean_recall']:.6f} | {summaries['8']['mean_recall']:.6f} | {summaries['12']['mean_recall']:.6f} |",
        f"| Mean context count | {summaries['5']['mean_context_tokens']:.2f} | {summaries['8']['mean_context_tokens']:.2f} | {summaries['12']['mean_context_tokens']:.2f} |",
        f"| p95 context count | {summaries['5']['p95_context_tokens']:.0f} | {summaries['8']['p95_context_tokens']:.0f} | {summaries['12']['p95_context_tokens']:.0f} |",
        f"| Max context count | {summaries['5']['max_context_tokens']:.0f} | {summaries['8']['max_context_tokens']:.0f} | {summaries['12']['max_context_tokens']:.0f} |",
        f"| Budget exhausted | {summaries['5']['budget_exhausted']} | {summaries['8']['budget_exhausted']} | {summaries['12']['budget_exhausted']} |",
        f"| Mean support units | {summaries['5']['mean_support_units']:.2f} | {summaries['8']['mean_support_units']:.2f} | {summaries['12']['mean_support_units']:.2f} |",
        "",
        "## Cutoff-loss population",
        "",
        f"- Rule: Hybrid Top20 ALL and BGE Top5 not ALL; population `{cutoff_count}`.",
        f"- Recovered ALL at Top8: `{recovered8}/{cutoff_count}`.",
        f"- Recovered ALL at Top12: `{recovered12}/{cutoff_count}`.",
        f"- Still unresolved at Top12: `{len(unresolved_ids)}/{cutoff_count}`.",
        f"- ALL regressions Top5→Top8: `{len(decision['regression_ids']['top5_to_top8'])}`.",
        f"- ALL regressions Top8→Top12: `{len(decision['regression_ids']['top8_to_top12'])}`.",
        f"- ALL gain Top5→Top8: `{decision['marginal']['all_gain_top5_to_top8']}`; Top8→Top12: `{decision['marginal']['all_gain_top8_to_top12']}`.",
        f"- Mean-recall gain Top5→Top8: `{decision['marginal']['mean_recall_gain_top5_to_top8']:.6f}`; Top8→Top12: `{decision['marginal']['mean_recall_gain_top8_to_top12']:.6f}`.",
        "",
        "## Decision",
        "",
        f"- Top8 gate: `{decision['top8_gate']}`.",
        f"- Top12 gate: `{decision['top12_gate']}`.",
        f"- Diagnostic verdict: `{decision['verdict']}`.",
        f"- Preferred DEBUG candidate: `{decision['preferred_debug_candidate']}`.",
        f"- Manual review queries: `{len(review_ids)}`; see `manual-review.md`.",
        "- Cross-lingual breakdown: `NOT_AVAILABLE` because no trusted existing language-group label was persisted.",
        "- No production promotion is authorized by this run.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if not any((args.prepare_only, args.run, args.finalize)):
        parser.error("choose --prepare-only, --run, or --finalize")
    if args.prepare_only:
        preregistration()
    if args.run:
        run_offline()
    if args.finalize:
        finalize()


if __name__ == "__main__":
    main()
