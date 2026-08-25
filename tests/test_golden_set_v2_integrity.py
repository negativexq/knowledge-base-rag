"""Sprint 20: validates the REAL tests/fixtures/embedding_benchmark_golden_v2.json
fixture against the REAL chunker output — no Qdrant/Ollama needed, since
location_for() only depends on chunk attributes the chunkers themselves
compute deterministically. This is what actually proves "every expected
location corresponds to a real ingested chunk," not just an isolated
unit test of the validation logic (see test_golden_set_validation.py).
"""

import json
from collections import Counter

from app.evaluation.golden_set_validation import validate_golden_set
from app.ingestion.chunker import chunk_document
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.llm.citation_location import location_for
from tests.fixtures.golden_api_reference_en import build_golden_api_reference_en
from tests.fixtures.golden_enterprise_faq_tr import build_golden_enterprise_faq_tr
from tests.fixtures.golden_markdown_source import build_golden_markdown_source
from tests.fixtures.golden_source import build_golden_source_pdf

GOLDEN_PATH = "tests/fixtures/embedding_benchmark_golden_v2.json"

MINIMUM_DISTRIBUTION = {
    ("tr", "en"): 75,
    ("en", "tr"): 75,
    ("tr", "tr"): 25,
    ("en", "en"): 25,
}


def _load_questions() -> list[dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def _real_locations(tmp_path) -> set[tuple[str, str, str]]:
    """Builds the real chunk set from the actual fixture-building
    functions and the actual chunkers — the same functions
    scripts/benchmark_embeddings.py uses to build the benchmark corpus —
    and derives their real (source_type, source_id, location) triples.
    "filesystem" is hardcoded here because that's the source_type
    LocalFilesystemConnector always passes, overriding chunk_document's/
    chunk_markdown_document's own "pdf"/"markdown" defaults — see
    app/ingestion/ingest.py.
    """
    pdf_path = tmp_path / "nimbus_handbook.pdf"
    cli_path = tmp_path / "nimbus_cli.md"
    api_path = tmp_path / "nimbus_api_reference.md"
    faq_path = tmp_path / "nimbus_kurumsal_sss.md"
    build_golden_source_pdf(str(pdf_path))
    build_golden_markdown_source(str(cli_path))
    build_golden_api_reference_en(str(api_path))
    build_golden_enterprise_faq_tr(str(faq_path))

    chunks = []
    chunks += chunk_document(str(pdf_path), "nimbus_handbook_pdf", "filesystem")
    chunks += chunk_markdown_document(str(cli_path), "nimbus_cli_md", "filesystem")
    chunks += chunk_markdown_document(str(api_path), "nimbus_api_reference_md", "filesystem")
    chunks += chunk_markdown_document(str(faq_path), "nimbus_kurumsal_sss_md", "filesystem")

    locations = set()
    for chunk in chunks:
        payload = {
            "page_number": chunk.page_number,
            "paragraph_index": chunk.paragraph_index,
            "heading_path": list(chunk.heading_path),
            "heading_occurrence": chunk.heading_occurrence,
        }
        locations.add((chunk.source_type, chunk.source_id, location_for(payload)))
    return locations


def test_golden_v2_has_at_least_200_questions():
    questions = _load_questions()

    assert len(questions) >= 200


def test_golden_v2_meets_the_minimum_language_pair_distribution(tmp_path):
    questions = _load_questions()
    report = validate_golden_set(questions, _real_locations(tmp_path))

    assert report.meets_distribution(MINIMUM_DISTRIBUTION), report.language_pair_counts


def test_golden_v2_has_no_exact_or_normalized_duplicate_questions(tmp_path):
    questions = _load_questions()
    report = validate_golden_set(questions, _real_locations(tmp_path))

    assert report.exact_duplicate_queries == []
    assert report.normalized_duplicate_queries == []


def test_golden_v2_has_zero_dangling_expected_locations(tmp_path):
    """The core promise of this fixture: every single expected_location
    corresponds to a chunk the REAL chunkers actually produce from the
    REAL fixture corpus — not a typo, not stale after an edit.
    """
    questions = _load_questions()
    report = validate_golden_set(questions, _real_locations(tmp_path))

    assert report.dangling_locations == []


def test_golden_v2_not_found_ratio_is_reasonable():
    """Not-found questions should be present (calibration signal) but
    not dominate the set — a sanity band, not a precise target.
    """
    questions = _load_questions()
    report = validate_golden_set(questions, real_locations=set())

    assert 0.02 <= report.not_found_ratio <= 0.15


def test_golden_v2_covers_a_real_spread_of_difficulty_categories():
    questions = _load_questions()
    difficulties = Counter(q["difficulty"] for q in questions)

    expected_categories = {
        "exact_lexical",
        "semantic_paraphrase",
        "terminology_mismatch",
        "acronym_abbreviation",
        "number_date_lookup",
        "multi_sentence_evidence",
        "heading_dependent",
        "ambiguous_wording",
        "hard_negative",
        "not_found",
    }

    assert expected_categories.issubset(difficulties.keys())
    # Every category present at least a few times, not just once.
    assert all(count >= 2 for count in difficulties.values())


def test_golden_v2_every_question_id_is_unique():
    questions = _load_questions()
    ids = [q["id"] for q in questions]

    assert len(ids) == len(set(ids))
