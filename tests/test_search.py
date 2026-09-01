import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

import app.retrieval.search as search_module
from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import QdrantStore
from app.retrieval.filters import build_filter
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.retrieval.search import RERANK_CANDIDATE_K, SEARCH_QUERY_PREFIX, search
from app.retrieval.sparse import SparseVector
from app.security.models import RetrievalContext


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


COLLECTION = "test_search"


class _FakeOllama:
    def __init__(self):
        self.calls = []

    async def embed(
        self, text: str, model: str, prefix: str = "", dimensions: int | None = None
    ) -> list[float]:
        self.calls.append(
            {"text": text, "model": model, "prefix": prefix, "dimensions": dimensions}
        )
        vector = [0.0] * (dimensions or 768)
        vector[0] = 1.0
        return vector


class _FakeSparseEncoder:
    def embed_query(self, text: str) -> SparseVector:
        return SparseVector(indices=[42], values=[1.0])

    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[42], values=[2.0])


def _chunk(text: str) -> Chunk:
    return Chunk(
        doc_id="doc",
        source_type="pdf",
        source_id="doc",
        page_number=1,
        paragraph_index=0,
        char_range=(0, len(text)),
        text=text,
    )


@pytest.mark.asyncio
async def test_search_applies_search_query_prefix_to_dense_embedding():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    # qdrant-client's local (":memory:") mode raises a KeyError when
    # querying a sparse vector with an IDF modifier against a completely
    # empty collection (confirmed this doesn't happen on a real Qdrant
    # server). Upsert one point first so the local IDF store is initialized.
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    ollama = _FakeOllama()

    await search(
        "what is hybrid search",
        ollama=ollama,
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
    )

    assert ollama.calls[0]["prefix"] == SEARCH_QUERY_PREFIX
    assert ollama.calls[0]["text"] == "what is hybrid search"


@pytest.mark.asyncio
async def test_search_accepts_a_query_prefix_override_for_a_different_embedding_model():
    """Sprint 18: scripts/benchmarks/benchmark_embeddings.py needs to reuse this
    exact function for a challenger embedding model with its own
    instruction format — asserting the override actually reaches
    ollama.embed() (not silently ignored, not blended with
    SEARCH_QUERY_PREFIX) is what proves that reuse doesn't quietly carry
    nomic's prefix over to a different model.
    """
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_prefix_override")
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    ollama = _FakeOllama()

    await search(
        "how many gb of free storage",
        ollama=ollama,
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_prefix_override",
        embed_model="qwen3-embedding:4b",
        context=RetrievalContext(tenant_id="default"),
        query_prefix="Instruct: retrieve relevant passages\nQuery: ",
    )

    assert ollama.calls[0]["prefix"] == "Instruct: retrieve relevant passages\nQuery: "
    assert ollama.calls[0]["prefix"] != SEARCH_QUERY_PREFIX
    assert ollama.calls[0]["model"] == "qwen3-embedding:4b"


@pytest.mark.asyncio
async def test_search_forwards_a_dimensions_override_to_the_embedding_call():
    """Sprint 19: without this, a Matryoshka-truncated config (e.g.
    qwen3-4b@1024) embedded its QUERY at the model's native dimension
    while the collection was indexed at the truncated one — a real
    dimension mismatch Qdrant rejects outright. Reproduced running the
    real benchmark before this parameter existed.
    """
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_dims", dense_dimension=1024)
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 1024],
        [SparseVector(indices=[1], values=[1.0])],
    )
    ollama = _FakeOllama()

    await search(
        "how many gb of free storage",
        ollama=ollama,
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_dims",
        embed_model="qwen3-embedding:4b",
        context=RetrievalContext(tenant_id="default"),
        dimensions=1024,
    )

    assert ollama.calls[0]["dimensions"] == 1024


@pytest.mark.asyncio
async def test_search_without_dimensions_override_leaves_it_none():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_no_dims")
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    ollama = _FakeOllama()

    await search(
        "query",
        ollama=ollama,
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_no_dims",
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
    )

    assert ollama.calls[0]["dimensions"] is None


@pytest.mark.asyncio
async def test_search_returns_hybrid_results():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "2")
    store.ensure_collection()
    dense_vector = [0.0] * 768
    dense_vector[0] = 1.0
    store.upsert_chunks(
        [_chunk("hello world")],
        [dense_vector],
        [SparseVector(indices=[42], values=[2.0])],
    )

    results = await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "2",
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
    )

    assert len(results) == 1
    assert results[0].payload["text"] == "hello world"


@pytest.mark.asyncio
async def test_search_builds_and_passes_filter_from_doc_ids(monkeypatch):
    client = QdrantClient(":memory:")
    captured = {}

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        doc_ids=["doc-a", "doc-b"],
    )

    # User filters remain applied by Qdrant; the server-owned ACL is applied
    # immediately after this one raw retrieval and before reranking.
    expected_user = build_filter(doc_ids=["doc-a", "doc-b"])
    assert captured["filters"] == expected_user


class _FakeReranker:
    def __init__(self):
        self.calls = []

    def rerank(self, query, candidates, top_n):
        self.calls.append({"query": query, "candidates": candidates, "top_n": top_n})
        # deterministic "rerank": reverse the candidate order
        return list(reversed(candidates))[:top_n]


@pytest.mark.asyncio
async def test_search_uses_reranker_when_provided(monkeypatch):
    client = QdrantClient(":memory:")
    hybrid_candidates = [
        SearchResult(score=0.9, payload={"text": "first", "tenant_id": "default"}),
        SearchResult(score=0.5, payload={"text": "second", "tenant_id": "default"}),
    ]

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        return hybrid_candidates

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)
    reranker = _FakeReranker()

    results = await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        reranker=reranker,
        top_n=2,
    )

    assert reranker.calls[0]["query"] == "hello"
    assert reranker.calls[0]["candidates"] == hybrid_candidates
    assert reranker.calls[0]["top_n"] == 2
    assert [r.payload["text"] for r in results] == ["second", "first"]


@pytest.mark.asyncio
async def test_search_records_raw_and_authorized_counts_without_second_retrieval(monkeypatch):
    raw_candidates = [
        SearchResult(
            score=0.9,
            payload={"text": "authorized", "tenant_id": "tenant-a", "source_id": "a"},
        ),
        SearchResult(
            score=0.8,
            payload={
                "text": "private",
                "tenant_id": "tenant-b",
                "source_id": "b",
                "secret": "must-not-leak",
            },
        ),
    ]
    calls = 0

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        nonlocal calls
        calls += 1
        return raw_candidates

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)
    report = RetrievalReport()
    reranker = _FakeReranker()

    results = await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=QdrantClient(":memory:"),
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="tenant-a"),
        reranker=reranker,
        report=report,
    )

    assert calls == 1
    assert report.pre_acl_candidate_count == 2
    assert report.authorized_candidate_count == 1
    assert [result.payload["source_id"] for result in reranker.calls[0]["candidates"]] == ["a"]
    assert [result.payload["source_id"] for result in results] == ["a"]


@pytest.mark.asyncio
async def test_search_records_zero_counts_for_empty_raw_retrieval(monkeypatch):
    calls = 0

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)
    report = RetrievalReport()

    assert (
        await search(
            "missing",
            ollama=_FakeOllama(),
            sparse_encoder=_FakeSparseEncoder(),
            qdrant_client=QdrantClient(":memory:"),
            collection_name=COLLECTION,
            embed_model="nomic-embed-text",
            context=RetrievalContext(tenant_id="tenant-a"),
            report=report,
        )
        == []
    )
    assert calls == 1
    assert report.pre_acl_candidate_count == 0
    assert report.authorized_candidate_count == 0


@pytest.mark.asyncio
async def test_search_reports_unauthorized_only_without_exposing_raw_metadata(monkeypatch):
    raw_candidates = [
        SearchResult(
            score=0.9,
            payload={
                "text": "private",
                "tenant_id": "tenant-b",
                "source_id": "private-source",
                "secret": "must-not-leak",
            },
        )
    ]
    calls = 0

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        nonlocal calls
        calls += 1
        return raw_candidates

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)
    report = RetrievalReport()

    results = await search(
        "private",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=QdrantClient(":memory:"),
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="tenant-a"),
        reranker=_FakeReranker(),
        report=report,
    )

    assert calls == 1
    assert results == []
    assert report.pre_acl_candidate_count == 1
    assert report.authorized_candidate_count == 0
    report_json = str(report.as_dict())
    assert "private-source" not in report_json
    assert "must-not-leak" not in report_json


@pytest.mark.asyncio
async def test_search_isolates_synchronous_reranker_in_worker_thread(monkeypatch):
    client = QdrantClient(":memory:")
    candidates = [SearchResult(score=0.9, payload={"text": "first", "tenant_id": "default"})]
    monkeypatch.setattr(search_module, "hybrid_search", lambda *args, **kwargs: candidates)
    calls = []

    async def fake_to_thread(function, *args):
        calls.append((function, args))
        return function(*args)

    monkeypatch.setattr(search_module.asyncio, "to_thread", fake_to_thread)
    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        reranker=_FakeReranker(),
    )

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_search_propagates_reranker_exceptions_through_worker_thread(monkeypatch):
    client = QdrantClient(":memory:")
    candidates = [SearchResult(score=0.9, payload={"text": "first", "tenant_id": "default"})]
    monkeypatch.setattr(search_module, "hybrid_search", lambda *args, **kwargs: candidates)

    class _FailingReranker:
        def rerank(self, query, candidates, top_n):
            raise RuntimeError("reranker failed")

    with pytest.raises(RuntimeError, match="reranker failed"):
        await search(
            "hello",
            ollama=_FakeOllama(),
            sparse_encoder=_FakeSparseEncoder(),
            qdrant_client=client,
            collection_name=COLLECTION,
            embed_model="nomic-embed-text",
            context=RetrievalContext(tenant_id="default"),
            reranker=_FailingReranker(),
        )


@pytest.mark.asyncio
async def test_search_fetches_rerank_candidate_k_from_hybrid_search_by_default(monkeypatch):
    client = QdrantClient(":memory:")
    captured = {}

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        reranker=_FakeReranker(),
    )

    assert captured["top_k"] == RERANK_CANDIDATE_K


@pytest.mark.asyncio
async def test_search_without_reranker_falls_back_to_hybrid_order_truncated_to_top_n(monkeypatch):
    client = QdrantClient(":memory:")
    hybrid_candidates = [
        SearchResult(score=0.9, payload={"text": "first", "tenant_id": "default"}),
        SearchResult(score=0.5, payload={"text": "second", "tenant_id": "default"}),
        SearchResult(score=0.1, payload={"text": "third", "tenant_id": "default"}),
    ]

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        return hybrid_candidates

    monkeypatch.setattr(search_module, "hybrid_search", fake_hybrid_search)

    results = await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION,
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        top_n=2,
    )

    assert [r.payload["text"] for r in results] == ["first", "second"]


@pytest.mark.asyncio
async def test_search_creates_embed_and_retrieve_spans_with_attributes():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "3")
    store.ensure_collection()
    dense_vector = [0.0] * 768
    dense_vector[0] = 1.0
    store.upsert_chunks(
        [_chunk("hello world")],
        [dense_vector],
        [SparseVector(indices=[42], values=[2.0])],
    )
    tracer, exporter = _local_tracer_with_exporter()

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "3",
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        tracer=tracer,
    )

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "embed_query" in spans
    assert spans["embed_query"].attributes["embed.model"] == "nomic-embed-text"
    assert "retrieve_hybrid" in spans
    assert spans["retrieve_hybrid"].attributes["retrieve.candidate_count"] == 1
    assert spans["retrieve_hybrid"].attributes["retrieve.top_k"] == RERANK_CANDIDATE_K
    assert "retrieve.top_score" in spans["retrieve_hybrid"].attributes


@pytest.mark.asyncio
async def test_search_creates_rerank_span_only_when_reranker_provided():
    client = QdrantClient(":memory:")
    hybrid_candidates = [
        SearchResult(score=0.9, payload={"text": "first", "tenant_id": "default"})
    ]

    def fake_hybrid_search(client_, collection_name, dense_vector, sparse_vector, **kwargs):
        return hybrid_candidates

    import app.retrieval.search as sm

    original = sm.hybrid_search
    sm.hybrid_search = fake_hybrid_search
    try:
        tracer, exporter = _local_tracer_with_exporter()
        await search(
            "hello",
            ollama=_FakeOllama(),
            sparse_encoder=_FakeSparseEncoder(),
            qdrant_client=client,
            collection_name=COLLECTION,
            embed_model="nomic-embed-text",
            context=RetrievalContext(tenant_id="default"),
            reranker=_FakeReranker(),
            top_n=1,
            tracer=tracer,
        )
        span_names = {span.name for span in exporter.get_finished_spans()}
        assert "rerank" in span_names

        tracer2, exporter2 = _local_tracer_with_exporter()
        await search(
            "hello",
            ollama=_FakeOllama(),
            sparse_encoder=_FakeSparseEncoder(),
            qdrant_client=client,
            collection_name=COLLECTION,
            embed_model="nomic-embed-text",
            context=RetrievalContext(tenant_id="default"),
            top_n=1,
            tracer=tracer2,
        )
        span_names2 = {span.name for span in exporter2.get_finished_spans()}
        assert "rerank" not in span_names2
    finally:
        sm.hybrid_search = original


@pytest.mark.asyncio
async def test_search_populates_a_report_with_real_stages_when_given_one():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_report")
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    report = RetrievalReport()

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_report",
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        report=report,
    )

    stage_names = [s.name for s in report.stages]
    assert "query_embedding" in stage_names
    assert "sparse_encoding" in stage_names
    assert "hybrid_retrieval" in stage_names
    # No reranker was passed — the report must not claim one ran.
    assert "rerank" not in stage_names
    assert "truncate_to_top_n" in stage_names
    assert report.acl_applied is True
    assert report.acl_tenant_id == "default"
    assert report.is_system_context is False
    assert all(s.duration_ms >= 0 for s in report.stages)
    assert report.reranker == {
        "enabled": False,
        "model": None,
        "backend": None,
        "candidate_k": 20,
        "top_n": 5,
    }


@pytest.mark.asyncio
async def test_search_report_records_a_rerank_stage_when_a_reranker_is_given():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_report_rerank")
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    report = RetrievalReport()

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_report_rerank",
        embed_model="nomic-embed-text",
        context=RetrievalContext(tenant_id="default"),
        reranker=_FakeReranker(),
        report=report,
    )

    stage_names = [s.name for s in report.stages]
    assert "rerank" in stage_names
    assert "truncate_to_top_n" not in stage_names


@pytest.mark.asyncio
async def test_search_report_reflects_a_system_context_with_no_tenant():
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION + "_report_system")
    store.ensure_collection()
    store.upsert_chunks(
        [_chunk("placeholder")],
        [[0.0] * 768],
        [SparseVector(indices=[1], values=[1.0])],
    )
    report = RetrievalReport()

    await search(
        "hello",
        ollama=_FakeOllama(),
        sparse_encoder=_FakeSparseEncoder(),
        qdrant_client=client,
        collection_name=COLLECTION + "_report_system",
        embed_model="nomic-embed-text",
        context=RetrievalContext.system(),
        report=report,
    )

    assert report.acl_applied is False
    assert report.is_system_context is True
    assert report.acl_tenant_id is None
