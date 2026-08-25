from app.evaluation.dataset_fingerprint import corpus_fingerprint, golden_set_fingerprint


def _q(id_, query="Q", query_lang="en", content_lang="en", locations=None, difficulty="exact"):
    return {
        "id": id_,
        "query": query,
        "query_lang": query_lang,
        "content_lang": content_lang,
        "expected_locations": locations or [["filesystem", "doc", "A"]],
        "difficulty": difficulty,
    }


def test_golden_set_fingerprint_is_deterministic():
    questions = [_q("a"), _q("b")]

    first = golden_set_fingerprint(questions)
    second = golden_set_fingerprint(questions)

    assert first == second


def test_golden_set_fingerprint_is_independent_of_input_order():
    a_then_b = golden_set_fingerprint([_q("a"), _q("b")])
    b_then_a = golden_set_fingerprint([_q("b"), _q("a")])

    assert a_then_b == b_then_a


def test_golden_set_fingerprint_changes_when_a_query_changes():
    original = golden_set_fingerprint([_q("a", query="original text")])
    edited = golden_set_fingerprint([_q("a", query="edited text")])

    assert original != edited


def test_golden_set_fingerprint_changes_when_expected_location_changes():
    original = golden_set_fingerprint([_q("a", locations=[["filesystem", "doc", "A"]])])
    edited = golden_set_fingerprint([_q("a", locations=[["filesystem", "doc", "B"]])])

    assert original != edited


def test_golden_set_fingerprint_changes_when_a_question_is_added():
    smaller = golden_set_fingerprint([_q("a")])
    bigger = golden_set_fingerprint([_q("a"), _q("b")])

    assert smaller != bigger


def test_corpus_fingerprint_is_deterministic_and_order_independent():
    docs = {"a.md": "content a", "b.md": "content b"}

    first = corpus_fingerprint(docs)
    second = corpus_fingerprint({"b.md": "content b", "a.md": "content a"})

    assert first == second


def test_corpus_fingerprint_changes_when_content_changes():
    original = corpus_fingerprint({"a.md": "original"})
    edited = corpus_fingerprint({"a.md": "edited"})

    assert original != edited
