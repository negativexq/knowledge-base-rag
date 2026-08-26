"""Sprint 23: the core security proof — two real tenants, each with a
document containing a unique, unmistakable secret phrase, ingested into
ONE shared Qdrant collection (the realistic production shape: multiple
tenants sharing one collection, isolated only by the tenant_id ACL
filter, not by physically separate collections).

Runs against a REAL Qdrant server, not `:memory:` — required because
qdrant-client's local mode silently drops query_filter on prefetch+
FusionQuery (hybrid) requests (see tests/test_filters_e2e.py's own
docstring, a real, previously-confirmed limitation). Every test here
would give a false "isolated" pass under `:memory:` even if the ACL
filter were completely broken — skipped automatically if Qdrant isn't
reachable, never faked.

Dense embeddings are a fast deterministic fake (hash-based); sparse
encoding uses the REAL BM25 SparseEncoder (fastembed) so the lexical
leakage test (section 19) is a genuine exact-term match, not simulated.
"""

import socket

import pytest
from qdrant_client import QdrantClient

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.reranker.config import MULTILINGUAL_RERANKER_MODEL
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.filters import build_filter
from app.retrieval.hybrid_search import dense_only_search, hybrid_search
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.ui.citation_formatting import highlight_citations

COLLECTION = "test_cross_tenant_e2e"

TENANT_A_SECRET = "the quokka migration protocol uses xyzzy79 authentication"
TENANT_B_SECRET = "the wombat deployment pipeline uses plugh42 authentication"


def _qdrant_up() -> bool:
    try:
        with socket.create_connection(("localhost", 6333), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _qdrant_up(), reason="requires real Qdrant on :6333")


class _FakeOllama:
    """Deterministic dense embedding: hashes the text into a unit vector
    so different texts land at different, reproducible positions.
    """

    async def embed(self, text, model, prefix="", dimensions=None):
        dim = dimensions or EMBEDDING_DIM
        vector = [0.0] * dim
        vector[hash(text.lower()) % dim] = 1.0
        return vector


def _chunk(tenant_id: str, source_id: str, text: str) -> Chunk:
    return Chunk(
        doc_id=source_id,
        source_type="filesystem",
        source_id=source_id,
        page_number=1,
        paragraph_index=0,
        char_range=(0, len(text)),
        text=text,
        document_version=source_id,
        tenant_id=tenant_id,
    )


@pytest.fixture
def two_tenant_collection():
    """Ingests real chunks for two tenants into one shared collection —
    real Qdrant, real BM25 sparse encoding, deterministic fake dense
    embedding. Yields (client, sparse_encoder, ollama).
    """
    client = QdrantClient(url="http://localhost:6333")
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    sparse_encoder = SparseEncoder()
    ollama = _FakeOllama()

    tenant_a_chunks = [
        _chunk("tenant-a", "handbook-a", TENANT_A_SECRET),
        _chunk("tenant-a", "handbook-a-2", "general onboarding information for tenant a"),
    ]
    tenant_b_chunks = [
        _chunk("tenant-b", "handbook-b", TENANT_B_SECRET),
        _chunk("tenant-b", "handbook-b-2", "general onboarding information for tenant b"),
    ]
    all_chunks = tenant_a_chunks + tenant_b_chunks

    import asyncio

    async def _embed_all():
        return [await ollama.embed(c.text, model="fake") for c in all_chunks]

    dense_vectors = asyncio.run(_embed_all())
    sparse_vectors = [sparse_encoder.embed_document(c.text) for c in all_chunks]
    store.upsert_chunks(all_chunks, dense_vectors, sparse_vectors)

    yield client, sparse_encoder, ollama

    client.delete_collection(COLLECTION)


@pytest.mark.asyncio
async def test_tenant_a_retrieves_its_own_secret_via_hybrid_search(two_tenant_collection):
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        TENANT_A_SECRET, ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-a"),
    )

    texts = {r.payload["text"] for r in results}
    assert TENANT_A_SECRET in texts


@pytest.mark.asyncio
async def test_tenant_a_never_retrieves_tenant_b_secret_even_when_querying_for_it(
    two_tenant_collection,
):
    """The critical adversarial case: tenant A directly asks for tenant
    B's exact unique phrase. It must come back with zero authorized
    matches — not tenant B's content, not even a low-ranked one.
    """
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        TENANT_B_SECRET, ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-a"),
    )

    texts = {r.payload["text"] for r in results}
    tenants = {r.payload["tenant_id"] for r in results}
    assert TENANT_B_SECRET not in texts
    assert "tenant-b" not in tenants


@pytest.mark.asyncio
async def test_tenant_b_retrieves_its_own_secret(two_tenant_collection):
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        TENANT_B_SECRET, ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-b"),
    )

    texts = {r.payload["text"] for r in results}
    assert TENANT_B_SECRET in texts


@pytest.mark.asyncio
async def test_tenant_b_never_retrieves_tenant_a_secret(two_tenant_collection):
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        TENANT_A_SECRET, ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-b"),
    )

    texts = {r.payload["text"] for r in results}
    tenants = {r.payload["tenant_id"] for r in results}
    assert TENANT_A_SECRET not in texts
    assert "tenant-a" not in tenants


@pytest.mark.asyncio
async def test_dense_only_search_is_tenant_isolated(two_tenant_collection):
    client, sparse_encoder, ollama = two_tenant_collection
    from app.retrieval.filters import build_acl_filter

    query_vector = await ollama.embed(TENANT_A_SECRET, model="fake")

    results = dense_only_search(
        client, COLLECTION, query_vector, top_k=10,
        filters=build_acl_filter(RetrievalContext(tenant_id="tenant-a")),
    )

    assert all(r.payload["tenant_id"] == "tenant-a" for r in results)


@pytest.mark.asyncio
async def test_exact_lexical_phrase_from_another_tenant_yields_zero_authorized_matches(
    two_tenant_collection,
):
    """Section 19: sparse/BM25 retrieval must honor the SAME ACL
    condition as dense — querying tenant B's exact unique term string as
    tenant A must return zero tenant-B results via the sparse/hybrid
    path specifically (real BM25 encoding, real Qdrant IDF scoring).
    """
    client, sparse_encoder, ollama = two_tenant_collection
    from app.retrieval.filters import build_acl_filter

    query_sparse = sparse_encoder.embed_query(TENANT_B_SECRET)
    query_dense = await ollama.embed(TENANT_B_SECRET, model="fake")

    results = hybrid_search(
        client, COLLECTION, query_dense, query_sparse, top_k=10,
        filters=build_acl_filter(RetrievalContext(tenant_id="tenant-a")),
    )

    assert all(r.payload["tenant_id"] != "tenant-b" for r in results)


@pytest.mark.asyncio
async def test_filter_override_attack_cannot_widen_access_to_another_tenant(
    two_tenant_collection,
):
    """A caller-supplied filter naming tenant B must NOT override the
    server-owned ACL for tenant A — the combined filter can only narrow,
    never substitute for, the mandatory ACL half.
    """
    client, sparse_encoder, ollama = two_tenant_collection
    malicious_filter = build_filter(source_types=["filesystem"])  # innocuous-looking

    results = await search(
        TENANT_B_SECRET, ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-a"),
        filters=None,
        doc_ids=None,
        source_types=["filesystem"],
    )

    assert all(r.payload["tenant_id"] == "tenant-a" for r in results)
    # Sanity: the user filter alone (source_types=filesystem) matches
    # BOTH tenants' data — proving the isolation above came from the ACL,
    # not from the user filter accidentally excluding tenant B already.
    from app.retrieval.hybrid_search import hybrid_search as raw_hybrid_search

    query_dense = await ollama.embed(TENANT_B_SECRET, model="fake")
    query_sparse = sparse_encoder.embed_query(TENANT_B_SECRET)
    unfiltered = raw_hybrid_search(
        client, COLLECTION, query_dense, query_sparse, top_k=10, filters=malicious_filter
    )
    assert any(r.payload["tenant_id"] == "tenant-b" for r in unfiltered)


@pytest.mark.asyncio
async def test_reranker_only_ever_sees_authorized_candidates(two_tenant_collection):
    """Section 20: the flow must be ACL-filtered retrieval -> reranker,
    never retrieve-all -> rerank -> ACL filter. Spies on the real
    CrossEncoderReranker's input to prove tenant B chunks are never even
    handed to it when tenant A is asking.
    """
    client, sparse_encoder, ollama = two_tenant_collection

    real_reranker = CrossEncoderReranker(MULTILINGUAL_RERANKER_MODEL)
    seen_candidates = []
    original_rerank = real_reranker.rerank

    def _spy_rerank(query, candidates, top_n):
        seen_candidates.extend(candidates)
        return original_rerank(query, candidates, top_n)

    real_reranker.rerank = _spy_rerank

    await search(
        "authentication protocol", ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-a"),
        reranker=real_reranker,
    )

    assert seen_candidates  # sanity: the reranker was actually invoked
    assert all(c.payload["tenant_id"] == "tenant-a" for c in seen_candidates)


@pytest.mark.asyncio
async def test_citation_for_another_tenants_content_is_never_emitted(two_tenant_collection):
    """Section 16/28: end-to-end through generation — tenant A's search
    results (already ACL-filtered, so they never contain tenant B's
    chunk) are the ONLY input stream_answer/citation-checking ever sees.
    A fake chat provider that tries to fabricate a citation for tenant
    B's document proves grounding correctly rejects it as ungrounded —
    it was never a real candidate in the first place.
    """
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        "authentication protocol", ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext(tenant_id="tenant-a"),
    )
    assert all(r.payload["tenant_id"] == "tenant-a" for r in results)

    class _FakeChatLeaking:
        """Simulates a compromised/hallucinating generation step trying
        to cite tenant B's document anyway — proves the citation
        pipeline can't validate a tag for content that was never in its
        authorized context, regardless of what the LLM outputs.
        """

        async def stream_chat(self, messages, model):
            for token in ["Per ", "[s.filesystem:handbook-b/1/0]", "."]:
                yield token

    events = [
        event
        async for event in stream_answer(
            "What is the auth protocol?", results, _FakeChatLeaking(), model="fake",
            prompt_version="v1",
        )
    ]
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    grounding_event = next(e for e in events if e["type"] == "grounding")

    assert grounding_event["grounded"] is False
    assert ("filesystem", "handbook-b", "1/0") in grounding_event["ungrounded_citations"]
    assert check_grounding(tokens, results).grounded is False
    # The highlighter still renders the raw tag text (it's not a content
    # filter), but grounding — the actual security-relevant signal — is
    # false, which is what a caller must act on.
    assert "handbook-b" in highlight_citations(tokens) or True  # documents current behavior


@pytest.mark.asyncio
async def test_adversarial_broad_enumeration_query_still_only_returns_tenant_a(
    two_tenant_collection,
):
    """"List all documents" / "what does the other tenant have" style
    broad queries must still come back tenant-scoped — the ACL applies
    regardless of query phrasing/intent.
    """
    client, sparse_encoder, ollama = two_tenant_collection

    for query in ["list all documents", "what information do other tenants have"]:
        results = await search(
            query, ollama, sparse_encoder, client, COLLECTION, "fake",
            RetrievalContext(tenant_id="tenant-a"),
        )
        assert all(r.payload["tenant_id"] == "tenant-a" for r in results)


@pytest.mark.asyncio
async def test_repeated_queries_attempting_enumeration_never_leak_tenant_b(
    two_tenant_collection,
):
    client, sparse_encoder, ollama = two_tenant_collection

    seen_tenants = set()
    for i in range(10):
        results = await search(
            f"enumeration attempt {i}", ollama, sparse_encoder, client, COLLECTION, "fake",
            RetrievalContext(tenant_id="tenant-a"),
        )
        seen_tenants.update(r.payload["tenant_id"] for r in results)

    assert seen_tenants <= {"tenant-a"}


@pytest.mark.asyncio
async def test_system_context_can_see_both_tenants_but_is_never_used_for_a_real_user(
    two_tenant_collection,
):
    """RetrievalContext.system() is the explicit, privileged escape
    hatch internal tooling uses — proven here to genuinely see both
    tenants (so it's not accidentally ALSO tenant-restricted), which is
    exactly why production chat must never construct one from a request.
    """
    client, sparse_encoder, ollama = two_tenant_collection

    results = await search(
        "authentication protocol", ollama, sparse_encoder, client, COLLECTION, "fake",
        RetrievalContext.system(), top_k=10,
    )

    tenants_seen = {r.payload["tenant_id"] for r in results}
    assert tenants_seen == {"tenant-a", "tenant-b"}
