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
        ({**_raw(), "gold_in_page_text": None, "gold_in_evidence": None}, "generation"),
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
