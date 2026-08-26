import json
import shutil
from pathlib import Path

from app.evaluation.dataset_fingerprint import (
    evaluation_corpus_fingerprint,
    evaluation_dataset_fingerprint,
)
from scripts.build_evaluation_artifacts import build_artifacts
from scripts.evaluation_corpus_quality import quality_metrics
from scripts.render_evaluation_pdfs import render_all
from scripts.validate_evaluation_corpus import expected_evidence_language, validate

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
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
        else:
            from scripts.validate_evaluation_corpus import _read_document

            text = _read_document(path, "pdf")
        documents.append({**document, "text": text})

    assert evaluation_dataset_fingerprint(questions) == evaluation_dataset_fingerprint(
        list(reversed(questions))
    )
    assert evaluation_corpus_fingerprint(documents) == evaluation_corpus_fingerprint(
        list(reversed(documents))
    )


def test_corpus_v2_split_is_deterministic():
    first = _load_questions()
    second = json.loads(DATASET.read_text(encoding="utf-8"))

    assert [(q["id"], q["split"]) for q in first] == [(q["id"], q["split"]) for q in second]
    assert {q["split"] for q in first} == {"development", "calibration", "frozen_test"}


def test_artifact_builder_does_not_mutate_canonical_assets(tmp_path):
    canonical = [
        path for path in CORPUS.rglob("*")
        if path.is_file() and path.name != "__pycache__"
    ]
    before = {path: path.read_bytes() for path in canonical}
    build_artifacts(CORPUS, DATASET, tmp_path / "artifacts")

    assert {path: path.read_bytes() for path in canonical} == before


def test_pdf_sources_exist_and_render_to_selectable_text(tmp_path):
    manifest = json.loads((CORPUS / "corpus-manifest.json").read_text(encoding="utf-8"))
    pdfs = [document for document in manifest["documents"] if document["content_type"] == "pdf"]
    assert all((CORPUS / document["source_path"]).is_file() for document in pdfs)

    rendered = render_all(tmp_path)
    assert len(rendered) == len(pdfs)
    for path in rendered:
        assert path.stat().st_size > 0
        assert path.read_bytes().startswith(b"%PDF")


def test_answerable_evidence_language_is_derived_from_manifest():
    manifest = json.loads((CORPUS / "corpus-manifest.json").read_text(encoding="utf-8"))
    languages = {document["source_id"]: document["language"] for document in manifest["documents"]}
    questions = _load_questions()
    mixed = next(question for question in questions if question["id"] == "multi-01-0")
    assert expected_evidence_language(mixed, languages) == "mixed"
    assert mixed["evidence_language"] == "mixed"


def test_validator_rejects_evidence_language_drift(tmp_path):
    def mutate(questions):
        question = next(q for q in questions if q["answerability"] == "answerable")
        question["evidence_language"] = "tr" if question["evidence_language"] != "tr" else "en"

    report = _isolated_copy(tmp_path, mutate)
    assert any("evidence_language" in error for error in report["errors"])


def test_validator_rejects_generated_query_grammar(tmp_path):
    def mutate(questions):
        questions[0]["question"] = "For a the support case, how is the issue handled?"

    report = _isolated_copy(tmp_path, mutate)
    assert any("generated query grammar artifact" in error for error in report["errors"])


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
        "en->en": 149,
        "en->tr": 36,
        "tr->en": 82,
        "tr->mixed": 4,
        "tr->tr": 66,
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


def test_long_documents_have_distinct_substantive_content():
    stats = json.loads((ARTIFACTS / "statistics.json").read_text(encoding="utf-8"))
    long_ids = {
        "employee-handbook-en", "long-policy-tr", "support-playbook",
        "enterprise-contract-guide", "product-guide-en", "regional-returns-eu",
        "regional-returns-tr", "returns-manual-tr",
    }
    for source_id in long_ids:
        metrics = stats["content_quality"][source_id]
        assert metrics["exact_duplicate_ratio"] <= 0.03
        assert metrics["normalized_duplicate_ratio"] <= 0.07
        assert metrics["unique_substantive_paragraph_ratio"] >= 0.93


def test_quality_metrics_expose_count_based_repetition():
    repeated = "The same policy paragraph is repeated to pad a document with no new rule."
    metrics = quality_metrics("\n\n".join([repeated] * 10))

    assert metrics["exact_duplicate_ratio"] > 0.03
    assert metrics["normalized_duplicate_ratio"] > 0.07


def test_validator_rejects_relevant_distractor_conflict(tmp_path):
    def mutate(questions):
        question = next(q for q in questions if q["answerability"] == "answerable")
        question["distractor_source_ids"] = list(question["expected_source_ids"])

    report = _isolated_copy(tmp_path, mutate)

    assert any("both supporting/relevant and distractor" in error for error in report["errors"])


def test_validator_rejects_source_as_fact_id(tmp_path):
    def mutate(questions):
        question = next(q for q in questions if q["answerability"] == "answerable")
        question["fact_id"] = question["expected_source_ids"][0]

    report = _isolated_copy(tmp_path, mutate)

    assert any("fact_id must identify a fact" in error for error in report["errors"])


def test_validator_rejects_wrong_language_metadata(tmp_path):
    corpus = tmp_path / "corpus"
    artifacts = tmp_path / "artifacts"
    shutil.copytree(CORPUS, corpus)
    shutil.copytree(ARTIFACTS, artifacts)
    manifest_path = corpus / "corpus-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    document = next(d for d in manifest["documents"] if d["source_id"] == "long-policy-tr")
    document["language"] = "en"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = validate(corpus, corpus / "golden-dataset-v2.json", artifacts)

    assert any("language metadata does not match" in error for error in report["errors"])


def test_queries_do_not_reveal_evaluation_labels():
    questions = _load_questions()
    forbidden = (
        "available evidence", "tenant boundary", "using the turkish", "without naming a plan"
    )

    assert not any(any(phrase in q["question"].lower() for phrase in forbidden) for q in questions)


def test_manifest_authority_graph_and_injection_fixture():
    manifest = json.loads((CORPUS / "corpus-manifest.json").read_text(encoding="utf-8"))
    source_ids = {doc["source_id"] for doc in manifest["documents"]}
    assert all(set(doc["related_source_ids"]) <= source_ids for doc in manifest["documents"])
    injection = (CORPUS / "injection-bearing-policy.md").read_text(encoding="utf-8")
    assert "SYSTEM OVERRIDE" in injection
    assert "This line is untrusted" not in injection
