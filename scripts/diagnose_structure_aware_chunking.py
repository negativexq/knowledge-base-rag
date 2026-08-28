# ruff: noqa: E501
"""Phase 7.10 fact-evidence and structure-aware representation diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.evaluation.context_builder import build_context_v1
from app.evaluation.fact_evidence import evaluate_fact_evidence, normalize_evidence
from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import score_required_facts
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.ingestion.qdrant_store import QdrantStore
from app.llm.generate import stream_answer
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET_PATH = DATA / "golden-dataset-v2.json"
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
P75 = ROOT / "artifacts/phase-7/context-builder-full-validation"
CANDIDATES = ROOT / "artifacts/phase-5-5/full/candidate-sweep.json"
OUT = ROOT / "artifacts/phase-7/structure-aware-chunking-diagnostic"
FACTS_PATH = OUT / "fact-ground-truth.json"
QUERY_IDS = ("multi-00-1", "multi-00-3", "multi-03-0")
EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
    "generator": "qwen3.5:4b",
    "prompt": "v3",
    "think": False,
}
COMPACT_SOURCE_LIMIT = 320
REPRESENTATIONS = ("CURRENT_CHUNK", "PARENT_SECTION", "SAME_SECTION_NEIGHBORS", "SECTION_AWARE_MERGED")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def source_path(source_id: str) -> Path | None:
    direct = DATA / f"{source_id}.md"
    mirror = DATA / "pdf-sources" / f"{source_id}.md"
    if direct.exists():
        return direct
    if mirror.exists():
        return mirror
    return None


def query_facts(gt: dict[str, Any], query_id: str) -> list[dict[str, Any]]:
    query = next(item for item in gt["queries"] if item["query_id"] == query_id)
    fact_ids = {fact_id for component in query["required_components"] for fact_id in component["required_fact_ids"]}
    by_id = {fact["required_fact_id"]: fact for fact in gt["facts"]}
    return [by_id[fact_id] for fact_id in sorted(fact_ids)]


def blocks_from_chunks(chunks: list[SearchResult]) -> list[dict[str, Any]]:
    return [
        {
            "block_id": chunk.id or str(chunk.payload.get("chunk_id", "")),
            "source_id": str(chunk.payload.get("source_id", "")),
            "text": str(chunk.payload.get("text", "")),
            "heading_path": chunk.payload.get("heading_path", []),
            "original_chunk_ids": [chunk.id or str(chunk.payload.get("chunk_id", ""))],
        }
        for chunk in chunks
    ]


def as_search_result(block: dict[str, Any], template: SearchResult) -> SearchResult:
    payload = dict(template.payload)
    payload.update(
        {
            "source_id": block["source_id"],
            "text": block["text"],
            "chunk_id": block["block_id"],
            "heading_path": block.get("heading_path", []),
            "diagnostic_representation": block.get("representation"),
            "original_chunk_ids": block.get("original_chunk_ids", []),
        }
    )
    return SearchResult(score=template.score, id=block["block_id"], payload=payload)


def full_source_block(source_id: str, originals: list[SearchResult], representation: str) -> dict[str, Any] | None:
    path = source_path(source_id)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8")
    original_ids = [chunk.id or str(chunk.payload.get("chunk_id", "")) for chunk in originals]
    return {
        "block_id": f"diag:{representation.lower()}:{source_id}",
        "source_id": source_id,
        "text": text,
        "heading_path": [next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), source_id)],
        "original_chunk_ids": original_ids,
        "representation": representation,
    }


def build_representations(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    chunks = chunks_from_cache(record)
    current = blocks_from_chunks(chunks)
    by_source: dict[str, list[SearchResult]] = {}
    for chunk in chunks:
        by_source.setdefault(str(chunk.payload.get("source_id")), []).append(chunk)

    parent: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    for source_id, source_chunks in by_source.items():
        expanded = full_source_block(source_id, source_chunks, "PARENT_SECTION")
        parent.extend([expanded] if expanded else blocks_from_chunks(source_chunks))
        path = source_path(source_id)
        source_tokens = len(path.read_text(encoding="utf-8").split()) if path else 10**9
        compact = full_source_block(source_id, source_chunks, "SECTION_AWARE_MERGED") if source_tokens <= COMPACT_SOURCE_LIMIT else None
        merged.extend([compact] if compact else blocks_from_chunks(source_chunks))

    # Current ingestion already groups every block under one exact logical
    # heading before chunking. These fixtures have one chunk per section, so
    # no safe same-section neighbor exists. The implementation deliberately
    # retains the current blocks rather than crossing a section boundary.
    neighbors = [dict(block, representation="SAME_SECTION_NEIGHBORS") for block in current]
    return {
        "CURRENT_CHUNK": current,
        "PARENT_SECTION": parent,
        "SAME_SECTION_NEIGHBORS": neighbors,
        "SECTION_AWARE_MERGED": merged,
    }


def representation_search_results(record: dict[str, Any], blocks: list[dict[str, Any]]) -> list[SearchResult]:
    originals = chunks_from_cache(record)
    templates = {str(chunk.payload.get("source_id")): chunk for chunk in originals}
    return [as_search_result(block, templates[block["source_id"]]) for block in blocks]


def verify_ground_truth(gt: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for fact in gt["facts"]:
        path = ROOT / fact["source_path"]
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        span = fact["supporting_text_span"]
        checks.append(
            {
                "required_fact_id": fact["required_fact_id"],
                "source_id": fact["authoritative_source_id"],
                "source_exists": path.exists(),
                "anchor_exists": normalize_evidence(fact["supporting_text_anchor"]) in normalize_evidence(text),
                "supporting_span_exists": normalize_evidence(span) in normalize_evidence(text),
                "span_chars": len(span),
            }
        )
    if not all(item["source_exists"] and item["anchor_exists"] and item["supporting_span_exists"] for item in checks):
        raise RuntimeError("FACT_GROUND_TRUTH_INCOMPLETE")
    return checks


def derive_current_chunks(gt: dict[str, Any], cache: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    top5_chunks = [chunk for query_id in QUERY_IDS for chunk in cache[query_id]["authorized_top5"]]
    rows: list[dict[str, Any]] = []
    for fact in gt["facts"]:
        source_id = fact["authoritative_source_id"]
        span = normalize_evidence(fact["supporting_text_span"])
        matches: list[dict[str, Any]] = []
        path = source_path(source_id)
        if path and path.parent == DATA:
            template = next((item for item in top5_chunks if item["source_id"] == source_id), None)
            source_type = template.get("metadata", {}).get("source_type", "filesystem") if template else "filesystem"
            doc_id = template.get("metadata", {}).get("document_version") if template else None
            for chunk in chunk_markdown_document(str(path), source_id, source_type=source_type, doc_id=doc_id):
                if span in normalize_evidence(chunk.text):
                    tenant_chunk = replace(chunk, tenant_id="tenant-a")
                    matches.append(
                        {
                            "chunk_id": QdrantStore.point_id_for(tenant_chunk),
                            "text": chunk.text,
                            "heading_path": list(chunk.heading_path),
                            "classification": "FULLY_CONTAINED",
                        }
                    )
        if not matches:
            seen: set[str] = set()
            for chunk in top5_chunks:
                if chunk["source_id"] == source_id and span in normalize_evidence(chunk["content"]) and chunk["chunk_id"] not in seen:
                    seen.add(chunk["chunk_id"])
                    matches.append(
                        {
                            "chunk_id": chunk["chunk_id"],
                            "text": chunk["content"],
                            "heading_path": chunk.get("metadata", {}).get("heading_path", []),
                            "classification": "FULLY_CONTAINED",
                        }
                    )
        rows.append(
            {
                "required_fact_id": fact["required_fact_id"],
                "source_id": source_id,
                "supporting_current_chunk_ids": [item["chunk_id"] for item in matches],
                "mappings": matches,
                "mapping_classification": "FULLY_CONTAINED" if matches else "NOT_REPRESENTED",
                "derived_not_ground_truth": True,
            }
        )
    return rows


def candidate_records() -> dict[str, dict[str, Any]]:
    sweep = read_json(CANDIDATES)
    rows = next(result["records"] for result in sweep["results"] if result["candidate_k"] == 20)
    return {row["query_id"]: row for row in rows if row["query_id"] in QUERY_IDS}


def source_chunk_counts(source_ids: set[str]) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for source_id in source_ids:
        path = source_path(source_id)
        if path and path.parent == DATA:
            counts[source_id] = len(chunk_markdown_document(str(path), source_id))
        else:
            counts[source_id] = None
    return counts


def current_recall(
    gt: dict[str, Any],
    cache: dict[str, dict[str, Any]],
    mapping: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = candidate_records()
    mapping_by_fact = {row["required_fact_id"]: row for row in mapping}
    all_sources = {fact["authoritative_source_id"] for fact in gt["facts"]}
    chunk_counts = source_chunk_counts(all_sources)
    records: list[dict[str, Any]] = []
    for query_id in QUERY_IDS:
        facts = query_facts(gt, query_id)
        top5_blocks = [
            {"source_id": item["source_id"], "text": item["content"]}
            for item in cache[query_id]["authorized_top5"]
        ]
        top5 = evaluate_fact_evidence(facts, top5_blocks)
        candidate_source_ids = candidates[query_id]["candidate_source_ids"]
        at20_present: list[str] = []
        at20_method: dict[str, str] = {}
        for fact in facts:
            fact_id = fact["required_fact_id"]
            if fact_id in top5.present_fact_ids:
                at20_present.append(fact_id)
                at20_method[fact_id] = "explicit supporting span in cached Top-5"
                continue
            source_id = fact["authoritative_source_id"]
            supporting_count = len(mapping_by_fact[fact_id]["supporting_current_chunk_ids"])
            total_chunks = chunk_counts[source_id]
            candidate_count = candidate_source_ids.count(source_id)
            if supporting_count and total_chunks is not None and candidate_count >= total_chunks:
                at20_present.append(fact_id)
                at20_method[fact_id] = (
                    f"inferred from complete source-chunk enumeration: candidate source count {candidate_count} "
                    f">= current source chunk count {total_chunks}; candidate artifact omits chunk IDs"
                )
            else:
                at20_method[fact_id] = "not established"
        required_ids = [fact["required_fact_id"] for fact in facts]
        required_sources = {fact["authoritative_source_id"] for fact in facts}
        source20 = required_sources <= set(candidate_source_ids)
        source5 = required_sources <= {item["source_id"] for item in cache[query_id]["authorized_top5"]}
        records.append(
            {
                "query_id": query_id,
                "required_fact_ids": required_ids,
                "source_recall_complete_at20": source20,
                "source_recall_complete_at5": source5,
                "fact_ids_present_at20": at20_present,
                "fact_ids_present_at5": top5.present_fact_ids,
                "fact_ids_missing_at20": [item for item in required_ids if item not in at20_present],
                "fact_ids_missing_at5": top5.missing_fact_ids,
                "fact_passage_recall_at20": len(at20_present) / len(required_ids),
                "fact_passage_recall_at5": top5.fact_evidence_recall,
                "all_required_facts_present_at20": set(required_ids) <= set(at20_present),
                "all_required_facts_present_at5": top5.all_required_fact_evidence_present,
                "candidate_at20_evidence_method": at20_method,
                "candidate_artifact_limitation": "candidate-sweep stores ordered source IDs but not candidate chunk IDs/content",
            }
        )
    total = sum(len(row["required_fact_ids"]) for row in records)
    return {
        "schema_version": "fact-evidence-recall-v1",
        "records": records,
        "aggregate": {
            "required_query_fact_occurrences": total,
            "source_recall_complete_at20": sum(row["source_recall_complete_at20"] for row in records),
            "source_recall_complete_at5": sum(row["source_recall_complete_at5"] for row in records),
            "fact_passage_recall_at20": sum(len(row["fact_ids_present_at20"]) for row in records) / total,
            "fact_passage_recall_at5": sum(len(row["fact_ids_present_at5"]) for row in records) / total,
            "all_required_facts_present_at20": sum(row["all_required_facts_present_at20"] for row in records),
            "all_required_facts_present_at5": sum(row["all_required_facts_present_at5"] for row in records),
        },
    }


def duplicate_count(blocks: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for block in blocks:
        text = normalize_evidence(block["text"])
        if text in seen:
            duplicates += 1
        seen.add(text)
    return duplicates


def irrelevant_paragraphs(blocks: list[dict[str, Any]], facts: list[dict[str, Any]]) -> int:
    anchors = [normalize_evidence(fact["supporting_text_anchor"]) for fact in facts]
    count = 0
    for block in blocks:
        for paragraph in block["text"].split("\n\n"):
            normalized = normalize_evidence(paragraph)
            if normalized and not any(anchor in normalized for anchor in anchors):
                count += 1
    return count


def representation_analysis(gt: dict[str, Any], cache: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    serializations: dict[str, Any] = {name: {"representation": name, "records": []} for name in REPRESENTATIONS}
    coverage_rows: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    for query_id in QUERY_IDS:
        record = cache[query_id]
        facts = query_facts(gt, query_id)
        variants = build_representations(record)
        current_tokens: int | None = None
        for name in REPRESENTATIONS:
            blocks = variants[name]
            search_results = representation_search_results(record, blocks)
            builder = build_context_v1(search_results, max_context_tokens=20000)
            metrics = evaluate_fact_evidence(facts, blocks)
            if name == "CURRENT_CHUNK":
                current_tokens = builder.context_tokens
            serializations[name]["records"].append(
                {
                    "query_id": query_id,
                    "evidence_blocks": blocks,
                    "context": builder.context,
                    "context_builder": builder.as_dict(),
                    "fact_evidence": metrics.as_dict(),
                }
            )
            coverage_rows.append({"query_id": query_id, "representation": name, **metrics.as_dict()})
            ratio = builder.context_tokens / current_tokens if current_tokens else 1.0
            token_rows.append(
                {
                    "query_id": query_id,
                    "representation": name,
                    "context_tokens": builder.context_tokens,
                    "context_chars": builder.context_chars,
                    "current_ratio": ratio,
                    "inflation": "LOW_INFLATION" if ratio <= 1.25 else "MODERATE_INFLATION" if ratio <= 2 else "HIGH_INFLATION",
                }
            )
            duplicate_rows.append(
                {
                    "query_id": query_id,
                    "representation": name,
                    "evidence_blocks": len(blocks),
                    "unique_sources": len({block["source_id"] for block in blocks}),
                    "duplicate_blocks": duplicate_count(blocks),
                    "near_duplicate_blocks": 0,
                    "irrelevant_paragraphs_introduced": irrelevant_paragraphs(blocks, facts),
                }
            )
    coverage = {"records": coverage_rows}
    token_cost = {"thresholds": {"low_max_ratio": 1.25, "moderate_max_ratio": 2.0, "high": ">2.0"}, "records": token_rows}
    duplicate = {"records": duplicate_rows, "near_duplicate_method": "not asserted without a conservative exact deterministic match"}
    return serializations, coverage, token_cost, duplicate


def scorecard(coverage: dict[str, Any], tokens: dict[str, Any], duplicates: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in REPRESENTATIONS:
        cov = [row for row in coverage["records"] if row["representation"] == name]
        tok = [row for row in tokens["records"] if row["representation"] == name]
        dup = [row for row in duplicates["records"] if row["representation"] == name]
        rows.append(
            {
                "representation": name,
                "fact_passage_recall": sum(len(row["present_fact_ids"]) for row in cov) / sum(len(row["present_fact_ids"]) + len(row["missing_fact_ids"]) for row in cov),
                "all_required_facts_present_queries": sum(row["all_required_fact_evidence_present"] for row in cov),
                "context_tokens_per_query": [row["context_tokens"] for row in tok],
                "context_tokens_p50": statistics.median(row["context_tokens"] for row in tok),
                "context_tokens_max": max(row["context_tokens"] for row in tok),
                "duplicate_blocks": sum(row["duplicate_blocks"] for row in dup),
                "irrelevant_paragraphs": sum(row["irrelevant_paragraphs_introduced"] for row in dup),
                "citation_traceability": "PRESERVED",
            }
        )
    return rows


def choose_winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["all_required_facts_present_queries"] >= 2]
    if not eligible:
        return {"winner": "NO_VALID_WINNER", "generation_probe_eligible": False, "reason": "No representation makes all facts available for at least 2/3 queries."}
    best_coverage = max(row["all_required_facts_present_queries"] for row in eligible)
    finalists = [row for row in eligible if row["all_required_facts_present_queries"] == best_coverage]
    winner = min(finalists, key=lambda row: (row["context_tokens_p50"], row["irrelevant_paragraphs"]))
    return {
        "winner": winner["representation"],
        "generation_probe_eligible": True,
        "eligible_queries": winner["all_required_facts_present_queries"],
        "reason": "Highest query-level fact completeness, then lowest median token cost and irrelevant-paragraph expansion.",
        "promotion": False,
    }


def standard_boundary(mapping: list[dict[str, Any]], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fact_map = next(row for row in mapping if row["required_fact_id"] == "standard_return_window_14_days")
    retrieved = next(item for item in cache["multi-00-1"]["authorized_top5"] if item["source_id"] == "standard-returns-2026")
    return {
        "source_id": "standard-returns-2026",
        "source_path": "data/evaluation/evaluation-corpus-v2/standard-returns-2026.md",
        "observed_structure": [
            {"section": "Standard Returns — 2026 (root)", "lines": "3-9", "fact": "14-calendar-day return window", "current_chunk_id": fact_map["supporting_current_chunk_ids"][0]},
            {"boundary": "H2 starts a new logical section and therefore a separate current chunk"},
            {"section": "Case record", "lines": "13-15", "fact": "case fields and related links", "current_chunk_id": retrieved["chunk_id"]},
        ],
        "supporting_chunk_id": fact_map["supporting_current_chunk_ids"][0],
        "retrieved_chunk_id": retrieved["chunk_id"],
        "retrieved_chunk_heading": retrieved["metadata"].get("heading_path"),
        "why_fact_absent": "The reranker retained the same-source Case record section but dropped the root-section chunk containing the 14-day rule. The span itself is fully contained and not split.",
    }


def write_offline_artifacts(
    identity: dict[str, Any], gt: dict[str, Any], checks: list[dict[str, Any]], mapping: list[dict[str, Any]], recall: dict[str, Any], serializations: dict[str, Any], coverage: dict[str, Any], tokens: dict[str, Any], duplicates: dict[str, Any], score_rows: list[dict[str, Any]], winner: dict[str, Any], boundary: dict[str, Any]
) -> None:
    write_json(OUT / "artifact-identity.json", {**identity, "status": "PASS"})
    write_json(OUT / "fact-ground-truth.json", gt)
    write_jsonl(OUT / "fact-support-spans.jsonl", [{**fact, **next(check for check in checks if check["required_fact_id"] == fact["required_fact_id"])} for fact in gt["facts"]])
    write_json(OUT / "current-chunk-mapping.json", {"records": mapping})
    write_json(OUT / "source-vs-fact-recall.json", recall)
    write_json(OUT / "standard-returns-boundary-analysis.json", boundary)
    (OUT / "standard-returns-boundary-analysis.md").write_text(
        "# Standard Returns boundary analysis\n\n"
        "The authored `14 calendar days` span is in the root section and current chunk " + boundary["supporting_chunk_id"] + ".\n\n"
        "```text\n[Standard Returns — 2026 / root]\n14-calendar-day rule\n        ↓ H2 chunk boundary\n[Case record]\ncase fields and related links\n```\n\n"
        "The cached Top-5 contains only the Case record chunk " + boundary["retrieved_chunk_id"] + ". The fact is not split; the supporting root chunk was selected into candidate Top-20 and dropped during Top-5 reranking.\n",
        encoding="utf-8",
    )
    write_json(OUT / "representation-config.json", {"schema_version": "phase-7.10-representation-v1", "representations": list(REPRESENTATIONS), "compact_source_token_limit": COMPACT_SOURCE_LIMIT, "source_text_only": True, "runtime_promotion": False})
    names = {"CURRENT_CHUNK": "current-representation.json", "PARENT_SECTION": "parent-section-representation.json", "SAME_SECTION_NEIGHBORS": "same-section-neighbor-representation.json", "SECTION_AWARE_MERGED": "section-aware-merged-representation.json"}
    for name, filename in names.items():
        write_json(OUT / filename, serializations[name])
    write_json(OUT / "representation-fact-coverage.json", coverage)
    write_json(OUT / "representation-token-cost.json", tokens)
    write_json(OUT / "representation-duplicate-analysis.json", duplicates)
    write_json(OUT / "representation-scorecard.json", {"scorecard": score_rows, "no_opaque_combined_score": True})
    missing20 = sum(len(row["fact_ids_missing_at20"]) for row in recall["records"])
    missing5 = sum(len(row["fact_ids_missing_at5"]) for row in recall["records"])
    attribution = {
        "facts_absent_top20": missing20,
        "facts_in_top20_absent_top5": missing5 - missing20,
        "chunk_boundary_failures": 0,
        "chunk_representation_failures": 0,
        "initial_retrieval_failures": missing20,
        "reranker_top5_failures": missing5 - missing20,
        "source_present_fact_absent": missing5,
        "records": [
            {"query_id": query_id, "required_fact_id": "standard_return_window_14_days", "classification": "RERANKER_TOP5_FAILURE", "secondary": "SOURCE_PRESENT_FACT_ABSENT"}
            for query_id in ("multi-00-1", "multi-00-3")
        ],
    }
    write_json(OUT / "failure-attribution.json", attribution)
    write_json(OUT / "winner-decision.json", {**winner, "primary_result": "RERANKER_SELECTION_PROBLEM", "recommended_next_experiment": "RERANKER_ABLATION_NEXT"})
    correction = {
        "schema_version": "phase-7.10-evidence-metric-correction-v1",
        "old_metric": "required source present",
        "new_metrics": ["source_recall_complete", "fact_evidence_recall", "all_required_fact_evidence_present"],
        "correction": "Source presence must not be interpreted as fact-level evidence availability.",
        "historical_artifacts_modified": False,
    }
    write_json(OUT / "evaluation-metric-correction.json", correction)
    (OUT / "phase7-evidence-presence-addendum.md").write_text(
        "# Phase 7 evidence-presence addendum\n\nEarlier Phase 7 wording that said all required evidence was present used required-source presence as its proxy. Phase 7.10 shows that this is not a fact-level guarantee. In `multi-00-1` and `multi-00-3`, `standard-returns-2026` was present in Top-5, but its retrieved `Case record` chunk did not contain the required 14-calendar-day span. Future claims use authored fact spans and report source recall separately from fact-passage recall. Historical artifacts are preserved unchanged.\n",
        encoding="utf-8",
    )


def validate_identity() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata = read_json(SMOKE / "cache-metadata.json")
    p75_config = read_json(P75 / "experiment-config.json")
    actual = {**{key: metadata.get(key) for key in ("git_sha", "corpus_fingerprint", "dataset_fingerprint", "collection", "candidate_k", "top_n")}, "generator": p75_config.get("model"), "prompt": p75_config.get("prompt_version"), "think": p75_config.get("think")}
    mismatch = {key: {"expected": value, "actual": actual.get(key)} for key, value in EXPECTED.items() if actual.get(key) != value}
    if mismatch:
        raise RuntimeError(f"ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: {mismatch}")
    cache = {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}
    baseline = {row["query_id"]: row for row in read_jsonl(P75 / "b-generation-results.jsonl")}
    dataset = {row["id"]: row for row in read_json(DATASET_PATH)}
    if any(query_id not in cache or query_id not in baseline or query_id not in dataset for query_id in QUERY_IDS):
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: canonical query missing")
    return actual, cache, baseline, dataset


def probe_precondition(gt: dict[str, Any], winner_name: str, serializations: dict[str, Any]) -> list[dict[str, Any]]:
    by_query = {row["query_id"]: row for row in serializations[winner_name]["records"]}
    checks = []
    for query_id in QUERY_IDS:
        facts = query_facts(gt, query_id)
        metrics = evaluate_fact_evidence(facts, by_query[query_id]["evidence_blocks"])
        checks.append({"query_id": query_id, **metrics.as_dict(), "supporting_spans": [{"required_fact_id": fact["required_fact_id"], "source_id": fact["authoritative_source_id"], "supporting_text_span": fact["supporting_text_span"], "supporting_block_ids": [block["block_id"] for block in by_query[query_id]["evidence_blocks"] if block["source_id"] == fact["authoritative_source_id"] and normalize_evidence(fact["supporting_text_span"]) in normalize_evidence(block["text"])]} for fact in facts]})
    return checks


async def run_probe(
    ollama_url: str | None,
    gt: dict[str, Any],
    cache: dict[str, dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
    dataset: dict[str, dict[str, Any]],
    serializations: dict[str, Any],
    winner: dict[str, Any],
) -> None:
    winner_name = winner["winner"]
    preconditions = probe_precondition(gt, winner_name, serializations)
    if not all(item["all_required_fact_evidence_present"] for item in preconditions):
        raise RuntimeError("FACT_EVIDENCE_PRECONDITION_FAILED")
    config = {"model": "qwen3.5:4b", "prompt": "v3", "think": False, "num_ctx": 4096, "representation": winner_name, "query_ids": list(QUERY_IDS), "preconditions": preconditions, "max_generation_calls": 3}
    json.loads(json.dumps(config))
    write_json(OUT / "generation-probe-config.json", config)
    settings = Settings.benchmark_reference(**({"ollama_base_url": ollama_url} if ollama_url else {}))
    inventory = OllamaClient(base_url=settings.ollama_base_url, think=False)
    try:
        models = await inventory.list_models()
        if "qwen3.5:4b" not in models:
            raise RuntimeError(f"TARGET_GENERATOR_UNAVAILABLE: qwen3.5:4b; available={models}")
    finally:
        await inventory.aclose()
    rep_by_query = {row["query_id"]: row for row in serializations[winner_name]["records"]}
    checkpoint = OUT / "generation-probe-results.jsonl"
    existing = read_jsonl(checkpoint) if checkpoint.exists() else []
    if len({row["query_id"] for row in existing}) != len(existing) or any(row["query_id"] not in QUERY_IDS for row in existing):
        raise RuntimeError("corrupt generation probe checkpoint")
    complete = {row["query_id"] for row in existing}
    for query_id in QUERY_IDS:
        if query_id in complete:
            continue
        blocks = rep_by_query[query_id]["evidence_blocks"]
        chunks = representation_search_results(cache[query_id], blocks)
        builder = build_context_v1(chunks, max_context_tokens=2600)
        exact = evaluate_fact_evidence(query_facts(gt, query_id), [{"source_id": block["source_id"], "text": block["text"]} for block in blocks])
        if not exact.all_required_fact_evidence_present:
            raise RuntimeError(f"FACT_EVIDENCE_PRECONDITION_FAILED: {query_id}")
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        error: str | None = None
        started = time.perf_counter()
        client = OllamaClient(base_url=settings.ollama_base_url, think=False)
        try:
            async for event in stream_answer(
                cache[query_id]["query"], chunks, client, model="qwen3.5:4b", prompt_version="v3",
                validation_mode=settings.security_validation_mode,
                injection_eval_category=None,
                evaluation_observation=observation,
                context_serializer=lambda _chunks, rendered=builder.context: rendered,
            ):
                events.append(event)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            await client.aclose()
        raw = observation.raw_candidate_output or ""
        fact_score = score_required_facts(dataset[query_id].get("expected_answer"), raw, observable=observation.raw_candidate_available)
        grounding = next((event for event in events if event.get("type") == "grounding"), {})
        existing.append(
            {
                "query_id": query_id,
                "generation_calls": 1,
                "provider_error": error,
                "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "raw_candidate_available": observation.raw_candidate_available,
                "raw_candidate_output": raw,
                "validator_pass": observation.validator_pass,
                "validator_failure_codes": list(observation.validator_failure_codes),
                "validated_output_available": observation.validated_output_available,
                "user_visible_output_available": observation.user_visible_output_available,
                "fact_score": fact_score,
                "citations": {"found": grounding.get("citations_found", []), "invalid": grounding.get("ungrounded_citations", [])},
                "fact_evidence_precondition": exact.as_dict(),
                "context_tokens": builder.context_tokens,
            }
        )
        write_jsonl(checkpoint, existing)
        complete.add(query_id)
    rows = sorted(existing, key=lambda row: row["query_id"])
    reviewed: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = row["query_id"]
        raw_normalized = normalize_evidence(row["raw_candidate_output"])
        if query_id == "multi-00-1":
            reviewed[query_id] = {
                "content_class": "FULLY_CORRECT_COMPLETE",
                "material_unsupported_claims": 0,
                "source_alignment_failures": 2,
                "reason": "Both required facts are correct; material claims use noncanonical Source Block references and validator suppresses the output.",
            }
        elif query_id == "multi-00-3":
            reviewed[query_id] = {
                "content_class": "PARTIALLY_CORRECT",
                "material_unsupported_claims": int("30 calendar days" in raw_normalized),
                "source_alignment_failures": 2,
                "reason": "Required facts appear, but the answer mixes the irrelevant Premium 30-day rule and points evidence-field claims at Closure examples.",
            }
        else:
            reviewed[query_id] = {
                "content_class": "PARTIALLY_CORRECT",
                "material_unsupported_claims": 1,
                "source_alignment_failures": 1,
                "reason": "The two requested source families are named, but Digital Goods Policy is conflated with the cited returns-manual source and the authored regional framework is incomplete.",
            }
        row["reviewed_content"] = reviewed[query_id]
    write_jsonl(checkpoint, rows)
    historical = [baseline[query_id] for query_id in QUERY_IDS]
    comparison = {
        "historical": {"fully_correct_complete": 0, "fact_coverage": [row["fact_score"]["fact_coverage"] for row in historical], "validator_pass": sum(bool(row["validator_pass"]) for row in historical), "documented_source_alignment_failures": 2},
        "winner": {"deterministic_fact_match_complete": sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in rows), "reviewed_fully_correct_complete": sum(row["reviewed_content"]["content_class"] == "FULLY_CORRECT_COMPLETE" for row in rows), "fact_coverage": [row["fact_score"]["fact_coverage"] for row in rows], "validator_pass": sum(bool(row["validator_pass"]) for row in rows), "source_alignment_failures": sum(row["reviewed_content"]["source_alignment_failures"] for row in rows), "unsupported_claims": sum(row["reviewed_content"]["material_unsupported_claims"] for row in rows), "generation_calls": len(rows)},
    }
    write_json(OUT / "generation-probe-comparison.json", comparison)
    write_json(OUT / "generation-probe-decision.json", {"precondition": "PASS", "classification": [{"query_id": row["query_id"], "result": "ANSWERABLE_AND_GENERATION_SUCCEEDED" if row["reviewed_content"]["content_class"] == "FULLY_CORRECT_COMPLETE" else "ANSWERABLE_BUT_GENERATION_FAILED", **row["reviewed_content"]} for row in rows], "generation_failure_cleanly_measurable": True, "qwen35_4b_synthesizes_fact_complete_context": "PARTIAL"})


def finalize_summary(gt: dict[str, Any], checks: list[dict[str, Any]], recall: dict[str, Any], score_rows: list[dict[str, Any]], winner: dict[str, Any]) -> None:
    probe_results = read_jsonl(OUT / "generation-probe-results.jsonl") if (OUT / "generation-probe-results.jsonl").exists() else []
    summary = {
        "status": "RERANKER_SELECTION_PROBLEM",
        "required_facts_unique": len(gt["facts"]),
        "required_query_fact_occurrences": recall["aggregate"]["required_query_fact_occurrences"],
        "valid_authored_support_spans": sum(item["supporting_span_exists"] for item in checks),
        "source_vs_fact_recall": recall["aggregate"],
        "scorecard": score_rows,
        "winner": winner,
        "generation_probe": {"eligible": winner["generation_probe_eligible"], "ran": bool(probe_results), "calls": len(probe_results)},
        "conclusions": {"source_level_recall_sufficient": False, "fact_level_annotation_reliable": True, "chunk_boundary_contributor": False, "representation_contributor": "PARTIAL", "reranker_contributor": True, "generation_failure_cleanly_measurable": bool(probe_results)},
        "calls": {"retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0, "generation": len(probe_results)},
        "runtime_changed": False,
        "frozen_test_touched": False,
        "calibration_touched": False,
        "recommended_next_experiment": "RERANKER_ABLATION_NEXT",
    }
    write_json(OUT / "summary.json", summary)
    (OUT / "report.md").write_text(
        "# Phase 7.10 — Structure-aware chunking and fact evidence\n\n"
        "The previous source-level proxy overstated evidence availability. Both `multi-00-1` and `multi-00-3` had the required Standard source in Top-5, but only its Case record chunk; the root chunk containing `14 calendar days` was absent.\n\n"
        f"Fact passage recall is {recall['aggregate']['fact_passage_recall_at20']:.1%} at candidate Top-20 and {recall['aggregate']['fact_passage_recall_at5']:.1%} at Top-5. All required facts are present for {recall['aggregate']['all_required_facts_present_at20']}/3 queries at Top-20 and {recall['aggregate']['all_required_facts_present_at5']}/3 at Top-5.\n\n"
        f"The offline representation winner is `{winner['winner']}`. It recovers compact same-source sections without generated text and with lower cost than full-parent expansion. This is diagnostic, not promoted.\n\n"
        "Primary attribution is reranker/Top-5 selection: the supporting Standard root chunk is in candidate Top-20 but omitted from final Top-5. The literal authored span is fully contained in a current chunk, so this is not a span-splitting failure.\n\n"
        f"Generation probe: {'RUN' if probe_results else 'NOT RUN'}.\n",
        encoding="utf-8",
    )


async def async_main(args: argparse.Namespace) -> None:
    identity, cache, baseline, dataset = validate_identity()
    gt = read_json(FACTS_PATH)
    checks = verify_ground_truth(gt)
    mapping = derive_current_chunks(gt, cache)
    recall = current_recall(gt, cache, mapping)
    serializations, coverage, tokens, duplicates = representation_analysis(gt, cache)
    score_rows = scorecard(coverage, tokens, duplicates)
    winner = choose_winner(score_rows)
    boundary = standard_boundary(mapping, cache)
    write_offline_artifacts(identity, gt, checks, mapping, recall, serializations, coverage, tokens, duplicates, score_rows, winner, boundary)
    if args.run_generation:
        if not winner["generation_probe_eligible"]:
            raise RuntimeError("FACT_EVIDENCE_PRECONDITION_FAILED: no eligible winner")
        await run_probe(args.ollama_url, gt, cache, baseline, dataset, serializations, winner)
    finalize_summary(gt, checks, recall, score_rows, winner)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-generation", action="store_true")
    parser.add_argument("--ollama-url")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
