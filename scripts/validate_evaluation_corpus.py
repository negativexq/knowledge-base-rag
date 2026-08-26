"""Fast, model-free integrity checks for Evaluation Corpus v2.

The validator reads Markdown and text-selectable PDF fixtures, then checks
evaluator-owned labels and deterministic fingerprints. It never embeds,
reranks, generates, contacts Ollama, or opens Qdrant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.dataset_fingerprint import (
    evaluation_corpus_fingerprint,
    evaluation_dataset_fingerprint,
)
from app.parsing.pdf_parser import extract_paragraphs
from scripts.evaluation_corpus_quality import (
    language_matches,
    language_scores,
    quality_metrics,
    query_has_label_leakage,
)

VALID_LANGUAGES = {"en", "tr"}
VALID_TENANTS = {"tenant-a", "tenant-b"}
VALID_SPLITS = {"development", "calibration", "frozen_test"}
VALID_ANSWERABILITY = {"answerable", "unanswerable", "ambiguous"}
VALID_CONTENT_TYPES = {"markdown", "pdf"}
VALID_AUTHORITY_ROLES = {
    "canonical_policy", "channel_policy", "product_policy", "operational_policy",
    "security_policy", "service_authority", "superseded_policy", "change_notice",
    "supporting_policy", "contract_controlled", "regional_policy", "internal_handbook",
    "operational_playbook", "statutory_regional", "product_reference", "contract_authority",
}
VALID_CATEGORIES = {
    "standard_answerable",
    "hard_answerable",
    "unanswerable",
    "ambiguous",
    "version_conflict",
    "cross_lingual",
    "multi_document",
    "acl_negative",
    "injection_bearing",
}
QUERY_ARTIFACT_PATTERNS = (
    r"\bthe\s+the\b",
    r"\bfor\s+a\s+the\b",
    r"\b(?:using|according to) the (?:english|turkish) (?:source|document|policy)\b",
    r"\b(?:check|verify) the tenant boundary\b",
)


def _normalise_query(query: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", "", query.lower())).strip()


def _read_document(path: Path, content_type: str) -> str:
    if content_type == "markdown":
        return path.read_text(encoding="utf-8")
    return "\n\n".join(paragraph.text for paragraph in extract_paragraphs(str(path)))


def expected_evidence_language(
    question: dict[str, Any], source_languages: dict[str, str]
) -> str | None:
    """Derive the evidence language from evaluator-owned source references."""
    references = (
        question.get("expected_source_ids", [])
        + question.get("supporting_source_ids", [])
        + question.get("required_evidence", [])
    )
    languages = {
        source_languages[reference]
        for reference in references
        if reference in source_languages
    }
    if not languages:
        return None
    return languages.pop() if len(languages) == 1 else "mixed"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON {path}: {exc}") from exc


def validate(corpus_dir: Path, dataset_path: Path, artifact_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest = _load_json(corpus_dir / "corpus-manifest.json")
    documents = manifest.get("documents") if isinstance(manifest, dict) else None
    if manifest.get("schema_version") != "evaluation-corpus-v2" or not isinstance(documents, list):
        errors.append("corpus manifest must use evaluation-corpus-v2 and contain documents")
        documents = []
    if not 15 <= len(documents) <= 25:
        errors.append(f"expected 15–25 corpus documents, found {len(documents)}")

    source_map: dict[tuple[str, str], dict[str, Any]] = {}
    source_ids_seen: set[str] = set()
    corpus_records: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        prefix = f"document[{index}]"
        required = {"source_id", "path", "tenant_id", "language", "content_type", "title"}
        missing = required - set(document)
        if missing:
            errors.append(f"{prefix} missing fields: {sorted(missing)}")
            continue
        key = (document["tenant_id"], document["source_id"])
        if key in source_map:
            errors.append(f"duplicate document identity: {key}")
        if document["source_id"] in source_ids_seen:
            errors.append(f"duplicate source_id: {document['source_id']}")
        source_ids_seen.add(document["source_id"])
        source_map[key] = document
        if document["tenant_id"] not in VALID_TENANTS:
            errors.append(f"{prefix} has invalid tenant_id")
        if document["language"] not in VALID_LANGUAGES:
            errors.append(f"{prefix} has invalid language")
        if document["content_type"] not in VALID_CONTENT_TYPES:
            errors.append(f"{prefix} has invalid content_type")
        if document.get("authority_role") not in VALID_AUTHORITY_ROLES:
            errors.append(f"{prefix} has invalid or missing authority_role")
        if not document.get("authority_scope"):
            errors.append(f"{prefix} has missing authority_scope")
        path = corpus_dir / document["path"]
        if not path.is_file():
            errors.append(f"{prefix} path does not exist: {document['path']}")
            continue
        if path.suffix.lower() != (".pdf" if document["content_type"] == "pdf" else ".md"):
            errors.append(f"{prefix} extension does not match content_type")
            continue
        if document["content_type"] == "pdf":
            source_path = document.get("source_path")
            if not source_path:
                errors.append(f"{prefix} PDF is missing source_path")
            elif not (corpus_dir / source_path).is_file():
                errors.append(f"{prefix} PDF source_path does not exist: {source_path}")
            elif Path(source_path).suffix.lower() != ".md":
                errors.append(f"{prefix} PDF source_path must point to Markdown")
        try:
            text = _read_document(path, document["content_type"])
        except Exception as exc:  # pragma: no cover - error is reported, not hidden
            errors.append(f"{prefix} cannot be read: {exc}")
            continue
        if len(text.split()) < 20:
            errors.append(f"{prefix} is empty or only a placeholder")
        if document["content_type"] == "markdown" and "#" not in text:
            errors.append(f"{prefix} Markdown has no heading")
        if document["content_type"] == "pdf" and not text.strip():
            errors.append(f"{prefix} PDF has no selectable text")
        if not language_matches(text, document["language"]):
            errors.append(
                f"{prefix} language metadata does not match content: "
                f"expected {document['language']} "
                f"({language_scores(text)})"
            )
        if re.search(r"(?:operational record|operasyon kaydı)\s+\d+", text, re.IGNORECASE):
            errors.append(f"{prefix} contains count-based operational-record filler")
        corpus_records.append({**document, "text": text})

    source_id_names = {source_id for _, source_id in source_map}
    for document in documents:
        for related in document.get("related_source_ids", []):
            if related not in source_id_names:
                errors.append(
                    f"document {document.get('source_id')} references unknown related source "
                    f"{related}"
                )

    content_metrics = {
        record["source_id"]: quality_metrics(record["text"])
        for record in corpus_records
    }
    for source_id, metrics in content_metrics.items():
        if metrics["exact_duplicate_ratio"] > 0.03:
            errors.append(f"{source_id} exceeds exact substantive paragraph duplicate threshold")
        if metrics["normalized_duplicate_ratio"] > 0.07:
            errors.append(
                f"{source_id} exceeds normalized substantive paragraph duplicate threshold"
            )
        if metrics["repeated_long_ngram_ratio"] > 0.20:
            errors.append(f"{source_id} contains excessive repeated long n-grams")

    long_documents = [
        record for record in corpus_records
        if len(record["text"].split()) > 768
        or (record["content_type"] == "pdf" and (record.get("page_count") or 0) >= 8)
    ]
    if len(long_documents) < 8:
        errors.append(f"expected eight long/stress documents, found {len(long_documents)}")

    try:
        questions = _load_json(dataset_path)
    except ValueError as exc:
        errors.append(str(exc))
        questions = []
    if not isinstance(questions, list) or not 400 <= len(questions) <= 500:
        found = len(questions) if isinstance(questions, list) else "non-list"
        errors.append(f"expected 400–500 questions, found {found}")

    question_ids: set[str] = set()
    normalized_queries: dict[str, list[str]] = {}
    source_ids = {document["source_id"] for document in documents if "source_id" in document}
    source_tenants = {
        document["source_id"]: document["tenant_id"]
        for document in documents
        if "source_id" in document
    }
    for index, question in enumerate(questions if isinstance(questions, list) else []):
        prefix = f"question[{index}]"
        required = {
            "id", "question", "query_language", "evidence_language", "language_pair",
            "category", "answerability", "expected_answer", "expected_source_ids",
            "relevant_source_ids", "supporting_source_ids", "distractor_source_ids",
            "required_evidence",
            "tenant_id", "split", "case_family", "fact_id", "intent_group",
            "difficulty", "rationale",
        }
        missing = required - set(question)
        if missing:
            errors.append(f"{prefix} missing fields: {sorted(missing)}")
            continue
        question_id = question["id"]
        if question_id in question_ids:
            errors.append(f"duplicate question id: {question_id}")
        question_ids.add(question_id)
        normalized_queries.setdefault(_normalise_query(question["question"]), []).append(
            question_id
        )
        if query_has_label_leakage(question["question"]):
            errors.append(f"{prefix} contains evaluation-label or language-hint leakage")
        if any(
            re.search(pattern, question["question"], re.IGNORECASE)
            for pattern in QUERY_ARTIFACT_PATTERNS
        ):
            errors.append(f"{prefix} contains a generated query grammar artifact")
        qlang = question["query_language"]
        elang = question["evidence_language"]
        if qlang not in VALID_LANGUAGES:
            errors.append(f"{prefix} invalid query_language")
        if elang not in VALID_LANGUAGES | {"mixed", None}:
            errors.append(f"{prefix} invalid evidence_language")
        expected_pair = f"{qlang}->{elang}" if elang else f"{qlang}->none"
        if question["language_pair"] != expected_pair:
            errors.append(f"{prefix} language_pair does not match language fields")
        if question["tenant_id"] not in VALID_TENANTS:
            errors.append(f"{prefix} invalid tenant_id")
        if question["split"] not in VALID_SPLITS:
            errors.append(f"{prefix} invalid split")
        if not question["case_family"] or not question["fact_id"] or not question["intent_group"]:
            errors.append(f"{prefix} case_family, fact_id, and intent_group are required")
        if question["category"] not in VALID_CATEGORIES:
            errors.append(f"{prefix} invalid category")
        if question["answerability"] not in VALID_ANSWERABILITY:
            errors.append(f"{prefix} invalid answerability")

        expected = question["expected_source_ids"]
        relevant = question["relevant_source_ids"]
        supporting = question["supporting_source_ids"]
        distractors = question["distractor_source_ids"]
        required_evidence = question["required_evidence"]
        references = (
            ("expected", expected),
            ("relevant", relevant),
            ("supporting", supporting),
            ("distractor", distractors),
            ("required", required_evidence),
        )
        for label, refs in references:
            if not isinstance(refs, list) or any(ref not in source_ids for ref in refs):
                errors.append(f"{prefix} has an unknown {label} source reference")
        if set(relevant) != set(expected) | set(supporting):
            errors.append(
                f"{prefix} relevant_source_ids must equal expected plus supporting sources"
            )
        if set(distractors) & (set(expected) | set(supporting)):
            errors.append(f"{prefix} source cannot be both supporting/relevant and distractor")
        if question["fact_id"] in source_id_names:
            errors.append(f"{prefix} fact_id must identify a fact, not a source document")
        if question["answerability"] == "answerable":
            if not question["expected_answer"] or not expected or not required_evidence:
                errors.append(f"{prefix} answerable records require answer and evidence")
            if set(required_evidence) - set(expected):
                errors.append(f"{prefix} required_evidence must be a subset of expected_source_ids")
            if any(source_tenants.get(ref) != question["tenant_id"] for ref in expected):
                errors.append(f"{prefix} expected evidence crosses the caller tenant boundary")
            source_languages = {
                document["source_id"]: document["language"]
                for document in documents
                if "source_id" in document
            }
            derived_language = expected_evidence_language(question, source_languages)
            if question["evidence_language"] != derived_language:
                errors.append(
                    f"{prefix} evidence_language {question['evidence_language']!r} does not match "
                    f"referenced source languages ({derived_language!r})"
                )
        elif question["answerability"] == "unanswerable":
            if question["expected_answer"] is not None or expected or required_evidence:
                errors.append(f"{prefix} unanswerable records cannot require evidence or an answer")
        elif question["expected_answer"] is not None or expected or required_evidence:
            errors.append(f"{prefix} ambiguous records cannot carry required answer evidence")

    fact_signatures: dict[str, set[tuple[str, str, tuple[str, ...]]]] = {}
    for question in questions:
        signature = (
            question.get("answerability", ""),
            str(question.get("expected_answer")),
            tuple(sorted(question.get("expected_source_ids", []))),
        )
        fact_signatures.setdefault(question.get("fact_id"), set()).add(signature)
    for fact_id, signatures in fact_signatures.items():
        allowed_case_prefixes = (
            "case.", "version.", "multi.", "acl.", "injection.", "negative.", "ambiguous."
        )
        if len(signatures) > 1 and not fact_id.startswith(allowed_case_prefixes):
            errors.append(f"fact_id maps to conflicting evidence signatures: {fact_id}")

    duplicates = [ids for ids in normalized_queries.values() if len(ids) > 1]
    if duplicates:
        errors.append(f"normalized duplicate questions: {duplicates[:3]}")
    family_splits: dict[str, set[str]] = {}
    for question in questions:
        family_splits.setdefault(question.get("case_family"), set()).add(question.get("split"))
    split_families = {
        family: sorted(splits) for family, splits in family_splits.items() if len(splits) > 1
    }
    if split_families:
        errors.append(
            f"case families cross split boundaries: {dict(list(split_families.items())[:3])}"
        )
    split_counts = Counter(question.get("split") for question in questions)
    total = len(questions)
    if total and not (0.40 <= split_counts["development"] / total <= 0.50):
        errors.append("development split is outside the 40–50% policy band")
    if total and not (0.20 <= split_counts["calibration"] / total <= 0.30):
        errors.append("calibration split is outside the 20–30% policy band")
    if total and not (0.25 <= split_counts["frozen_test"] / total <= 0.35):
        errors.append("frozen_test split is outside the 25–35% policy band")

    language_pairs = Counter(question.get("language_pair") for question in questions)
    if not language_pairs["tr->en"] or not language_pairs["en->tr"]:
        errors.append("both cross-lingual language directions must be represented")
    category_counts = Counter(question.get("category") for question in questions)
    for category in VALID_CATEGORIES:
        if category_counts[category] == 0:
            errors.append(f"category missing: {category}")

    corpus_fp = evaluation_corpus_fingerprint(corpus_records)
    dataset_fp = evaluation_dataset_fingerprint(questions)
    fingerprint_file = _load_json(artifact_dir / "fingerprints.json")
    if fingerprint_file.get("corpus_fingerprint") != corpus_fp:
        errors.append("corpus fingerprint artifact does not match corpus files")
    if fingerprint_file.get("dataset_fingerprint") != dataset_fp:
        errors.append("dataset fingerprint artifact does not match dataset")
    metadata = _load_json(artifact_dir / "dataset-metadata.json")
    if (
        metadata.get("dataset_fingerprint") != dataset_fp
        or metadata.get("corpus_fingerprint") != corpus_fp
    ):
        errors.append("dataset metadata fingerprints do not match")
    if metadata.get("question_count") != len(questions):
        errors.append("dataset metadata question_count does not match dataset")

    stats = _load_json(artifact_dir / "statistics.json")
    if (
        stats.get("question_count") != len(questions)
        or stats.get("document_count") != len(documents)
    ):
        errors.append("statistics artifact counts do not match source files")
    if stats.get("inference_executed") is not False:
        errors.append("statistics artifact must state that inference was not executed")
    for stat_key in (
        "answerable_language_pair_counts",
        "non_answerable_query_language_counts",
        "split_cross_tabs",
    ):
        if stat_key not in stats:
            errors.append(f"statistics artifact missing {stat_key}")

    return {
        "valid": not errors,
        "errors": errors,
        "document_count": len(documents),
        "question_count": len(questions),
        "split_counts": dict(split_counts),
        "answerability_counts": dict(
            Counter(question.get("answerability") for question in questions)
        ),
        "category_counts": dict(category_counts),
        "language_pair_counts": dict(language_pairs),
        "answerable_language_pair_counts": dict(
            Counter(
                question.get("language_pair")
                for question in questions
                if question.get("answerability") == "answerable"
            )
        ),
        "split_cross_tabs": stats.get("split_cross_tabs", {}),
        "content_quality": content_metrics,
        "non_answerable_query_language_counts": dict(
            Counter(
                question.get("query_language")
                for question in questions
                if question.get("answerability") != "answerable"
            )
        ),
        "corpus_fingerprint": corpus_fp,
        "dataset_fingerprint": dataset_fp,
        "heavy_inference_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Evaluation Corpus v2 without model inference"
    )
    parser.add_argument(
        "--corpus-dir", type=Path, default=Path("data/evaluation/evaluation-corpus-v2")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"),
    )
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/evaluation-corpus-v2"))
    args = parser.parse_args()
    report = validate(args.corpus_dir, args.dataset, args.artifact_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        for error in report["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Evaluation Corpus v2 validation passed; no model inference executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
