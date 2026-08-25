"""Hermetic end-to-end proof of the Sprint 3 DoD: a real folder holding a
real PDF AND a real Markdown file, ingested through ingest_connector in one
call, both retrievable via hybrid search and both producing correctly
formatted, grounded [s.filesystem:<source_id>/<location>] citations —
page/paragraph for the PDF chunk, heading path for the Markdown chunk.

Only Ollama embedding/chat and the sparse encoder are faked (no network, no
model downloads); parsing, chunking, Qdrant (:memory:) hybrid search,
registry (a real SQLite file), and grounding/citation logic all run for
real — same approach as tests/test_pipeline_e2e_hermetic.py in Sprint 0.
"""

import shutil

import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.registry.store import DocumentRegistry
from app.retrieval.search import search
from app.retrieval.sparse import SparseVector
from app.ui.citation_formatting import highlight_citations

COLLECTION = "test_pipeline_connector_e2e_hermetic"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))

    def embed_query(self, text: str) -> SparseVector:
        return self.embed_document(text)


class _FakeOllamaEmbed:
    async def embed(
        self, text: str, model: str, prefix: str = "", dimensions: int | None = None
    ) -> list[float]:
        vector = [0.01] * EMBEDDING_DIM
        vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
        return vector


class _FakeOllamaChat:
    """Answers by copying the ready-made citation tag of the first context
    block it's given — the same trick as Sprint 0's hermetic test, proving
    the tag survives build_context -> generation -> grounding regardless of
    whether that tag is page/paragraph- or heading-path-shaped.
    """

    def __init__(self, tag: str, sentence: str):
        self._tag = tag
        self._sentence = sentence

    async def stream_chat(self, messages, model):
        for token in [self._sentence, " ", self._tag, "."]:
            yield token


async def _ask_and_ground(query, results, expected_tag, sentence, tokens_holder):
    ollama_chat = _FakeOllamaChat(tag=expected_tag, sentence=sentence)
    events = [
        event
        async for event in stream_answer(
            query, results, ollama_chat, model="fake", prompt_version="v1"
        )
    ]
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    tokens_holder.append(tokens)
    grounding_event = next(e for e in events if e["type"] == "grounding")
    return tokens, grounding_event


@pytest.mark.asyncio
async def test_mixed_pdf_and_markdown_folder_end_to_end(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "handbook.pdf")
    (docs_dir / "readme.md").write_text(
        "# Kurulum\n\nBu kurulum bölümü PAGE1-PARA0 ile ilgisizdir ama benzersizdir."
    )

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    embedder = _FakeOllamaEmbed()
    sparse_encoder = _FakeSparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await embedder.embed(text, model="fake")

    stats = await ingest_connector(
        LocalFilesystemConnector(docs_dir), store, registry, embed_fn, sparse_encoder
    )
    assert stats.files_processed == 2
    assert store.count() == stats.chunks_upserted

    # both documents registered under the connector's source_type
    assert registry.get_document("filesystem", "handbook_pdf") is not None
    assert registry.get_document("filesystem", "readme_md") is not None

    # --- PDF chunk: retrieve, generate, ground a page/paragraph citation ---
    pdf_results = await search(
        "PAGE1-PARA0",
        ollama=embedder,
        sparse_encoder=sparse_encoder,
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="fake",
        top_k=10,
        top_n=3,
    )
    pdf_results = [r for r in pdf_results if r.payload["source_id"] == "handbook_pdf"]
    assert pdf_results, "PDF chunk not retrieved"
    pdf_top = pdf_results[0]
    pdf_location = f"{pdf_top.payload['page_number']}/{pdf_top.payload['paragraph_index']}"
    pdf_tag = f"[s.filesystem:handbook_pdf/{pdf_location}]"

    tokens_holder: list[str] = []
    pdf_tokens, pdf_grounding = await _ask_and_ground(
        "What is on page one?", pdf_results, pdf_tag, "This is the PDF answer", tokens_holder
    )
    assert pdf_tag in pdf_tokens
    assert pdf_grounding["grounded"] is True
    assert pdf_grounding["citations_found"] == [("filesystem", "handbook_pdf", pdf_location)]
    assert check_grounding(pdf_tokens, pdf_results).grounded is True
    assert f"**{pdf_tag}**" in highlight_citations(pdf_tokens)

    # --- Markdown chunk: retrieve, generate, ground a heading-path citation ---
    md_results = await search(
        "Kurulum bölümü benzersiz",
        ollama=embedder,
        sparse_encoder=sparse_encoder,
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="fake",
        top_k=10,
        top_n=3,
    )
    md_results = [r for r in md_results if r.payload["source_id"] == "readme_md"]
    assert md_results, "Markdown chunk not retrieved"
    md_top = md_results[0]
    assert md_top.payload["heading_path"] == ["Kurulum"]
    md_tag = "[s.filesystem:readme_md/Kurulum]"

    md_tokens, md_grounding = await _ask_and_ground(
        "What does the Kurulum section say?",
        md_results,
        md_tag,
        "This is the Markdown answer",
        tokens_holder,
    )
    assert md_tag in md_tokens
    assert md_grounding["grounded"] is True
    assert md_grounding["citations_found"] == [("filesystem", "readme_md", "Kurulum")]
    assert check_grounding(md_tokens, md_results).grounded is True
    assert f"**{md_tag}**" in highlight_citations(md_tokens)

    client.delete_collection(COLLECTION)
