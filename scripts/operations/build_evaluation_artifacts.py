# ruff: noqa: E501

"""Build derived Evaluation Corpus v2 artifacts from committed source files.

This module is deliberately read-only with respect to the corpus, manifest, and
golden dataset. It measures and fingerprints those assets; it never authors
documents or questions and never performs model inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.evaluation.dataset_fingerprint import (
    evaluation_corpus_fingerprint,
    evaluation_dataset_fingerprint,
)
from app.ingestion.chunker import chunk_document
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.parsing.pdf_parser import extract_paragraphs
from scripts.operations.evaluation_corpus_quality import quality_metrics

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts/evaluation-corpus-v2"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_text(path: Path, content_type: str) -> str:
    if content_type == "markdown":
        return path.read_text(encoding="utf-8")
    return "\n\n".join(paragraph.text for paragraph in extract_paragraphs(str(path)))


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return int(ordered[index])


def _counts(questions: list[dict], field: str, predicate: Callable[[dict], bool] | None = None) -> dict[str, int]:
    selected = [question for question in questions if predicate is None or predicate(question)]
    return {
        str(value): sum(question[field] == value for question in selected)
        for value in sorted({question[field] for question in selected})
    }


def _split_matrix(questions: list[dict], field: str) -> dict[str, dict[str, int]]:
    values = sorted({question[field] for question in questions})
    splits = ("development", "calibration", "frozen_test")
    return {
        str(value): {
            split: sum(question[field] == value and question["split"] == split for question in questions)
            for split in splits
        }
        for value in values
    }


def build_artifacts(
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    dataset_path: Path | None = None,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, Any]:
    dataset_path = dataset_path or corpus_dir / "golden-dataset-v2.json"
    manifest = _load(corpus_dir / "corpus-manifest.json")
    documents = manifest["documents"]
    questions = _load(dataset_path)
    corpus_records: list[dict[str, Any]] = []
    word_counts: list[int] = []
    for document in documents:
        text = _extract_text(corpus_dir / document["path"], document["content_type"])
        word_counts.append(len(text.split()))
        corpus_records.append({**document, "text": text})

    corpus_fp = evaluation_corpus_fingerprint(corpus_records)
    dataset_fp = evaluation_dataset_fingerprint(questions)
    split_counts = {
        split: sum(question["split"] == split for question in questions)
        for split in ("development", "calibration", "frozen_test")
    }
    stats: dict[str, Any] = {
        "schema_version": "evaluation-corpus-v2",
        "source_of_truth": {
            "manifest": str((corpus_dir / "corpus-manifest.json").relative_to(ROOT)),
            "dataset": str(dataset_path.relative_to(ROOT)),
            "pdf_sources": str((corpus_dir / "pdf-sources").relative_to(ROOT)),
            "artifacts_are_derived": True,
        },
        "document_count": len(documents),
        "markdown_count": sum(document["content_type"] == "markdown" for document in documents),
        "pdf_count": sum(document["content_type"] == "pdf" for document in documents),
        "document_language_counts": {lang: sum(document["language"] == lang for document in documents) for lang in ("tr", "en")},
        "document_tenant_counts": {tenant: sum(document["tenant_id"] == tenant for document in documents) for tenant in ("tenant-a", "tenant-b")},
        "total_characters": sum(len(record["text"]) for record in corpus_records),
        "total_words": sum(word_counts),
        "document_word_percentiles": {f"p{pct}": _percentile(word_counts, pct) for pct in (0, 25, 50, 75, 90, 100)},
        "content_quality": {record["source_id"]: quality_metrics(record["text"]) for record in corpus_records},
        "question_count": len(questions),
        "split_counts": split_counts,
        "case_family_count": len({question["case_family"] for question in questions}),
        "category_counts": dict(Counter(question["category"] for question in questions)),
        "answerability_counts": dict(Counter(question["answerability"] for question in questions)),
        "language_pair_counts": dict(Counter(question["language_pair"] for question in questions)),
        "answerable_language_pair_counts": _counts(questions, "language_pair", lambda q: q["answerability"] == "answerable"),
        "query_language_counts": _counts(questions, "query_language"),
        "non_answerable_query_language_counts": _counts(questions, "query_language", lambda q: q["answerability"] != "answerable"),
        "split_cross_tabs": {
            "answerability": _split_matrix(questions, "answerability"),
            "primary_category": _split_matrix(questions, "category"),
            "query_language": _split_matrix(questions, "query_language"),
            "tenant": _split_matrix(questions, "tenant_id"),
            "difficulty": _split_matrix(questions, "difficulty"),
        },
        "question_tenant_counts": _counts(questions, "tenant_id"),
        "fingerprints": {"corpus_fingerprint": corpus_fp, "dataset_fingerprint": dataset_fp},
        "inference_executed": False,
    }

    stress: dict[str, dict[str, int]] = {}
    for document in documents:
        path = corpus_dir / document["path"]
        stress[document["source_id"]] = {}
        for size in (256, 384, 512, 768):
            if document["content_type"] == "markdown":
                chunks = chunk_markdown_document(str(path), document["source_id"], "filesystem", chunk_size_tokens=size, overlap_tokens=50)
            else:
                chunks = chunk_document(str(path), document["source_id"], "filesystem", chunk_size_tokens=size, overlap_tokens=50)
            stress[document["source_id"]][str(size)] = len(chunks)
    stats["chunking_stress_dry_run"] = {"method": "whitespace proxy; no model tokenizer", "counts_by_source": stress}

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "statistics.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frozen_ids = [question["id"] for question in questions if question["split"] == "frozen_test"]
    metadata = {
        "schema_version": "golden-dataset-v2",
        "question_count": len(questions),
        "corpus_fingerprint": corpus_fp,
        "dataset_fingerprint": dataset_fp,
        "source_of_truth": str(dataset_path.relative_to(ROOT)),
        "split_policy": "Whole case families retain their committed development, calibration, or frozen_test assignment.",
        "frozen_test_policy": "Frozen test records are edited only through an explicit benchmark dataset revision that produces a new dataset fingerprint.",
        "case_family_policy": "All paraphrases and variants of one intent share one case_family and one split.",
        "case_family_count": len({question["case_family"] for question in questions}),
        "frozen_test_id_sha256": hashlib.sha256(json.dumps(frozen_ids, separators=(",", ":")).encode()).hexdigest(),
        "frozen_test_count": len(frozen_ids),
        "inference_executed": False,
    }
    (artifact_dir / "fingerprints.json").write_text(json.dumps({"corpus_fingerprint": corpus_fp, "dataset_fingerprint": dataset_fp}, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"document_count": len(documents), "question_count": len(questions), "corpus_fingerprint": corpus_fp, "dataset_fingerprint": dataset_fp}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static evaluation corpus artifacts")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    args = parser.parse_args()
    result = build_artifacts(args.corpus_dir, args.dataset, args.artifact_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
