"""MMLongBench-Doc pilot: the downloaded files are verified against a pinned
manifest before anything uses them, questions are parsed with their evidence
pages and evidence types, answers are scored deterministically, and the
report breaks every stage metric down by evidence type."""

import json
from pathlib import Path

import pytest

from app.evaluation.mmlongbench import (
    ChecksumMismatchError,
    Manifest,
    QuestionOutcome,
    answer_matches,
    build_report,
    download_manifest_files,
    git_blob_oid,
    load_manifest,
    page_hit,
    parse_question,
)

PDF = b"%PDF-1.4 tiny"
PARQUET = b"PAR1 questions"


def _manifest(tmp_path: Path, pdf: bytes = PDF) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "dataset": "yubo2333/MMLongBench-Doc",
                "revision": "rev123",
                "files": [
                    {"path": "documents/a.pdf", "size": len(pdf), "git_oid": git_blob_oid(pdf)},
                    {
                        "path": "data/train.parquet",
                        "size": len(PARQUET),
                        "git_oid": git_blob_oid(PARQUET),
                    },
                ],
                "question_rows": [3, 7],
            }
        )
    )
    return path


def test_git_blob_oid_matches_git_hash_object():
    # `printf 'hello\n' | git hash-object --stdin`
    assert git_blob_oid(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_load_manifest_reads_files_and_question_rows(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))

    assert isinstance(manifest, Manifest)
    assert manifest.revision == "rev123"
    assert [f.path for f in manifest.files] == ["documents/a.pdf", "data/train.parquet"]
    assert manifest.question_rows == (3, 7)
    assert manifest.url_for(manifest.files[0]) == (
        "https://huggingface.co/datasets/yubo2333/MMLongBench-Doc/resolve/rev123/documents/a.pdf"
    )


def test_download_verifies_every_file_and_skips_verified_ones(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return PDF if url.endswith(".pdf") else PARQUET

    dest = tmp_path / "data"
    paths = download_manifest_files(manifest, dest, fetch)

    assert [p.read_bytes() for p in paths] == [PDF, PARQUET]
    assert len(fetched) == 2

    download_manifest_files(manifest, dest, fetch)
    assert len(fetched) == 2  # already present and verified: no refetch


def test_a_tampered_download_is_rejected_and_not_written(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    dest = tmp_path / "data"

    with pytest.raises(ChecksumMismatchError, match="documents/a.pdf"):
        download_manifest_files(manifest, dest, lambda url: b"%PDF-1.4 evil!")

    assert not (dest / "documents" / "a.pdf").exists()
    assert not list(dest.rglob("*.tmp"))


def test_a_corrupted_local_copy_is_fetched_again(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    dest = tmp_path / "data"
    (dest / "documents").mkdir(parents=True)
    (dest / "documents" / "a.pdf").write_bytes(b"truncated")

    download_manifest_files(manifest, dest, lambda url: PDF if url.endswith(".pdf") else PARQUET)

    assert (dest / "documents" / "a.pdf").read_bytes() == PDF


def test_lfs_files_are_verified_by_their_sha256(tmp_path):
    # The Hub's tree lists an LFS file's git oid for its pointer, not its
    # content; the content is pinned by the LFS sha256 instead.
    import hashlib

    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "dataset": "d",
                "revision": "r",
                "files": [
                    {
                        "path": "data/train.parquet",
                        "size": len(PARQUET),
                        "sha256": hashlib.sha256(PARQUET).hexdigest(),
                    }
                ],
                "question_rows": [],
            }
        )
    )
    manifest = load_manifest(path)

    download_manifest_files(manifest, tmp_path / "ok", lambda url: PARQUET)
    with pytest.raises(ChecksumMismatchError):
        download_manifest_files(manifest, tmp_path / "bad", lambda url: b"PAR1 question!")


def test_parse_question_reads_pages_and_evidence_types():
    question = parse_question(
        {
            "doc_id": "PIP_Seniors.pdf",
            "doc_type": "Research report / Introduction",
            "question": "How many seniors?",
            "answer": "59%",
            "evidence_pages": "[5, 12]",
            "evidence_sources": "['Chart', 'Pure-text (Plain-text)']",
            "answer_format": "Str",
        },
        row_idx=42,
    )

    assert question.row_idx == 42
    assert question.evidence_pages == (5, 12)
    assert question.evidence_types == ("chart", "text")
    assert question.answerable is True


def test_unanswerable_questions_have_no_evidence():
    question = parse_question(
        {
            "doc_id": "a.pdf",
            "doc_type": "x",
            "question": "q",
            "answer": "Not answerable",
            "evidence_pages": "[]",
            "evidence_sources": "[]",
            "answer_format": "None",
        },
        row_idx=1,
    )

    assert question.answerable is False
    assert question.evidence_types == ()


@pytest.mark.parametrize(
    ("prediction", "gold", "answer_format", "expected"),
    [
        ("They see it as less well-off.", "Less well-off", "Str", True),
        ("Better off", "Less well-off", "Str", False),
        ("Revenue was 1,234.5 million.", "1234.5", "Float", True),
        ("Revenue was 1,300 million.", "1234.5", "Float", False),
        ("There are five figures.", "5", "Int", True),
        ("About 59% of seniors.", "59%", "Str", True),
        ("Apple, Banana and cherry", "['apple', 'banana', 'cherry']", "List", True),
        ("Apple and cherry", "['apple', 'banana', 'cherry']", "List", False),
        ("anything", "Not answerable", "None", False),
    ],
)
def test_answer_matching(prediction, gold, answer_format, expected):
    assert answer_matches(prediction, gold, answer_format) is expected


def test_page_hit_needs_the_same_document_and_an_evidence_page():
    results = [("other_pdf", 5), ("pip_seniors_pdf", 7)]

    assert page_hit(results, "pip_seniors_pdf", (7, 9)) is True
    assert page_hit(results, "pip_seniors_pdf", (5,)) is False
    assert page_hit([], "pip_seniors_pdf", (5,)) is False


def _q(row_idx, types, answerable=True):
    return parse_question(
        {
            "doc_id": "a.pdf",
            "doc_type": "x",
            "question": f"q{row_idx}",
            "answer": "x" if answerable else "Not answerable",
            "evidence_pages": "[1]" if answerable else "[]",
            "evidence_sources": repr(list(types)),
            "answer_format": "Str" if answerable else "None",
        },
        row_idx=row_idx,
    )


def test_report_slices_every_stage_by_evidence_type():
    outcomes = [
        QuestionOutcome(
            question=_q(1, ["Pure-text (Plain-text)"]),
            ingested=True,
            retrieved_top_k=True,
            retrieved_candidates=True,
            answered=True,
            correct=True,
            citation_on_evidence=True,
            acl_leaks=0,
        ),
        QuestionOutcome(
            question=_q(2, ["Chart", "Pure-text (Plain-text)"]),
            ingested=False,
            retrieved_top_k=False,
            retrieved_candidates=False,
            answered=False,
            correct=False,
            citation_on_evidence=None,
            acl_leaks=0,
        ),
        QuestionOutcome(
            question=_q(3, [], answerable=False),
            ingested=None,
            retrieved_top_k=None,
            retrieved_candidates=None,
            answered=False,
            correct=None,
            citation_on_evidence=None,
            acl_leaks=0,
        ),
    ]

    report = build_report(outcomes, top_k=5, candidate_k=20)

    text = report["slices"]["text"]
    assert text["questions"] == 2
    assert text["ingestion_evidence_page_coverage"] == {"rate": 0.5, "n": 2}
    assert text["retrieval_hit_at_5"] == {"rate": 0.5, "n": 2}
    assert text["retrieval_hit_at_20"] == {"rate": 0.5, "n": 2}
    assert text["answer_accuracy"] == {"rate": 0.5, "n": 2}
    assert text["citation_accuracy"] == {"rate": 1.0, "n": 1}

    chart = report["slices"]["chart"]
    assert chart["questions"] == 1
    assert chart["answer_accuracy"] == {"rate": 0.0, "n": 1}

    assert report["slices"]["layout"]["questions"] == 0
    assert report["answerability"] == {
        "unanswerable_correctly_refused": {"rate": 1.0, "n": 1},
        "answerable_coverage": {"rate": 0.5, "n": 2},
    }
    assert report["overall"]["questions"] == 3
    assert report["acl_leaks"] == 0


def test_cited_pages_resolve_support_ids_through_their_section_labels():
    from app.evaluation.mmlongbench import cited_pages

    units = [
        {"support_id": "E1.S1", "source_id": "a_pdf", "section_label": "page 3"},
        {"support_id": "E2.S4", "source_id": "b_pdf", "section_label": "page 12"},
        {"support_id": "E3.S1", "source_id": "c_md", "section_label": "Kurulum > Adım 1"},
    ]

    answer = "Revenue grew [E2.S4]; see also [E1.S1] and [E3.S1] and [E9.S9]."

    assert cited_pages(answer, units) == [("b_pdf", 12), ("a_pdf", 3)]
    assert cited_pages("No citations here.", units) == []


@pytest.mark.parametrize(
    ("prediction", "gold", "answer_format", "expected"),
    [
        # Support-id markers are citations, not numbers in the answer.
        ("No count is given. [E1.S2]", "2", "Int", False),
        ("Two figures. [E1.S2]", "2", "Int", True),
        # A hyphenated range is two positive numbers, not a negative one.
        ("Data from 1981-1982.", "['1981', '1982']", "List", True),
        ("Data from 1981-1982.", "-1982", "Int", False),
    ],
)
def test_answer_matching_ignores_citations_and_reads_ranges(
    prediction, gold, answer_format, expected
):
    assert answer_matches(prediction, gold, answer_format) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"abstain": False, "validator_failure_codes": []}, "answered"),
        ({"abstain": True, "validator_failure_codes": []}, "model_abstained"),
        (
            {"abstain": True, "validator_failure_codes": ["CRITICAL_VALUE_INDETERMINATE"]},
            "validator_blocked",
        ),
        (
            {"abstain": True, "validator_failure_codes": ["TOP_LEVEL_SCHEMA_INVALID"]},
            "output_invalid",
        ),
        ({"abstain": None, "validator_failure_codes": None}, "no_verdict"),
    ],
)
def test_response_kind_separates_refusals_by_their_source(raw, expected):
    from app.evaluation.mmlongbench import response_kind

    assert response_kind(raw) == expected


def test_an_invalid_output_is_not_a_correct_refusal():
    def outcome(row_idx, kind):
        return QuestionOutcome(
            question=_q(row_idx, [], answerable=False),
            ingested=None,
            retrieved_top_k=None,
            retrieved_candidates=None,
            answered=kind == "answered",
            correct=None,
            citation_on_evidence=None,
            acl_leaks=0,
            response_kind=kind,
        )

    report = build_report(
        [outcome(1, "model_abstained"), outcome(2, "output_invalid"), outcome(3, "answered")],
        top_k=5,
        candidate_k=15,
    )

    assert report["answerability"]["unanswerable_correctly_refused"] == {"rate": 0.3333, "n": 3}
    assert report["response_kinds"] == {"answered": 1, "model_abstained": 1, "output_invalid": 1}


def test_outcomes_can_be_rebuilt_from_saved_results():
    from app.evaluation.mmlongbench import outcome_from_result

    question = _q(1, ["Pure-text (Plain-text)"])
    raw = {
        "answer": "It is x. [E1.S1]",
        "abstain": False,
        "validator_failure_codes": [],
        "top_pages": [["a_pdf", 1]],
        "candidate_pages": [["a_pdf", 1]],
        "cited_pages": [["a_pdf", 1]],
        "acl_leaks": 0,
        "evidence_page_chars": {"1": 120},
    }

    outcome = outcome_from_result(question, raw, source_id="a_pdf")

    assert outcome.ingested is True
    assert (outcome.retrieved_top_k, outcome.retrieved_candidates) == (True, True)
    assert (outcome.answered, outcome.correct, outcome.citation_on_evidence) == (True, True, True)
    assert outcome.response_kind == "answered"


# --- where a wrong answer was lost -----------------------------------------


def _raw(answer="I could not find this.", top=True, page_text=True, evidence_text=True):
    return {
        "answer": answer,
        "abstain": False,
        "validator_failure_codes": [],
        "top_pages": [["a_pdf", 1]] if top else [["a_pdf", 9]],
        "candidate_pages": [["a_pdf", 1]],
        "cited_pages": [],
        "acl_leaks": 0,
        "evidence_page_chars": {"1": 120},
        "gold_in_page_text": page_text,
        "gold_in_evidence": evidence_text,
    }


def test_gold_visible_finds_the_gold_answer_in_text():
    from app.evaluation.mmlongbench import gold_visible

    question = _q(1, ["Pure-text (Plain-text)"])

    assert gold_visible(question, ["nothing here", "the value is x"]) is True
    assert gold_visible(question, ["nothing here"]) is False
    assert gold_visible(_q(2, [], answerable=False), ["x"]) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_raw(answer="It is x."), None),
        (_raw(page_text=False), "not_in_page_text"),
        (_raw(top=False), "retrieval"),
        (_raw(evidence_text=False), "assembly"),
        (_raw(), "generation"),
    ],
)
def test_a_wrong_answer_is_attributed_to_the_first_stage_that_lost_the_gold(raw, expected):
    from app.evaluation.mmlongbench import outcome_from_result

    outcome = outcome_from_result(_q(1, ["Pure-text (Plain-text)"]), raw, source_id="a_pdf")

    assert outcome.loss_stage == expected


def test_unanswerable_questions_have_no_loss_stage():
    from app.evaluation.mmlongbench import outcome_from_result

    outcome = outcome_from_result(_q(1, [], answerable=False), _raw(), source_id="a_pdf")

    assert outcome.loss_stage is None


def test_report_counts_loss_stages_and_gold_visibility():
    from app.evaluation.mmlongbench import outcome_from_result

    question = _q(1, ["Pure-text (Plain-text)"])
    outcomes = [
        outcome_from_result(question, _raw(answer="It is x."), source_id="a_pdf"),
        outcome_from_result(question, _raw(evidence_text=False), source_id="a_pdf"),
        outcome_from_result(question, _raw(), source_id="a_pdf"),
    ]

    report = build_report(outcomes, top_k=5, candidate_k=15)

    assert report["loss_stages"] == {"assembly": 1, "generation": 1}
    assert report["overall"]["gold_in_evidence"] == {"rate": 0.6667, "n": 3}


def test_with_gold_page_evidence_retrieval_is_not_a_loss_stage():
    from app.evaluation.mmlongbench import outcome_from_result

    raw = {**_raw(top=False), "evidence": "gold_page"}
    outcome = outcome_from_result(_q(1, ["Pure-text (Plain-text)"]), raw, source_id="a_pdf")

    assert outcome.loss_stage == "generation"


# --- scorer audit fixes (luna RAG pilot) -----------------------------------


def test_cited_pages_read_page_fields_and_labels_with_a_section_path():
    from app.evaluation.mmlongbench import cited_pages

    units = [
        {"support_id": "E1.S1", "source_id": "a_pdf", "section_label": "4 Experiments (page 8)"},
        {"support_id": "E1.S2", "source_id": "a_pdf", "section_label": "Results (pages 5–6)"},
        {
            "support_id": "E2.S1",
            "source_id": "b_pdf",
            "section_label": "Board of Directors",
            "page_number": 9,
            "page_end": 10,
        },
    ]

    answer = "x [E1.S1] y [E1.S2] z [E2.S1]"

    assert cited_pages(answer, units) == [
        ("a_pdf", 8),
        ("a_pdf", 5),
        ("a_pdf", 6),
        ("b_pdf", 9),
        ("b_pdf", 10),
    ]


@pytest.mark.parametrize(
    ("prediction", "gold", "answer_format", "expected"),
    [
        # The answer is the first number the answer states, not any number
        # mentioned on the way.
        ("Port 3 has the functions for pins 10 to 13.", "13", "Int", False),
        ("41% of seniors do not go online, 59% do.", "59", "Int", False),
        ("41% of seniors do not go online, 59% do.", "41", "Int", True),
        ("The gap is 12.0 points (65% vs 53%).", "12%", "Float", True),
        ("It is listed for two parts: 8052AH and 8751BH.", "2", "Int", True),
        # A one-letter slip in a long gold item is the gold's typo.
        ("Union Bank of India and Bank of Baroda", "['Unioon Bank of India']", "List", True),
        ("Bank of Baroda", "['Bank of India']", "List", False),
    ],
)
def test_answer_matching_reads_the_stated_number_and_tolerates_gold_typos(
    prediction, gold, answer_format, expected
):
    assert answer_matches(prediction, gold, answer_format) is expected


@pytest.mark.parametrize(
    ("gold", "answer_format"),
    [("2", "Int"), ("0.0", "Float"), ("['12', '13', '16']", "List")],
)
def test_small_number_golds_are_not_measured_in_page_text(gold, answer_format):
    from app.evaluation.mmlongbench import gold_visible

    question = parse_question(
        {
            "doc_id": "a.pdf",
            "doc_type": "x",
            "question": "q",
            "answer": gold,
            "evidence_pages": "[1]",
            "evidence_sources": "[]",
            "answer_format": answer_format,
        },
        row_idx=1,
    )

    # Any page holds a "2"; finding one says nothing about the answer.
    assert gold_visible(question, ["Table 2 lists 12, 13 and 16 items, 0.0 loss."]) is None


def test_an_unmeasured_gold_is_its_own_loss_stage():
    from app.evaluation.mmlongbench import outcome_from_result

    raw = {**_raw(), "gold_in_page_text": None, "gold_in_evidence": None}

    outcome = outcome_from_result(_q(1, ["Pure-text (Plain-text)"]), raw, source_id="a_pdf")

    assert outcome.loss_stage == "unmeasured"


def test_the_evidence_pages_the_model_saw_are_measured_and_lose_as_assembly():
    from app.evaluation.mmlongbench import outcome_from_result

    question = _q(1, ["Pure-text (Plain-text)"])
    unseen = {**_raw(), "seen_pages": [["a_pdf", 5]], "gold_in_page_text": None}
    seen = {**_raw(answer="It is x."), "seen_pages": [["a_pdf", 1]]}

    lost = outcome_from_result(question, unseen, source_id="a_pdf")
    found = outcome_from_result(question, seen, source_id="a_pdf")
    report = build_report([lost, found], top_k=5, candidate_k=15)

    # Retrieval found page 1, but the model was shown page 5 only.
    assert lost.loss_stage == "assembly"
    assert report["overall"]["evidence_page_seen"] == {"rate": 0.5, "n": 2}


# --- focused v2 question set -----------------------------------------------


def _row(doc, sources, answer="x"):
    return {"doc_id": doc, "evidence_sources": repr(sources), "answer": answer}


def test_the_focused_set_keeps_text_table_and_layout_questions_and_few_refusals():
    from app.evaluation.mmlongbench import select_focused_rows

    table = [
        _row("a.pdf", ["Table"]),
        _row("a.pdf", ["Figure"]),  # image-only: chunking cannot reach it
        _row("a.pdf", ["Chart", "Pure-text (Plain-text)"]),
        _row("a.pdf", [], "Not answerable"),
        _row("a.pdf", [], "Not answerable"),
        _row("a.pdf", [], "Not answerable"),
        _row("b.pdf", ["Generalized-text (Layout)"]),
        _row("c.pdf", ["Table"]),  # not a selected document
    ]

    assert select_focused_rows(table, ["a.pdf", "b.pdf"], unanswerable_per_doc=2) == [
        0,
        2,
        3,
        4,
        6,
    ]


def _numeric_question(gold: str, answer_format: str = "Float"):
    return parse_question(
        {
            "doc_id": "a.pdf",
            "doc_type": "x",
            "question": "q",
            "answer": gold,
            "evidence_pages": "[38]",
            "evidence_sources": "['Table']",
            "answer_format": answer_format,
        },
        row_idx=1,
    )


@pytest.mark.parametrize(
    ("gold", "page"),
    [
        ("18078", "ASSETS: Noncontrolling interests | 514 | 421 / TOTAL EQUITY | 18,078 | 18,705"),
        ("1358000", "In 2021 and 2020 we repurchased 1,358,000 and 643,000 shares."),
        ("495.00", "prices of $364.39 and $308.45, totaling approximately $495 and $198."),
    ],
)
def test_a_numeric_gold_anywhere_in_the_page_text_is_visible(gold, page):
    # v2 audit: gold_visible reused answer scoring, which reads only the
    # first number an answer states, so a page counted as missing the gold
    # unless the gold was the page's first number (11 of 23 losses).
    from app.evaluation.mmlongbench import gold_visible

    assert gold_visible(_numeric_question(gold), [page]) is True


def test_a_page_number_only_close_to_the_gold_does_not_make_it_visible():
    # A page is full of numbers; 1% tolerance would find 811 for 815.
    from app.evaluation.mmlongbench import gold_visible

    assert gold_visible(_numeric_question("815", "Int"), ["We operated 811 warehouses."]) is False


# MMLongBench-Doc-V2 (VectifyAI) corrects 106 gold answers and rewrites
# ambiguous questions, keeping V1's row order and dropping 20 rows. A V1 row
# takes its V2 sample's fields; rows are aligned in order by document, and a
# pair that shares no question text, answer or evidence pages is not taken as
# the same question.

from app.evaluation.mmlongbench import corrected_rows  # noqa: E402


def _v1v2_row(doc, question, answer, pages="[1]"):
    return {
        "doc_id": doc,
        "doc_type": "Report",
        "question": question,
        "answer": answer,
        "answer_format": "Str",
        "evidence_pages": pages,
        "evidence_sources": "['Pure-text (Plain-text)']",
    }


def test_v1_rows_take_their_v2_corrections_in_order():
    v1 = [
        _v1v2_row("a.pdf", "What is long-term debt?", "10314"),
        _v1v2_row("a.pdf", "What is the gap?", "73.0", "[16]"),
        _v1v2_row("b.pdf", "Dropped question", "x"),
        _v1v2_row("c.pdf", "Who wrote it?", "Ann"),
    ]
    v2 = [
        _v1v2_row("a.pdf", "What is long-term debt, including leases?", "10314"),
        _v1v2_row("a.pdf", "What is the gap?", "12.0", "[16]"),
        _v1v2_row("c.pdf", "Who wrote it?", "Ann"),
    ]

    rows = corrected_rows(v1, v2)

    assert rows[0]["question"] == "What is long-term debt, including leases?"
    assert rows[1]["answer"] == "12.0"
    assert rows[2] is None
    assert rows[3]["answer"] == "Ann"


def test_a_misaligned_v2_file_is_refused():
    v1 = [_v1v2_row("a.pdf", "What is the revenue in 2021?", "5", "[2]")]
    v2 = [_v1v2_row("a.pdf", "Who signed off?", "Acme", "[9]")]

    with pytest.raises(ValueError):
        corrected_rows(v1, v2)


def test_a_v2_refusal_gold_that_also_accepts_zero_is_unanswerable():
    # V2 labels 14 questions "Not answerable or 0 or none": a refusal is right.
    row = _v1v2_row("a.pdf", "What time does the red bar start?", "Not answerable or 0 or none")
    row["evidence_pages"] = "[]"
    row["evidence_sources"] = "[]"

    assert parse_question(row, 475).answerable is False


# V2 audit, category A: answers right in substance that the contains-match
# missed. 1020 and 1023 state a ratio as a percentage (gold 0.25, 0.192); 1025
# states a share count in thousands ("1,358 (000's)", gold 1358000).
@pytest.mark.parametrize(
    ("prediction", "gold", "answer_format", "expected"),
    [
        (
            "Long-term Debt to Total Liabilities is 25.04%. "
            "(calculation: (6692 + 2642 + 980) / 41190 * 100 = 25.04) [E1.S50]",
            "0.25",
            "Float",
            True,
        ),
        (
            "total debt to total assets: 19.25% (calculation: (799 + 6692 + 3916) "
            "/ 59268 * 100 = 19.25)",
            "0.192",
            "Float",
            True,
        ),
        ("Costco repurchased 1,358 (000’s) shares in FY2021. [E1.S153]", "1358000", "Int", True),
        ("It spent $495 million on repurchases.", "495", "Int", True),
        ("The ratio is 12.64%.", "0.192", "Float", False),
        ("The rate is 25%.", "0.25%", "Float", False),
        ("The ratio is 0.25.", "25", "Float", False),
    ],
)
def test_answer_matching_reads_percentages_and_thousands(prediction, gold, answer_format, expected):
    assert answer_matches(prediction, gold, answer_format) is expected
