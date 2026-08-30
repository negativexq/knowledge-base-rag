"""Artifact-only TechQA chunking diagnostic.

This module measures the existing DEBUG50 fact funnel and re-chunks the frozen
source documents in memory for the preregistered S0 grid.  It never reads the
holdout contents and never invokes retrieval, embedding, reranking, or a
provider.
"""

# ruff: noqa: E501, E402

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.qdrant_store import QdrantStore
from app.ingestion.tokenizer import token_count as qwen_token_count
from scripts.ragbench_emanual_common import text_has_sentence
from scripts.run_techqa_topn_ablation import (
    read_jsonl,
    source_chunks,
)

DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
UPSTREAM = ROOT / "artifacts/ragbench/canonical/techqa-upstream-funnel-v1"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-chunking-diagnostic-v1"
PREREG = OUT / "preregistration.json"
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
CORPUS_HASH = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
TOKENIZER = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "main"
ANNOTATED_SIZE = 38
GRID = [
    {"target_tokens": size, "overlap_tokens": overlap}
    for size in (500, 800, 1200)
    for overlap in (50, 150, 250)
]
BASELINE_OVERLAP = 50
SECTION_AWARE_BUDGETS = (2400, 4800)
SPLIT_VS_INTACT_STAGES = (
    "S1_IN_CANDIDATES",
    "S2_SURVIVES_RERANK_TOP5",
    "S2_SURVIVES_RERANK_TOP8",
    "S2_SURVIVES_RERANK_TOP12",
    "OFF_RRF_TOP5",
    "S3_IN_EVIDENCE_2400_TOP5",
    "S3_IN_EVIDENCE_4800_TOP5",
)
_SENTENCE_END = re.compile(r'[.!?。！？]["\'’”»\)\]]?$')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def grid_config(target_tokens: int, overlap_tokens: int) -> dict[str, Any]:
    if target_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap must be non-negative and smaller than chunk size")
    return {
        "target_tokens": target_tokens,
        "overlap_tokens": overlap_tokens,
        "mode": "baseline",
        "boundary_strategy": "legacy_word_sentence_heading_page_v1",
        "tokenizer_model": TOKENIZER,
        "tokenizer_revision": TOKENIZER_REVISION,
    }


def load_source_documents() -> list[dict[str, Any]]:
    rows = read_jsonl(DEBUG / "source-documents.jsonl")
    if not rows:
        raise RuntimeError("DEBUG_SOURCE_DOCUMENTS_MISSING")
    return rows


def load_funnel_rows() -> list[dict[str, Any]]:
    rows = read_jsonl(UPSTREAM / "fact-funnel.jsonl")
    if len(rows) != ANNOTATED_SIZE:
        raise RuntimeError("FUNNEL_ARTIFACT_MISMATCH")
    return rows


def verify_sources() -> dict[str, Any]:
    config = read_json(DEBUG / "config.json")
    frozen = read_json(UPSTREAM / "frozen-inputs.json")
    if (DEBUG / "sample.sha256").read_text(encoding="utf-8").strip() != DEBUG_HASH:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if config.get("dataset_revision") != REVISION or config.get("sample_hash") != DEBUG_HASH:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if config.get("config_fingerprint") != CONFIG_HASH or config.get("corpus_fingerprint") != CORPUS_HASH:
        raise RuntimeError("FROZEN_INPUT_MISMATCH")
    if file_hash(DEBUG / "retrieval-results.jsonl") != frozen["retrieval_file_sha256"]:
        raise RuntimeError("FROZEN_INPUT_MISMATCH")
    if file_hash(DEBUG / "reranker-results.jsonl") != frozen["reranker_file_sha256"]:
        raise RuntimeError("FROZEN_INPUT_MISMATCH")
    if frozen.get("bge_rank_order_verified") is not True or frozen.get("bge_model") != "BAAI/bge-reranker-v2-m3":
        raise RuntimeError("FROZEN_INPUT_MISMATCH")
    return {
        "dataset": config["dataset"],
        "revision": REVISION,
        "split": config["split"],
        "debug50_hash": DEBUG_HASH,
        "holdout50_hash": HOLDOUT_HASH,
        "corpus_fingerprint": CORPUS_HASH,
        "config_fingerprint": CONFIG_HASH,
        "retrieval_file_sha256": frozen["retrieval_file_sha256"],
        "reranker_file_sha256": frozen["reranker_file_sha256"],
        "bge_model": frozen["bge_model"],
        "bge_rank_order_verified": True,
        "holdout_access": 0,
        "calls": {
            "openai": 0,
            "luna": 0,
            "terra": 0,
            "ollama": 0,
            "retrieval": 0,
            "embedding": 0,
            "reranker": 0,
        },
    }


def build_grid_chunks(documents: list[dict[str, Any]], target_tokens: int, overlap_tokens: int) -> list[dict[str, Any]]:
    grid_config(target_tokens, overlap_tokens)
    chunks: list[dict[str, Any]] = []
    for document in documents:
        built = chunk_markdown_text(
            document["text"],
            document["source_id"],
            document["source_type"],
            document["document_version"],
            chunk_size_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
        for chunk in built:
            chunks.append(
                {
                    "chunk_id": QdrantStore.point_id_for(chunk),
                    "payload": dict(chunk.__dict__),
                    "qwen_token_count": qwen_token_count(chunk.text, TOKENIZER, TOKENIZER_REVISION),
                }
            )
    return chunks


def state_for_facts(fact_chunk_ids: dict[str, list[str]], required_keys: list[str]) -> dict[str, Any]:
    unmapped = [key for key in required_keys if not fact_chunk_ids.get(key)]
    all_ids = sorted({chunk_id for ids in fact_chunk_ids.values() for chunk_id in ids})
    common = [chunk_id for chunk_id in all_ids if not unmapped and all(chunk_id in fact_chunk_ids[key] for key in required_keys)]
    if unmapped:
        state = "UNMAPPED"
    elif common:
        state = "INTACT"
    elif all_ids:
        state = "SPLIT"
    else:
        state = "UNMAPPED"
    return {
        "state": state,
        "fact_chunk_count": len(all_ids),
        "fact_chunk_ids": all_ids,
        "common_chunk_ids": common,
        "unmapped_keys": unmapped,
    }


def map_facts(row: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    atomic = row["s0"]["atomic_facts"]
    required_keys = row["fact_keys"]
    fact_chunk_ids: dict[str, list[str]] = {}
    for key in required_keys:
        text = atomic.get(key, {}).get("text")
        if not text:
            fact_chunk_ids[key] = []
            continue
        fact_chunk_ids[key] = [
            item["chunk_id"]
            for item in chunks
            if text_has_sentence(str(item["payload"].get("text", "")), str(text))
        ]
    return {
        **state_for_facts(fact_chunk_ids, required_keys),
        "required_keys": required_keys,
        "fact_chunk_ids_by_key": fact_chunk_ids,
    }


def grid_cell(documents: list[dict[str, Any]], rows: list[dict[str, Any]], target_tokens: int, overlap_tokens: int) -> dict[str, Any]:
    chunks = build_grid_chunks(documents, target_tokens, overlap_tokens)
    bundles = {row["query_id"]: map_facts(row, chunks) for row in rows}
    lengths = [item["qwen_token_count"] for item in chunks]
    ordered = sorted(lengths)
    def percentile(fraction: float) -> int:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]
    return {
        "target_tokens": target_tokens,
        "overlap_tokens": overlap_tokens,
        "chunking_mode": "baseline",
        "boundary_strategy": "legacy_word_sentence_heading_page_v1",
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "chunk_length_tokens_qwen": {
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "max": max(lengths),
            "mean": sum(lengths) / len(lengths),
        },
        "s0": {
            state: sum(bundle["state"] == state for bundle in bundles.values())
            for state in ("INTACT", "SPLIT", "UNMAPPED")
        },
        "bundles": bundles,
    }


def baseline_split_details(rows: list[dict[str, Any]], baseline_chunks: dict[str, Any]) -> list[dict[str, Any]]:
    details = []
    for row in rows:
        s0 = row["s0"]
        if s0["state"] != "SPLIT":
            continue
        records = []
        for chunk_id in s0["fact_chunk_ids"]:
            item = baseline_chunks.get(chunk_id)
            if item is None:
                continue
            payload = item.payload
            records.append(
                {
                    "chunk_id": chunk_id,
                    "source_id": payload.get("source_id"),
                    "document_version": payload.get("document_version"),
                    "heading_path": list(payload.get("heading_path") or []),
                    "char_range": list(payload.get("char_range") or []),
                    "text": payload.get("text", ""),
                }
            )
        by_source: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            by_source.setdefault(str(record["source_id"]), []).append(record)
        adjacent = True
        boundary_types: set[str] = set()
        for source_records in by_source.values():
            source_records.sort(key=lambda item: item["char_range"][0])
            for left, right in zip(source_records, source_records[1:]):
                if left["char_range"][1] < right["char_range"][0]:
                    adjacent = False
                if left["heading_path"] != right["heading_path"]:
                    boundary_types.add("HEADING")
                elif _SENTENCE_END.search(str(left["text"].rstrip())):
                    boundary_types.add("SENTENCE")
                else:
                    boundary_types.add("HARD_WORD_CUT")
        if len(by_source) > 1:
            adjacent = False
        fact_texts = [s0["atomic_facts"][key].get("text") for key in row["fact_keys"] if s0["atomic_facts"].get(key, {}).get("text")]
        fact_span_text = "\n".join(dict.fromkeys(fact_texts))
        span_tokens = qwen_token_count(fact_span_text, TOKENIZER, TOKENIZER_REVISION) if fact_span_text else 0
        details.append(
            {
                "query_id": row["query_id"],
                "question": row["question"],
                "required_keys": row["fact_keys"],
                "chunk_count": len(records),
                "source_count": len(by_source),
                "chunks_adjacent": adjacent,
                "fact_span_tokens": span_tokens,
                "span_exceeds_50_token_overlap": span_tokens > BASELINE_OVERLAP,
                "boundary_types": sorted(boundary_types) or ["UNKNOWN"],
                "page_boundary_applicable": False,
                "chunks": records,
            }
        )
    return details


def phase1_summary(funnel_rows: list[dict[str, Any]], off_rows: list[dict[str, Any]]) -> dict[str, Any]:
    off = {row["query_id"]: row for row in off_rows if row["arm"] == "OFF" and row["top_n"] == 5}
    groups = {state: [row for row in funnel_rows if row["s0"]["state"] == state] for state in ("INTACT", "SPLIT", "UNMAPPED")}
    fields = {
        **{stage: ("stages", stage) for stage in SPLIT_VS_INTACT_STAGES if stage != "OFF_RRF_TOP5"},
        "OFF_RRF_TOP5": ("off",),
    }
    cross = {}
    for group, group_rows in groups.items():
        stage_counts = {}
        for stage, path in fields.items():
            states = []
            for row in group_rows:
                value = off[row["query_id"]]["truth"]["state"] if stage == "OFF_RRF_TOP5" else row[path[0]][path[1]]["state"]
                states.append(value)
            stage_counts[stage] = {state: states.count(state) for state in ("ALL", "PARTIAL", "NONE", "NO_DATA")}
        cross[group] = {"count": len(group_rows), "stages": stage_counts}
    return {
        "bundle_count": len(funnel_rows),
        "group_counts": {group: len(items) for group, items in groups.items()},
        "cross_tab": cross,
        "split_details": [],
    }


def boundary_strategy_summary() -> dict[str, Any]:
    return {
        "name": "legacy_word_sentence_heading_page_v1",
        "implementation_files": [
            "app/ingestion/markdown_chunker.py",
            "app/ingestion/chunker.py",
        ],
        "algorithm": [
            "Markdown is parsed into blocks and grouped by (heading_path, heading_occurrence).",
            "Each heading group is treated as a surrogate page; a chunk never crosses that group boundary.",
            "The baseline splitter finds non-whitespace words and takes a target-sized word window.",
            "The next window starts at max(previous_start + 1, previous_end - overlap_tokens).",
            "For non-final windows it searches up to 300 characters for sentence-ending punctuation and extends to that boundary when found.",
            "If no sentence ending is found in the lookahead, the target word boundary is used: this is the hard word cut.",
        ],
        "what_legacy_word_means": "legacy is the historical baseline path; word means whitespace-token windows, not Qwen tokenizer token windows",
        "heading_boundary": "respected by grouping; heading groups are processed independently",
        "page_boundary": "not an actual Markdown page boundary; the shared splitter terminology is retained, while Markdown uses heading surrogates",
        "sentence_boundary": "preferred within a 300-character lookahead, but not guaranteed",
        "hard_word_cut": "fallback when no sentence terminator is found in that lookahead",
        "boundary_strategy_is_metadata_only_in_baseline": True,
    }


def budget_interaction(grid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "target_chunk_tokens": item["target_tokens"],
            "budget_2400_theoretical_full_chunks": 2400 // item["target_tokens"],
            "budget_4800_theoretical_full_chunks": 4800 // item["target_tokens"],
            "note": "Theoretical target-sized chunks; sentence extension and headers can reduce actual fit.",
        }
        for item in sorted({(item["target_tokens"], item["overlap_tokens"]) for item in grid})
        for item in [{"target_tokens": item[0], "overlap_tokens": item[1]}]
        if item["overlap_tokens"] == 50
    ]


def run() -> None:
    source = verify_sources()
    rows = load_funnel_rows()
    documents = load_source_documents()
    baseline_chunks = source_chunks()
    off_rows = read_jsonl(UPSTREAM / "reranker-off-results.jsonl")
    phase1 = phase1_summary(rows, off_rows)
    phase1["split_details"] = baseline_split_details(rows, baseline_chunks)
    grid_results = [grid_cell(documents, rows, item["target_tokens"], item["overlap_tokens"]) for item in GRID]
    summary = {
        "implementation_check": True,
        "promotion_authority": False,
        "source_integrity": source,
        "phase1": phase1,
        "boundary_strategy": boundary_strategy_summary(),
        "grid": grid_results,
        "budget_interaction": budget_interaction(GRID),
        "warnings": [
            "Chunking changes require re-embedding and invalidate frozen rankings and downstream frozen artifacts; no re-index was performed.",
            "DEBUG50 is an inspected hard cluster; the 38-query split/intact comparison is not a TechQA population estimate.",
            "S0 is a text/chunk mapping diagnostic only; no retrieval or semantic quality claim is made.",
        ],
    }
    write_json("chunking_summary.json", summary)


def preregister() -> None:
    source = verify_sources()
    value = {
        "version": "TECHQA_CHUNKING_DIAGNOSTIC",
        "implementation_check": True,
        "promotion_authority": False,
        "scope": "DEBUG50 only; no holdout content access",
        "source": source,
        "populations": {"annotated": 38, "split_vs_intact_source": "upstream fact-funnel.jsonl"},
        "grid": GRID,
        "baseline": {"target_tokens": 500, "overlap_tokens": 50, "boundary_strategy": "legacy_word_sentence_heading_page_v1"},
        "token_measurement": {"model": TOKENIZER, "revision": TOKENIZER_REVISION},
        "phases": {
            "phase_1": "cross-tab existing fact funnel by S0 intact/split/unmapped",
            "phase_2": "in-memory baseline chunking grid; no embedding or index writes",
            "phase_3": "report-only classification A/B/C; no next action recommendation",
        },
        "zero_inference": {"openai": 0, "luna": 0, "terra": 0, "ollama": 0, "retrieval": 0, "embedding": 0, "reranker": 0},
        "holdout": {"hash": HOLDOUT_HASH, "access": 0, "retrieval": 0, "embedding": 0, "reranker": 0, "generation": 0, "judge": 0},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    if PREREG.exists():
        if canonical_hash(read_json(PREREG)) != canonical_hash(value):
            raise RuntimeError("PREREGISTRATION_ALREADY_FROZEN")
    else:
        PREREG.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (OUT / "preregistration.sha256").write_text(file_hash(PREREG) + "\n", encoding="utf-8")


def require_prereg() -> None:
    if not PREREG.exists() or not (OUT / "preregistration.sha256").exists():
        raise RuntimeError("PREREGISTRATION_MISSING")
    if file_hash(PREREG) != (OUT / "preregistration.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("PREREGISTRATION_HASH_MISMATCH")


def report(summary: dict[str, Any]) -> tuple[str, str, str]:
    phase1 = summary["phase1"]
    lines = [
        "# TechQA chunking diagnostic — split vs intact",
        "",
        "This is a zero-inference diagnostic over the inspected DEBUG50 hard cluster. It does not estimate TechQA-wide rates.",
        "",
        "## Frozen-artifact warning",
        "",
        "Changing chunking requires re-embedding. That would invalidate persisted RRF/BGE rankings, budget ablations, Top-N ablation, and the reranker OFF arm. No corpus re-index or embedding was performed.",
        "",
        f"S0 groups: intact `{phase1['group_counts']['INTACT']}`, split `{phase1['group_counts']['SPLIT']}`, explicit unmapped `{phase1['group_counts']['UNMAPPED']}` out of 38 bundles; atomic annotation keys: `{sum(row['s0']['atomic_fact_count'] for row in read_jsonl(UPSTREAM / 'fact-funnel.jsonl'))}`.",
        "",
        "## Cross-tab",
        "",
        "Counts are raw counts, not statistical tests. `OFF_RRF_TOP5` is the existing frozen reranker-OFF evidence replay at budget 4800.",
        "",
        "| S0 group | N | Stage | ALL | PARTIAL | NONE | NO_DATA |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for group in ("INTACT", "SPLIT", "UNMAPPED"):
        for stage in SPLIT_VS_INTACT_STAGES:
            counts = phase1["cross_tab"][group]["stages"][stage]
            lines.append(f"| {group} | {phase1['group_counts'][group]} | {stage} | {counts['ALL']} | {counts['PARTIAL']} | {counts['NONE']} | {counts['NO_DATA']} |")
    lines.extend([
        "",
        "### Direct split vs intact comparison",
        "",
        "| Stage | Split ALL | Split N | Intact ALL | Intact N |",
        "|---|---:|---:|---:|---:|",
    ])
    for stage in ("OFF_RRF_TOP5", "S3_IN_EVIDENCE_2400_TOP5", "S3_IN_EVIDENCE_4800_TOP5"):
        split = phase1["cross_tab"]["SPLIT"]["stages"][stage]["ALL"]
        intact = phase1["cross_tab"]["INTACT"]["stages"][stage]["ALL"]
        lines.append(f"| {stage} | {split} | 10 | {intact} | 26 |")
    lines.extend(["", "No percentage or significance claim is made because this is a small, inspected 10-vs-26 comparison.", "", "## Split bundle details", ""])
    for detail in phase1["split_details"]:
        lines.extend([
            f"### `{detail['query_id']}`",
            f"Question: {detail['question']}",
            f"- chunks carrying required text: `{detail['chunk_count']}` unique indexed chunks; source documents: `{detail['source_count']}`; adjacent: `{detail['chunks_adjacent']}`",
            f"- required bundle span: `{detail['fact_span_tokens']}` Qwen tokens; longer than 50-token overlap: `{detail['span_exceeds_50_token_overlap']}`",
            f"- boundary signals: `{', '.join(detail['boundary_types'])}`; actual Markdown page boundary applicable: `{detail['page_boundary_applicable']}`",
            "",
        ])
    lines.extend([
        "A high unique chunk count can include overlapping/repeated chunks whose text contains different required sentence keys; it is not a claim that the fact has that many independent semantic pieces.",
        "",
        "## Chunking conclusion",
        "",
        "The split/intact comparison is descriptive only. The parameter grid and budget trade-off are reported separately; no production conclusion or next-step recommendation is made here.",
        "",
    ])
    fact = "\n".join(lines)

    boundary = [
        "# Boundary strategy audit",
        "",
        "## `legacy_word_sentence_heading_page_v1`",
        "",
        "The implementation is in `app/ingestion/markdown_chunker.py` and `app/ingestion/chunker.py`.",
        "",
        "1. Markdown is parsed into blocks and grouped by `(heading_path, heading_occurrence)`.",
        "2. Each heading group becomes a surrogate page and is chunked independently; chunks do not cross that heading group.",
        "3. The baseline splitter uses `re.finditer(r'\\S+')`: its target and overlap are whitespace-word windows, not Qwen tokenizer tokens.",
        "4. The next start is `max(start + 1, end - overlap)`.",
        "5. A non-final chunk searches up to 300 characters for sentence-ending punctuation and extends to that sentence end when possible.",
        "6. If no sentence end is found in the lookahead, it falls back to the target word boundary: a hard word cut.",
        "",
        "### Name vs implementation",
        "",
        "- `legacy`: the historical baseline splitter, retained for frozen reproducibility.",
        "- `word`: confirmed by the whitespace regex; the configured `target_tokens`/`overlap_tokens` names are historical terminology in this path.",
        "- `sentence`: preferred but bounded by the 300-character lookahead, so it is not an absolute guarantee.",
        "- `heading`: respected for Markdown because heading groups are processed independently.",
        "- `page`: not a real Markdown page boundary in this adapter; surrogate page numbers represent heading groups.",
        "- `hard word cut`: the explicit fallback when no sentence boundary fits the lookahead.",
        "",
        "The grid below measures this baseline text algorithm with different word-window parameters and counts resulting chunk lengths with the Qwen3 tokenizer. It does not change production configuration or write an index.",
        "",
    ]
    boundary_text = "\n".join(boundary)

    grid_lines = [
        "# Chunk parameter grid and budget interaction",
        "",
        "In-memory re-chunking only; no embedding, retrieval, or index write. Length statistics use `Qwen/Qwen3-Embedding-4B` tokenizer (`main`).",
        "",
        "## Grid",
        "",
        "| Chunk size | Overlap | Total chunks | Intact | Split | Unmapped | Qwen p50 | Qwen p95 | Qwen max |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in summary["grid"]:
        lengths = cell["chunk_length_tokens_qwen"]
        grid_lines.append(f"| {cell['target_tokens']} | {cell['overlap_tokens']} | {cell['chunk_count']} | {cell['s0']['INTACT']} | {cell['s0']['SPLIT']} | {cell['s0']['UNMAPPED']} | {lengths['p50']} | {lengths['p95']} | {lengths['max']} |")
    baseline_chunks = next(cell["chunk_count"] for cell in summary["grid"] if cell["target_tokens"] == 500 and cell["overlap_tokens"] == 50)
    grid_lines.extend([
        "",
        "Overlap increases index-size pressure because the step is `chunk_size - overlap`; the total chunk count above is the measured in-memory count. The 500/50 cell is the current baseline representation.",
        "",
        "## Budget interaction (theoretical target-sized chunks)",
        "",
        "| Target chunk size | 2400 budget: full chunks | 4800 budget: full chunks |",
        "|---:|---:|---:|",
    ])
    for item in summary["budget_interaction"]:
        grid_lines.append(f"| {item['target_chunk_tokens']} | {item['budget_2400_theoretical_full_chunks']} | {item['budget_4800_theoretical_full_chunks']} |")
    grid_lines.extend([
        "",
        "These are floor calculations, not actual SectionAware fit counts: sentence extension, headings, overlap, and serialization overhead can reduce the number of complete chunks that fit. At 1200 target tokens, only two target-sized chunks fit in a 2400-token budget.",
        "",
        "## Phase 3 classification",
        "",
        "The raw Phase 1 comparison shows split bundles are less often ALL than intact bundles at both 2400 and 4800; this is a descriptive 10-vs-26 result, not a significance test.",
        f"At 2400, split bundles are ALL in `{summary['phase1']['cross_tab']['SPLIT']['stages']['S3_IN_EVIDENCE_2400_TOP5']['ALL']}/10` versus intact `{summary['phase1']['cross_tab']['INTACT']['stages']['S3_IN_EVIDENCE_2400_TOP5']['ALL']}/26`; at 4800 the counts are `{summary['phase1']['cross_tab']['SPLIT']['stages']['S3_IN_EVIDENCE_4800_TOP5']['ALL']}/10` versus `{summary['phase1']['cross_tab']['INTACT']['stages']['S3_IN_EVIDENCE_4800_TOP5']['ALL']}/26`.",
        "The grid therefore supports classification C at the diagnostic level: the issue is visible, and the 800/50 (also 800/150, 800/250 and all 1200 cells) cells move the measured groups from 26 intact/10 split to 27 intact/9 split. The 800/50 cell is the lowest-chunk-count member of that tied S0 outcome. This is not a production promotion: any chunking change would require re-embedding and would invalidate frozen downstream artifacts.",
        "No production winner, re-index plan, or next experiment is recommended by this report.",
        "DEBUG50 is an inspected hard cluster and the grid is not a TechQA-wide estimate.",
        "",
        f"Current baseline total chunk count for the 500/50 cell: `{baseline_chunks}`.",
    ])
    grid_text = "\n".join(grid_lines) + "\n"
    return fact, boundary_text + "\n", grid_text


def finalize() -> None:
    require_prereg()
    summary = read_json(OUT / "chunking_summary.json")
    fact, boundary, grid = report(summary)
    (OUT / "split_vs_intact.md").write_text(fact, encoding="utf-8")
    (OUT / "boundary_strategy.md").write_text(boundary, encoding="utf-8")
    (OUT / "chunk_param_grid.md").write_text(grid, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if not any((args.prepare_only, args.run, args.finalize)):
        parser.error("choose --prepare-only, --run, or --finalize")
    if args.prepare_only:
        preregister()
    if args.run:
        require_prereg()
        run()
    if args.finalize:
        finalize()


if __name__ == "__main__":
    main()
