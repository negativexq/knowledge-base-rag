"""Every PDF ingest produces a quality report: how many pages were read with
OCR and why, pages skipped, garbled blocks dropped, empty pages, and how much
structure was found. The report is stored with the document in the registry
and served by /ui/documents, so a badly indexed document is visible."""

import json
import logging
import sqlite3

import fitz
import pytest
from qdrant_client import QdrantClient

import app.parsing.pdf_parser as pdf_parser
from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.chunker import chunk_document
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.parsing.models import ParseReport
from app.parsing.pdf_parser import extract_elements
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector


def _report_pdf(tmp_path, name="report.pdf") -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Annual Report", fontsize=22)
    page.insert_text((72, 100), "Revenue", fontsize=15)
    page.insert_text((72, 125), "Revenue grew in every region this year.", fontsize=11)
    page = doc.new_page()
    page.insert_text((72, 60), "Revenue held up in the second half.", fontsize=11)
    path = tmp_path / name
    doc.save(path)
    return str(path)


def _scanned_pdf(tmp_path) -> str:
    source = fitz.open()
    source.new_page(width=420, height=160).insert_text((30, 80), "Scanned text", fontsize=22)
    pixmap = source[0].get_pixmap(dpi=100)
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "A page with text.", fontsize=11)
    scanned = doc.new_page(width=420, height=160)
    scanned.insert_image(scanned.rect, pixmap=pixmap)
    path = tmp_path / "scanned.pdf"
    doc.save(path)
    return str(path)


def test_a_clean_pdf_reports_its_structure(tmp_path):
    report = ParseReport()
    extract_elements(_report_pdf(tmp_path), report=report)

    assert report.as_dict() == {
        "pages": 2,
        "ocr_pages": {},
        "skipped_pages": 0,
        "garbled_blocks_dropped": 0,
        "empty_pages": 0,
        "headings": 2,
        "tables": 0,
        "furniture": 0,
        "heading_source": "layout",
        "needs_review": False,
    }


def test_a_scan_without_ocr_is_a_skipped_empty_page(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: False)
    report = ParseReport()
    with caplog.at_level(logging.WARNING, logger="app.parsing.pdf_parser"):
        extract_elements(_scanned_pdf(tmp_path), report=report)

    assert report.skipped_pages == 1
    assert report.empty_pages == 1
    assert report.as_dict()["needs_review"] is True


def test_ocr_pages_are_counted_by_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(
        pdf_parser, "_ocr_blocks", lambda page: [(30, 60, 390, 100, "Scanned text\n", 0, 0)]
    )
    report = ParseReport()
    extract_elements(_scanned_pdf(tmp_path), report=report)

    assert report.ocr_pages == {"no_text_layer": 1}
    assert report.as_dict()["needs_review"] is False


def test_bookmarks_are_named_as_the_heading_source(tmp_path):
    path = _report_pdf(tmp_path)
    with fitz.open(path) as doc:
        doc.set_toc([[1, "Annual Report", 1]])
        doc.save(tmp_path / "bookmarked.pdf")
    report = ParseReport()
    extract_elements(str(tmp_path / "bookmarked.pdf"), report=report)

    assert report.heading_source == "bookmarks"


def test_chunk_document_fills_a_report(tmp_path):
    report = ParseReport()
    chunk_document(_report_pdf(tmp_path), source_id="r", report=report)

    assert report.pages == 2


def test_registry_stores_the_quality_report(tmp_path):
    registry = DocumentRegistry(tmp_path / "registry.db")
    quality = {"pages": 3, "needs_review": True}
    registry.upsert_document("t", "filesystem", "a.pdf", "h", ingestion_quality=quality)
    registry.upsert_document("t", "filesystem", "b.md", "h")

    assert registry.get_document("t", "filesystem", "a.pdf").ingestion_quality == quality
    assert registry.get_document("t", "filesystem", "b.md").ingestion_quality is None


def test_an_existing_registry_gains_the_column(tmp_path):
    path = tmp_path / "registry.db"
    DocumentRegistry(path).upsert_document("t", "filesystem", "a.pdf", "h")
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE documents DROP COLUMN ingestion_quality")

    registry = DocumentRegistry(path)

    assert registry.get_document("t", "filesystem", "a.pdf").ingestion_quality is None


class _Sparse:
    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[1], values=[1.0])


@pytest.mark.asyncio
async def test_ingestion_records_the_report_for_pdfs_only(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _report_pdf(docs)
    (docs / "notes.md").write_text("# Notes\n\nPlain text.")

    async def embed(text: str) -> list[float]:
        return [0.1] * EMBEDDING_DIM

    registry = DocumentRegistry(tmp_path / "registry.db")
    await ingest_connector(
        LocalFilesystemConnector(docs),
        QdrantStore(client=QdrantClient(":memory:"), collection_name="quality"),
        registry,
        embed,
        _Sparse(),
    )

    records = {r.source_id: r for r in registry.list_documents()}
    [pdf] = [r for sid, r in records.items() if sid.endswith("pdf")]
    [md] = [r for sid, r in records.items() if sid.endswith("md")]
    assert pdf.ingestion_quality["pages"] == 2
    assert md.ingestion_quality is None
    json.dumps(pdf.ingestion_quality)


def test_documents_endpoint_serves_the_quality_report(tmp_path):
    from tests.test_api_ui import _auth, _client

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    _report_pdf(docs_dir)
    client = _client(tmp_path, docs_dir)
    client.post("/sync/filesystem", headers=_auth("token-operator-a"))

    [document] = client.get("/ui/documents", headers=_auth("token-user-a")).json()

    assert document["ingestion_quality"]["pages"] == 2
    assert document["ingestion_quality"]["needs_review"] is False
