"""Hermetic end-to-end proof of the Sprint 0 DoD: a single real PDF goes
through parse -> chunk -> embed -> upsert -> hybrid retrieve -> rerank ->
grounded generation -> citation formatting, using the new multi-source
citation tag format end to end.

Ollama and the cross-encoder/sparse models are the only pieces stood in for
(no network, no multi-hundred-MB model downloads required to prove the
pipeline wiring) — everything else (PyMuPDF parsing, chunking, real Qdrant
:memory: hybrid search with RRF fusion, grounding regex, citation
highlighting) runs for real. tests/test_ingest_e2e.py and
tests/test_generation_e2e.py cover the fully-real-services path and skip
automatically when Ollama/Qdrant aren't running locally.
"""

import shutil

import pytest
from qdrant_client import QdrantClient

from app.ingestion.ingest import ingest_path
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.search import search
from app.retrieval.sparse import SparseVector
from app.ui.citation_formatting import highlight_citations

COLLECTION = "test_pipeline_e2e_hermetic"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        # crude term-presence hash so shared vocabulary produces overlap.
        # Indices are deduped through a set (not just the input words) —
        # Python's string hash is randomized per process (PYTHONHASHSEED),
        # so two different words landing on the same `% 5000` bucket is a
        # real, seed-dependent occurrence, and Qdrant's local mode rejects
        # a sparse vector with duplicate indices.
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))

    def embed_query(self, text: str) -> SparseVector:
        return self.embed_document(text)


class _FakeOllamaEmbed:
    """Deterministic fake dense embedder: puts weight on a dimension chosen
    from the text's content so semantically similar text lands near itself,
    without needing a real model.
    """

    async def embed(
        self, text: str, model: str, prefix: str = "", dimensions: int | None = None
    ) -> list[float]:
        vector = [0.01] * EMBEDDING_DIM
        vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
        return vector


class _FakeOllamaChat:
    """Fake chat model that plays by the CITATION RULE: it 'answers' by
    copying the first context block's ready-made citation tag, proving the
    tag survives from build_context -> generation -> grounding check.
    """

    def __init__(self, tag: str, sentence: str):
        self._tag = tag
        self._sentence = sentence

    async def stream_chat(self, messages, model):
        for token in [self._sentence, " ", self._tag, "."]:
            yield token


@pytest.mark.asyncio
async def test_single_pdf_end_to_end_with_multisource_citation_format(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "handbook.pdf")

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    embedder = _FakeOllamaEmbed()
    sparse_encoder = _FakeSparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await embedder.embed(text, model="fake")

    stats = await ingest_path(
        str(docs_dir), store, embed_fn, sparse_encoder, chunk_size_tokens=20, overlap_tokens=5
    )
    assert stats.files_processed == 1
    assert stats.chunks_upserted > 0
    assert store.count() == stats.chunks_upserted

    scroll_result, _ = store._client.scroll(COLLECTION, limit=1)
    assert scroll_result[0].payload["source_type"] == "pdf"
    assert scroll_result[0].payload["source_id"] == "handbook"

    results: list[SearchResult] = await search(
        "PAGE1-PARA0",
        ollama=embedder,
        sparse_encoder=sparse_encoder,
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="fake",
        top_k=10,
        top_n=3,
    )
    assert results, "hybrid search returned no candidates"

    top = results[0]
    expected_tag = f"[s.pdf:handbook/{top.payload['page_number']}/{top.payload['paragraph_index']}]"
    ollama_chat = _FakeOllamaChat(tag=expected_tag, sentence="This is about the page one topic")

    events = [
        event
        async for event in stream_answer(
            "What is on page one?", results, ollama_chat, model="fake", prompt_version="v1"
        )
    ]

    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert expected_tag in tokens

    grounding_event = next(e for e in events if e["type"] == "grounding")
    assert grounding_event["grounded"] is True
    expected_location = f"{top.payload['page_number']}/{top.payload['paragraph_index']}"
    assert grounding_event["citations_found"] == [("pdf", "handbook", expected_location)]

    # cross-check with the standalone grounding function directly too
    assert check_grounding(tokens, results).grounded is True

    highlighted = highlight_citations(tokens)
    assert f"**{expected_tag}**" in highlighted

    client.delete_collection(COLLECTION)
