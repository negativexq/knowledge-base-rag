"""Shared, isolated helpers for the RAGBench eManual Basic-50 benchmark.

This module intentionally does not alter the application pipeline.  It adapts
the public RAGBench rows into the existing ingestion/retrieval/evidence and
V2.2 generation boundaries, while keeping all benchmark state below
``artifacts/ragbench``.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.models import Chunk
from app.llm.structured_output import (
    EVIDENCE_BACKED_OUTPUT_SCHEMA,
    EvidenceBackedValidation,
    render_evidence_backed_answer,
)
from app.retrieval.hybrid_search import SearchResult

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/ragbench/emanual-basic-50"
HF_REPO = "galileo-ai/ragbench"
HF_REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
HF_FILE = "emanual/test-00000-of-00001.parquet"
DATASET_URL = f"https://huggingface.co/datasets/{HF_REPO}/resolve/{HF_REVISION}/{HF_FILE}"
TENANT = "ragbench-emanual"
SEED = 42
SAMPLE_SIZE = 50
EMBED_MODEL = "qwen3-embedding:4b"
EMBED_DIM = 1024
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
GENERATOR_MODEL = "gpt-5.6-luna"
PROMPT_VERSION = "v3"
CONTRACT_VERSION = "output_contract_v2_2"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_rows(parquet_path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(parquet_path).to_pylist()
    for index, row in enumerate(rows):
        row["_row_index"] = index
    return sorted(rows, key=lambda row: str(row["id"]))


def row_identifier(row: dict[str, Any]) -> str:
    """Stable row identity when the public dataset's human ID is duplicated."""
    return f"{row['id']}#row-{int(row['_row_index']):04d}"


def choose_sample(
    rows: list[dict[str, Any]], seed: int = SEED, size: int = SAMPLE_SIZE
) -> list[dict[str, Any]]:
    import random

    if len(rows) < size:
        raise ValueError(f"dataset has {len(rows)} rows, cannot sample {size}")
    rng = random.Random(seed)
    chosen = rng.sample(rows, size)
    return sorted(chosen, key=lambda row: str(row["id"]))


def source_id_for(text: str) -> str:
    return "ragbench_emanual_doc_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def document_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts = {str(text) for row in rows for text in row.get("documents", [])}
    return [
        {
            "source_id": source_id_for(text),
            "document_version": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text,
            "tenant_id": TENANT,
        }
        for text in sorted(texts, key=lambda value: source_id_for(value))
    ]


def chunk_documents(docs: list[dict[str, Any]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        raw_chunks = chunk_markdown_text(
            doc["text"], doc["source_id"], "ragbench_emanual", doc["document_version"]
        )
        chunks.extend(replace(chunk, tenant_id=TENANT) for chunk in raw_chunks)
    return chunks


def relevant_sentence_map(row: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in row.get("documents_sentences") or []:
        for key, text in item or []:
            result[str(key)] = str(text)
    return result


def relevant_keys(row: dict[str, Any]) -> list[str]:
    return [str(key) for key in (row.get("all_relevant_sentence_keys") or [])]


def relevant_doc_indices(row: dict[str, Any]) -> set[int]:
    indices: set[int] = set()
    for key in relevant_keys(row):
        match = re.match(r"(\d+)", key)
        if match:
            indices.add(int(match.group(1)))
    return indices


def text_has_sentence(text: str, sentence: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_sentence = normalize_text(sentence)
    return bool(normalized_sentence) and normalized_sentence in normalized_text


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(value.split())


def truth_presence(
    row: dict[str, Any], results: list[SearchResult | dict[str, Any]]
) -> dict[str, Any]:
    sentence_map = relevant_sentence_map(row)
    keys = relevant_keys(row)
    texts: list[str] = []
    source_ids: set[str] = set()
    for result in results:
        payload = result.payload if isinstance(result, SearchResult) else result
        texts.append(str(payload.get("text", "")))
        if payload.get("source_id"):
            source_ids.add(str(payload["source_id"]))
    present = [
        key for key in keys if text_has_sentence("\n".join(texts), sentence_map.get(key, ""))
    ]
    return {
        "relevant_sentence_keys": keys,
        "present_sentence_keys": present,
        "missing_sentence_keys": [key for key in keys if key not in present],
        "sentence_recall": len(present) / len(keys) if keys else 0.0,
        "all_relevant_sentences_present": bool(keys) and len(present) == len(keys),
        "relevant_doc_indices": sorted(relevant_doc_indices(row)),
        "present_source_ids": sorted(source_ids),
    }


def serialize_result(result: SearchResult, *, rank: int, score_name: str) -> dict[str, Any]:
    payload = result.payload
    text = str(payload.get("text", ""))
    serialized = {
        "rank": rank,
        "chunk_id": result.id or payload.get("chunk_id"),
        "source_type": payload.get("source_type"),
        "source_id": payload.get("source_id"),
        "document_version": payload.get("document_version"),
        score_name: result.score,
        "tenant_id": payload.get("tenant_id"),
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
        "page_number": payload.get("page_number"),
        "paragraph_index": payload.get("paragraph_index"),
        "heading_path": payload.get("heading_path", []),
        "heading_occurrence": payload.get("heading_occurrence", 0),
    }
    # Evidence blocks carry additional server-generated provenance and budget
    # observability.  Preserve it when serializing replay snapshots while
    # keeping the historical anchor record shape backward compatible.
    for key in (
        "evidence_block_id",
        "contributing_chunk_ids",
        "citation_aliases",
        "section_aware",
        "section_key",
        "anchor_chunk_id",
        "token_count",
        "truncated",
        "original_token_count",
        "visible_token_count",
    ):
        if key in payload:
            serialized[key] = payload[key]
    return serialized


def deserialize_result(value: dict[str, Any], score_name: str = "score") -> SearchResult:
    payload = dict(value)
    score = float(payload.pop(score_name, value.get("score", 0.0)))
    result_id = str(payload.pop("chunk_id", ""))
    return SearchResult(score=score, payload=payload, id=result_id)


def answer_text(validation: EvidenceBackedValidation) -> str:
    return render_evidence_backed_answer(
        validation.valid_parts, abstain=validation.application_abstain
    )


def token_f1(prediction: str, reference: str) -> float:
    pred = normalize_text(prediction).split()
    ref = normalize_text(reference).split()
    if not pred or not ref:
        return 1.0 if pred == ref else 0.0
    counts: dict[str, int] = {}
    for token in ref:
        counts[token] = counts.get(token, 0) + 1
    overlap = 0
    for token in pred:
        if counts.get(token, 0):
            counts[token] -= 1
            overlap += 1
    if not overlap:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def score_benchmark(
    row: dict[str, Any], visible: str, validation: EvidenceBackedValidation
) -> dict[str, Any]:
    reference = str(row.get("response") or "")
    # Citation tags are a delivery/provenance concern, not answer content.
    # Score the validated claim text separately so benchmark references are
    # not penalized merely because the application appends [E1]-style tags.
    prediction = (
        "\n".join(part.text for part in validation.valid_parts) if validation.valid_parts else ""
    )
    exact = normalize_text(prediction) == normalize_text(reference)
    f1 = token_f1(prediction, reference)
    return {
        "reference_answer": reference,
        "normalized_exact_match": exact,
        "token_f1": round(f1, 6),
        "fully_correct": exact,
        "grounded_supported": bool(validation.valid_parts),
        "abstained": bool(validation.model_abstain or validation.application_abstain),
        "false_abstention": bool(
            (validation.model_abstain or validation.application_abstain) and reference
        ),
    }


def percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def summary_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "max": round(max(ordered), 3),
    }


def schema_hash() -> str:
    return canonical_hash(EVIDENCE_BACKED_OUTPUT_SCHEMA)
