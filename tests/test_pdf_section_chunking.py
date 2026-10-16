"""PDF chunks follow the document's sections: a chunk never mixes two
sections, every chunk records the section path it belongs to, and the text
that is embedded and sparse-indexed carries that path as context while the
stored chunk text (what the model reads and citations quote) stays the
source text. Section-aware evidence groups PDF chunks by section."""

import fitz
import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evidence.section_aware import _section_key
from app.evidence.support_units import section_label
from app.ingestion.chunker import chunk_document
from app.ingestion.fingerprint import PipelineFingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.models import Chunk, index_text
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.parsing.pdf_parser import extract_paragraphs
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector


@pytest.fixture
def report_pdf(tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Annual Report", fontsize=22)
    page.insert_text((72, 100), "Revenue", fontsize=15)
    page.insert_text((72, 125), "Revenue grew in every region this year.", fontsize=11)
    page.insert_text((72, 165), "Outlook", fontsize=15)
    page.insert_text((72, 190), "We expect steady demand next year.", fontsize=11)
    page = doc.new_page()
    page.insert_text((72, 60), "The outlook assumes stable prices.", fontsize=11)
    path = tmp_path / "report.pdf"
    doc.save(path)
    return str(path)


def _chunk_with(chunks, text):
    [chunk] = [c for c in chunks if text in c.text]
    return chunk


def test_a_chunk_never_mixes_two_sections(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")

    revenue = _chunk_with(chunks, "Revenue grew")
    assert "steady demand" not in revenue.text
    assert revenue.section_path == ("Annual Report", "Revenue")


def test_a_heading_with_no_body_of_its_own_joins_the_next_section(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")

    assert not [c for c in chunks if c.text == "Annual Report"]
    assert _chunk_with(chunks, "Revenue grew").text.startswith("Annual Report\n\nRevenue")


def test_chunks_record_their_section_path_across_pages(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")

    assert _chunk_with(chunks, "steady demand").section_path == ("Annual Report", "Outlook")
    assert _chunk_with(chunks, "stable prices").section_path == ("Annual Report", "Outlook")
    assert _chunk_with(chunks, "stable prices").heading_path == ()


def test_char_ranges_still_point_into_the_page_text(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")
    pages: dict[int, list[str]] = {}
    for paragraph in extract_paragraphs(report_pdf):
        pages.setdefault(paragraph.page_number, []).append(paragraph.text)

    for chunk in chunks:
        page_text = "\n\n".join(pages[chunk.page_number]) + "\n\n"
        start, end = chunk.char_range
        if chunk.page_crossing:  # anchored where it starts on its first page
            assert chunk.text.startswith(page_text[start:].strip()[:20])
        else:
            assert page_text[start:end].strip() == chunk.text


def test_pdfs_without_headings_chunk_by_page_as_before(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample")

    assert {c.page_number for c in chunks} == {1, 2, 3}
    assert all(c.section_path == () for c in chunks)
    page_one = [c for c in chunks if c.page_number == 1]
    assert len(page_one) == 1
    assert "PAGE1-PARA0" in page_one[0].text and "PAGE1-PARA1" in page_one[0].text


def _chunk(**fields) -> Chunk:
    base = dict(
        doc_id="d",
        source_type="pdf",
        source_id="s",
        page_number=3,
        paragraph_index=0,
        char_range=(0, 10),
        text="Values are approximate.",
    )
    return Chunk(**{**base, **fields})


def test_index_text_prefixes_the_section_path():
    chunk = _chunk(section_path=("Packages", "Thermal data"))

    assert index_text(chunk) == "Packages > Thermal data\n\nValues are approximate."


def test_index_text_uses_markdown_headings_and_leaves_plain_chunks_alone():
    assert index_text(_chunk(heading_path=("Setup", "Step 1"))).startswith("Setup > Step 1\n\n")
    assert index_text(_chunk()) == "Values are approximate."


def test_section_label_and_key_use_the_pdf_section():
    payload = {"page_number": 3, "section_path": ["Packages", "Thermal data"]}

    assert section_label(payload) == "Packages > Thermal data (page 3)"
    assert _section_key(payload) == ("section", ("Packages", "Thermal data"))
    assert _section_key({"page_number": 3}) == ("page", 3)


def test_fingerprint_records_the_index_text_mode():
    default = PipelineFingerprint(
        embedding_model="m",
        embedding_revision="r",
        embedding_dimension=3,
        query_instruction="q",
        document_instruction="d",
        index_schema_version=1,
    )
    other = PipelineFingerprint(**{**default.__dict__, "index_text_mode": "body_v1"})

    assert default.index_text_mode == "section_context_v1"
    assert default.digest() != other.digest()


class _RecordingSparse:
    def __init__(self):
        self.texts: list[str] = []

    def embed_document(self, text: str) -> SparseVector:
        self.texts.append(text)
        return SparseVector(indices=[1], values=[1.0])


@pytest.mark.asyncio
async def test_ingestion_embeds_the_section_context_but_stores_the_source_text(
    tmp_path, report_pdf
):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "report.pdf").write_bytes(open(report_pdf, "rb").read())
    embedded: list[str] = []

    async def embed(text: str) -> list[float]:
        embedded.append(text)
        return [0.1] * EMBEDDING_DIM

    sparse = _RecordingSparse()
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name="sections")
    await ingest_connector(
        LocalFilesystemConnector(docs),
        store,
        DocumentRegistry(tmp_path / "registry.db"),
        embed,
        sparse,
    )

    outlook = "Outlook\n\nWe expect steady demand next year.\n\nThe outlook assumes stable prices."
    assert f"Annual Report > Outlook\n\n{outlook}" in embedded
    assert sparse.texts == embedded
    points, _ = client.scroll("sections", limit=50, with_payload=True)
    stored = {p.payload["text"]: p.payload for p in points}
    assert stored[outlook]["section_path"] == ["Annual Report", "Outlook"]
    assert (stored[outlook]["page_number"], stored[outlook]["page_end"]) == (1, 2)
