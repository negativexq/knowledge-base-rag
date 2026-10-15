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
