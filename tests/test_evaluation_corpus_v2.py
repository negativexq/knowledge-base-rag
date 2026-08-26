import json
import shutil
from pathlib import Path

from app.evaluation.dataset_fingerprint import (
    evaluation_corpus_fingerprint,
    evaluation_dataset_fingerprint,
)
from scripts.build_evaluation_corpus_v2 import build_questions
from scripts.validate_evaluation_corpus import validate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/evaluation/evaluation-corpus-v2"
ARTIFACTS = ROOT / "artifacts/evaluation-corpus-v2"
DATASET = CORPUS / "golden-dataset-v2.json"


def _load_questions() -> list[dict]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def _isolated_copy(tmp_path: Path, mutate) -> dict:
    corpus = tmp_path / "corpus"
    artifacts = tmp_path / "artifacts"
    shutil.copytree(CORPUS, corpus)
    shutil.copytree(ARTIFACTS, artifacts)
    dataset = corpus / "golden-dataset-v2.json"
    questions = json.loads(dataset.read_text(encoding="utf-8"))
    mutate(questions)
    dataset.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    return validate(corpus, dataset, artifacts)


def test_corpus_v2_integrity_and_pdf_readability():
    report = validate(CORPUS, DATASET, ARTIFACTS)

    assert report["valid"], report["errors"]
    assert report["document_count"] == 20
    assert report["question_count"] == 445
    assert report["heavy_inference_executed"] is False


def test_corpus_v2_fingerprints_are_deterministic():
    questions = _load_questions()
    metadata = json.loads((CORPUS / "corpus-manifest.json").read_text(encoding="utf-8"))
    documents = []
    for document in metadata["documents"]:
        path = CORPUS / document["path"]
        text = path.read_text(encoding="utf-8") if path.suffix == ".md" else ""
        documents.append({**document, "text": text})

    assert evaluation_dataset_fingerprint(questions) == evaluation_dataset_fingerprint(
        list(reversed(questions))
    )
    assert evaluation_corpus_fingerprint(documents) == evaluation_corpus_fingerprint(
        list(reversed(documents))
    )


def test_corpus_v2_split_is_deterministic():
    first = build_questions()
    second = build_questions()

    assert [(q["id"], q["split"]) for q in first] == [(q["id"], q["split"]) for q in second]
    assert {q["split"] for q in first} == {"development", "calibration", "frozen_test"}


def test_corpus_v2_case_families_never_cross_splits():
    questions = _load_questions()
    split_by_family = {}
    for question in questions:
        split_by_family.setdefault(question["case_family"], set()).add(question["split"])

    assert all(len(splits) == 1 for splits in split_by_family.values())


def test_validator_rejects_case_family_split_leakage(tmp_path):
    def mutate(questions):
        family = questions[0]["case_family"]
        sibling = next(
            question for question in questions[1:] if question["case_family"] == family
        )
        sibling["split"] = (
            "frozen_test" if questions[0]["split"] != "frozen_test" else "development"
        )

    report = _isolated_copy(tmp_path, mutate)

    assert any("case families cross split boundaries" in error for error in report["errors"])


def test_statistics_separate_answerable_pairs_and_split_cross_tabs():
    stats = json.loads((ARTIFACTS / "statistics.json").read_text(encoding="utf-8"))

    assert stats["answerable_language_pair_counts"] == {
        "en->en": 162,
        "en->tr": 27,
        "tr->en": 88,
        "tr->mixed": 4,
        "tr->tr": 56,
    }
    assert stats["non_answerable_query_language_counts"] == {"en": 54, "tr": 54}
    assert set(stats["split_cross_tabs"]) == {
        "answerability",
        "primary_category",
        "query_language",
        "tenant",
        "difficulty",
    }


def test_validator_rejects_duplicate_question_ids(tmp_path):
    def mutate(questions):
        questions[1] = {**questions[1], "id": questions[0]["id"]}

    report = _isolated_copy(tmp_path, mutate)

    assert any("duplicate question id" in error for error in report["errors"])


def test_validator_rejects_invalid_split(tmp_path):
    report = _isolated_copy(tmp_path, lambda questions: questions[0].update(split="holdout"))

    assert any("invalid split" in error for error in report["errors"])


def test_validator_rejects_missing_source_reference(tmp_path):
    def mutate(questions):
        questions[0]["expected_source_ids"] = ["does-not-exist"]

    report = _isolated_copy(tmp_path, mutate)

    assert any("unknown expected source reference" in error for error in report["errors"])


def test_validator_rejects_answerable_without_evidence(tmp_path):
    def mutate(questions):
        answerable = next(
            question for question in questions if question["answerability"] == "answerable"
        )
        answerable["expected_source_ids"] = []
        answerable["required_evidence"] = []

    report = _isolated_copy(tmp_path, mutate)

    assert any(
        "answerable records require answer and evidence" in error
        for error in report["errors"]
    )


def test_validator_rejects_invalid_language_pair_and_tenant(tmp_path):
    def mutate(questions):
        questions[0]["language_pair"] = "en->tr"
        questions[1]["tenant_id"] = "tenant-c"

    report = _isolated_copy(tmp_path, mutate)

    assert any("language_pair does not match" in error for error in report["errors"])
    assert any("invalid tenant_id" in error for error in report["errors"])
