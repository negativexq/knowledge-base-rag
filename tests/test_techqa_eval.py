from app.evaluation.techqa import (
    build_report,
    cited_sources,
    doc_file_name,
    holdout_questions,
    source_id_for_text,
)


def _row(qid, question="q?", documents=("doc a", "doc b"), keys=("1c",), response="gold"):
    return {
        "id": qid,
        "question": question,
        "documents": list(documents),
        "response": response,
        "all_relevant_sentence_keys": list(keys),
    }


def test_doc_file_name_is_stable_and_source_id_keeps_extension():
    name = doc_file_name("doc a")
    assert name == doc_file_name("doc a")
    assert name.startswith("techqa_") and name.endswith(".md")
    assert source_id_for_text("doc a") == name.replace(".", "_")


def test_holdout_questions_keep_id_order_first_row_and_relevant_docs():
    rows = [
        _row("Q2", question="second"),
        _row("Q1", question="first", keys=("0a", "0b")),
        _row("Q1", question="duplicate"),
        _row("Q3", keys=()),
    ]
    questions = holdout_questions(rows, ["Q1", "Q2", "Q3"])
    assert [q.qid for q in questions] == ["Q1", "Q2", "Q3"]
    assert questions[0].question == "first"
    assert questions[0].row_idx == 1
    assert questions[0].relevant_sources == (source_id_for_text("doc a"),)
    assert questions[1].relevant_sources == (source_id_for_text("doc b"),)
    assert questions[2].relevant_sources == ()


def test_holdout_questions_fail_on_a_missing_id():
    try:
        holdout_questions([_row("Q1")], ["Q1", "Q9"])
    except ValueError as error:
        assert "Q9" in str(error)
    else:
        raise AssertionError("missing id accepted")


def test_cited_sources_follow_citation_order_and_skip_unknown_ids():
    units = [
        {"support_id": "E1.S1", "source_id": "a_md"},
        {"support_id": "E2.S1", "source_id": "b_md"},
    ]
    answer = "x [E2.S1] y [E9.S9] z [E1.S1] [E2.S1]"
    assert cited_sources(answer, units) == ["b_md", "a_md"]


def _raw(qid, abstain=False, codes=None, top=(), candidates=(), cited=(), leaks=0, seconds=1.0):
    return {
        "qid": qid,
        "abstain": abstain,
        "validator_failure_codes": codes if codes is not None else [],
        "top_sources": list(top),
        "candidate_sources": list(candidates),
        "cited_sources": list(cited),
        "acl_leaks": leaks,
        "seconds": seconds,
    }


def test_build_report_counts_kinds_hits_citations_and_scores():
    rows = [_row("Q1", keys=("0a",)), _row("Q2", keys=("1a",)), _row("Q3", keys=())]
    questions = holdout_questions(rows, ["Q1", "Q2", "Q3"])
    a, b = source_id_for_text("doc a"), source_id_for_text("doc b")
    raws = [
        _raw("Q1", top=[a], candidates=[a, b], cited=[a], seconds=2.0),
        _raw("Q2", abstain=True, codes=["CRITICAL_VALUE_MISMATCH"], candidates=[b]),
        _raw("Q3", abstain=True),
    ]
    scores = {"Q1": "CORRECT", "Q2": "UNAVAILABLE", "Q3": "UNAVAILABLE"}
    report = build_report(questions, raws, top_n=14, candidate_k=40, scores=scores)
    assert report["response_kinds"] == {
        "answered": 1,
        "validator_blocked": 1,
        "model_abstained": 1,
    }
    assert report["retrieval_hit_top"] == {"rate": 0.5, "n": 2}
    assert report["retrieval_hit_candidates"] == {"rate": 1.0, "n": 2}
    assert report["citation_on_relevant"] == {"rate": 1.0, "n": 1}
    assert report["semantic"]["counts"] == {"CORRECT": 1, "UNAVAILABLE": 2}
    assert report["semantic"]["useful_rate"] == round(1 / 3, 4)
    assert report["acl_leaks"] == 0
    assert report["median_seconds"] == 1.0


def test_build_report_without_scores_leaves_semantic_empty():
    questions = holdout_questions([_row("Q1")], ["Q1"])
    report = build_report(questions, [_raw("Q1")], top_n=5, candidate_k=20)
    assert report["semantic"] is None
