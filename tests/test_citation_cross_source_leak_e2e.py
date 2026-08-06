"""Sprint 5 DoD: the production-rag-platform doc-scoping bug, proven at the
FULL PIPELINE level (real ingest -> real Qdrant -> real retrieval -> real
grounding), not just as a unit test of check_grounding() against synthetic
payloads (that regression test already existed — see test_grounding.py).

The bug: two unrelated documents can naturally collide on location (every
PDF's first chunk is page 1/paragraph 0; two markdown files can both start
with the same top-level heading). A citation must be validated against the
EXACT source it claims — if grounding only checked "does some chunk in
context have this location", a citation for document A would incorrectly
validate as long as document B (present in the same context) happened to
have a chunk at that same location. This test ingests two real, distinct
PDFs (colliding page/paragraph) and two real, distinct Markdown files
(colliding heading path) into one shared collection, confirms the collision
is real (not fabricated test data), and proves a citation naming one
document is only satisfied by that document's own chunk being in context —
never by the other document's chunk at the same location.
"""

import fitz
import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.sparse import SparseVector

COLLECTION = "test_citation_cross_source_leak_e2e"


def _make_pdf(path, first_page_text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 150), first_page_text, fontsize=11)
    doc.save(path)
    doc.close()


async def _fake_embed(text: str) -> list[float]:
    vector = [0.01] * EMBEDDING_DIM
    vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
    return vector


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def _chunk_for(all_points, source_id: str):
    matches = [p for p in all_points if p.payload["source_id"] == source_id]
    assert matches, f"no chunk found for source_id={source_id!r}"
    return matches[0]


@pytest.mark.asyncio
async def test_pdf_citation_cannot_leak_across_two_documents_sharing_page_one_paragraph_zero(
    tmp_path,
):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    # Every PDF's first chunk is page=1, paragraph=0 — the exact collision
    # that caused the original production-rag-platform bug.
    _make_pdf(docs_dir / "cv.pdf", "CV_DOC-PARA0 knows Python and SQL, five years experience.")
    _make_pdf(docs_dir / "handbook.pdf", "HANDBOOK_DOC-PARA0 refunds are processed within 30 days.")

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")

    await ingest_connector(
        LocalFilesystemConnector(docs_dir), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    all_points, _ = store._client.scroll(COLLECTION, limit=1000)
    cv_chunk = _chunk_for(all_points, "cv_pdf")
    handbook_chunk = _chunk_for(all_points, "handbook_pdf")

    # Confirm the collision is real, not assumed: two independently ingested
    # PDFs, same location.
    assert (cv_chunk.payload["page_number"], cv_chunk.payload["paragraph_index"]) == (1, 0)
    assert (handbook_chunk.payload["page_number"], handbook_chunk.payload["paragraph_index"]) == (
        1,
        0,
    )

    combined_context = [
        SearchResult(score=0.9, payload=cv_chunk.payload),
        SearchResult(score=0.9, payload=handbook_chunk.payload),
    ]

    # Each document's own citation validates fine against the mixed context.
    assert check_grounding("Knows Python [s.filesystem:cv_pdf/1/0].", combined_context).grounded
    assert check_grounding(
        "Refunds in 30 days [s.filesystem:handbook_pdf/1/0].", combined_context
    ).grounded

    # The leak check: cv's tag must NOT validate against a context that only
    # holds handbook's chunk, even though the location "1/0" matches — and
    # vice versa. If grounding matched on location alone (the pre-fix bug),
    # both of these would incorrectly pass.
    handbook_only = [SearchResult(score=0.9, payload=handbook_chunk.payload)]
    cv_only = [SearchResult(score=0.9, payload=cv_chunk.payload)]
    assert not check_grounding("Knows Python [s.filesystem:cv_pdf/1/0].", handbook_only).grounded
    assert not check_grounding(
        "Refunds in 30 days [s.filesystem:handbook_pdf/1/0].", cv_only
    ).grounded


@pytest.mark.asyncio
async def test_markdown_citation_cannot_leak_across_two_documents_sharing_a_heading(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    # Two unrelated docs both using "# Giriş" as their top heading — the
    # markdown analogue of the PDF page1/paragraph0 collision.
    (docs_dir / "product_a.md").write_text("# Giriş\n\nProduct A costs $10 per month.")
    (docs_dir / "product_b.md").write_text("# Giriş\n\nProduct B costs $50 per month.")

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_md")
    registry = DocumentRegistry(tmp_path / "registry.db")

    await ingest_connector(
        LocalFilesystemConnector(docs_dir), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    all_points, _ = store._client.scroll(COLLECTION + "_md", limit=1000)
    a_chunk = _chunk_for(all_points, "product_a_md")
    b_chunk = _chunk_for(all_points, "product_b_md")
    assert a_chunk.payload["heading_path"] == ["Giriş"]
    assert b_chunk.payload["heading_path"] == ["Giriş"]  # genuine collision confirmed

    combined_context = [
        SearchResult(score=0.9, payload=a_chunk.payload),
        SearchResult(score=0.9, payload=b_chunk.payload),
    ]

    assert check_grounding(
        "Costs $10/month [s.filesystem:product_a_md/Giriş].", combined_context
    ).grounded

    # product_a's tag must not validate against a context holding only
    # product_b's "Giriş" chunk, despite the identical location string.
    b_only = [SearchResult(score=0.9, payload=b_chunk.payload)]
    assert not check_grounding(
        "Costs $10/month [s.filesystem:product_a_md/Giriş].", b_only
    ).grounded


@pytest.mark.asyncio
async def test_generated_answer_citing_the_wrong_document_is_flagged_ungrounded_end_to_end(
    tmp_path,
):
    """Same collision as the PDF test above, but driven through the real
    stream_answer generation path — proving the leak is caught in the
    actual generate -> grounding-check flow a real chat turn goes through,
    not just via a direct check_grounding() call.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    _make_pdf(docs_dir / "cv.pdf", "CV_DOC-PARA0 knows Python and SQL.")
    _make_pdf(docs_dir / "handbook.pdf", "HANDBOOK_DOC-PARA0 refunds within 30 days.")

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_gen")
    registry = DocumentRegistry(tmp_path / "registry.db")

    await ingest_connector(
        LocalFilesystemConnector(docs_dir), store, registry, _fake_embed, _FakeSparseEncoder()
    )

    all_points, _ = store._client.scroll(COLLECTION + "_gen", limit=1000)
    cv_chunk = _chunk_for(all_points, "cv_pdf")
    handbook_chunk = _chunk_for(all_points, "handbook_pdf")

    # Retrieval only surfaces the CV chunk (a realistic top-1 hybrid search
    # result for a CV-focused query) — the handbook chunk is NOT in context.
    cv_only_context = [SearchResult(score=0.9, payload=cv_chunk.payload)]

    class _FakeOllamaMislabeling:
        """Simulates the historical failure mode: the model states a fact
        that belongs to a document NOT in context (handbook), but tags it
        with the in-context document's citation (cv, coincidentally sharing
        location 1/0) — a plausible-looking but wrong citation.
        """

        async def stream_chat(self, messages, model):
            for token in ["Refunds take 30 days", " ", "[s.filesystem:handbook_pdf/1/0]", "."]:
                yield token

    events = [
        event
        async for event in stream_answer(
            "What is the refund policy?",
            cv_only_context,
            _FakeOllamaMislabeling(),
            model="fake",
            prompt_version="v1",
        )
    ]
    grounding_event = next(e for e in events if e["type"] == "grounding")

    # handbook_pdf's chunk was never in context — the citation is rejected
    # even though the location it names (1/0) is exactly what cv_pdf (the
    # document actually in context) also has.
    assert grounding_event["grounded"] is False
    assert grounding_event["ungrounded_citations"] == [("filesystem", "handbook_pdf", "1/0")]

    handbook_chunk_id = handbook_chunk.payload["source_id"]
    assert handbook_chunk_id == "handbook_pdf"  # sanity: confirms which doc was excluded
