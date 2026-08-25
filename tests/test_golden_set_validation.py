from app.evaluation.golden_set_validation import (
    find_dangling_locations,
    find_exact_duplicates,
    find_normalized_duplicates,
    language_pair_counts,
    normalize_query,
    validate_golden_set,
)


def _q(id_, query, query_lang="en", content_lang="en", location=("filesystem", "doc", "A")):
    return {
        "id": id_,
        "query": query,
        "query_lang": query_lang,
        "content_lang": content_lang,
        "expected_locations": [list(location)],
    }


def test_normalize_query_collapses_case_punctuation_and_whitespace():
    assert normalize_query("What is X?") == normalize_query("what is x")
    assert normalize_query("  Hello,   world!  ") == normalize_query("hello world")


def test_normalize_query_preserves_turkish_characters():
    assert normalize_query("Şifre nedir?") == "şifre nedir"


def test_find_exact_duplicates_detects_identical_query_text():
    questions = [_q("a", "How many GB?"), _q("b", "How many GB?"), _q("c", "Different question")]

    duplicates = find_exact_duplicates(questions)

    assert duplicates == [["a", "b"]]


def test_find_exact_duplicates_empty_when_all_unique():
    questions = [_q("a", "Q1"), _q("b", "Q2")]

    assert find_exact_duplicates(questions) == []


def test_find_normalized_duplicates_catches_casing_and_punctuation_variants():
    questions = [_q("a", "What is X?"), _q("b", "what is x"), _q("c", "Totally different")]

    duplicates = find_normalized_duplicates(questions)

    assert duplicates == [["a", "b"]]


def test_find_normalized_duplicates_does_not_flag_genuinely_different_questions():
    questions = [_q("a", "How many GB of storage?"), _q("b", "How many days for a refund?")]

    assert find_normalized_duplicates(questions) == []


def test_find_dangling_locations_flags_a_location_absent_from_real_qdrant_points():
    questions = [_q("a", "Q1", location=("filesystem", "doc", "Real"))]
    real_locations = {("filesystem", "doc", "Real")}

    assert find_dangling_locations(questions, real_locations) == []

    questions_with_dangling = [_q("b", "Q2", location=("filesystem", "doc", "Fake"))]
    dangling = find_dangling_locations(questions_with_dangling, real_locations)

    assert dangling == [("b", ("filesystem", "doc", "Fake"))]


def test_find_dangling_locations_ignores_not_found_questions_with_no_expected_locations():
    questions = [{"id": "nf", "expected_locations": [], "expect_not_found": True}]

    assert find_dangling_locations(questions, set()) == []


def test_language_pair_counts_groups_by_query_and_content_language():
    questions = [
        _q("a", "Q1", query_lang="tr", content_lang="en"),
        _q("b", "Q2", query_lang="tr", content_lang="en"),
        _q("c", "Q3", query_lang="en", content_lang="tr"),
    ]

    counts = language_pair_counts(questions)

    assert counts == {("tr", "en"): 2, ("en", "tr"): 1}


def test_language_pair_counts_excludes_not_found_questions_with_no_content_lang():
    questions = [
        _q("a", "Q1", query_lang="tr", content_lang="en"),
        {"id": "nf", "query_lang": "tr", "content_lang": None, "expected_locations": []},
    ]

    counts = language_pair_counts(questions)

    assert counts == {("tr", "en"): 1}


def test_validate_golden_set_is_clean_for_a_healthy_dataset():
    questions = [
        _q("a", "Question one", query_lang="tr", content_lang="en"),
        _q("b", "Question two", query_lang="en", content_lang="tr"),
    ]
    real_locations = {("filesystem", "doc", "A")}

    report = validate_golden_set(questions, real_locations)

    assert report.is_clean
    assert report.exact_duplicate_queries == []
    assert report.dangling_locations == []


def test_validate_golden_set_is_not_clean_with_a_dangling_location():
    questions = [_q("a", "Q1", location=("filesystem", "doc", "Missing"))]

    report = validate_golden_set(questions, real_locations=set())

    assert not report.is_clean
    assert report.dangling_locations == [("a", ("filesystem", "doc", "Missing"))]


def test_validate_golden_set_computes_not_found_ratio():
    questions = [
        _q("a", "Q1"),
        _q("b", "Q2"),
        _q("c", "Q3"),
        {"id": "nf", "query": "Q4", "query_lang": "en", "content_lang": None,
         "expected_locations": [], "expect_not_found": True},
    ]

    report = validate_golden_set(questions, real_locations={("filesystem", "doc", "A")})

    assert report.not_found_count == 1
    assert report.not_found_ratio == 0.25
    assert report.total_questions == 4


def test_meets_distribution_checks_minimums_per_cell():
    questions = [_q(f"a{i}", f"Q{i}", query_lang="tr", content_lang="en") for i in range(80)]
    report = validate_golden_set(questions, real_locations={("filesystem", "doc", "A")})

    assert report.meets_distribution({("tr", "en"): 75})
    assert not report.meets_distribution({("tr", "en"): 81})
    assert not report.meets_distribution({("en", "tr"): 1})  # cell doesn't exist at all
