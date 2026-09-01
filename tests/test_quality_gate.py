"""Sprint 22: hermetic tests for the migration quality/smoke gates —
a fake search() dependency chain (real Qdrant :memory:, fake embed) so
these run with no real Ollama, matching the golden-set benchmark
fixtures' own hermetic pattern from Sprint 18-21.
"""

import pytest
from qdrant_client import QdrantClient

from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import get_embedding_model_config
from app.migration.quality_gate import run_quality_gate, run_smoke
from app.retrieval.sparse import SparseVector
from app.shared.config import Settings

DIMENSION = 8
COLLECTION = "test_quality_gate"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[], values=[])

    def embed_query(self, text: str) -> SparseVector:
        return SparseVector(indices=[], values=[])


def _unit(index: int) -> list[float]:
    v = [0.0] * DIMENSION
    v[index] = 1.0
    return v


class _FakeOllama:
    """query text "match N" embeds to unit vector N — deterministic,
    controllable retrieval outcomes without a real model.
    """

    async def embed(self, text, model, prefix="", dimensions=None):
        if text.startswith("match"):
            index = int(text[len("match"):])
            return _unit(index)
        return _unit(7)


def _store_with_two_points() -> QdrantClient:
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION, dense_dimension=DIMENSION)
    store.ensure_collection()
    from app.ingestion.models import Chunk

    chunk_a = Chunk(
        doc_id="a", source_type="filesystem", source_id="a", page_number=1,
        paragraph_index=0, char_range=(0, 5), text="alpha", heading_path=("H",),
        heading_occurrence=0, document_version="v1",
    )
    chunk_b = Chunk(
        doc_id="b", source_type="filesystem", source_id="b", page_number=1,
        paragraph_index=0, char_range=(0, 5), text="beta", heading_path=("H",),
        heading_occurrence=0, document_version="v1",
    )
    store.upsert_chunks(
        [chunk_a, chunk_b], [_unit(0), _unit(1)],
        [SparseVector(indices=[], values=[]), SparseVector(indices=[], values=[])],
    )
    return client


def _config():
    return get_embedding_model_config("qwen3-4b", Settings(), output_dimension=DIMENSION)


@pytest.mark.asyncio
async def test_run_quality_gate_computes_recall_and_passes_without_a_baseline():
    client = _store_with_two_points()
    questions = [
        {
            "id": "q1", "query": "match0", "query_lang": "en", "content_lang": "en",
            "expected_locations": [["filesystem", "a", "H"]],
        },
    ]

    result = await run_quality_gate(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
        baseline=None,
    )

    assert result.passed
    assert result.baseline_cross_recall_at_5 is None


@pytest.mark.asyncio
async def test_run_quality_gate_fails_when_below_baseline_minus_tolerance():
    client = _store_with_two_points()
    # A tr/en cross-lingual pair that will NOT retrieve the right chunk
    # (query embeds to unit(7), no point is at index 7).
    questions = [
        {
            "id": "q1", "query": "no match", "query_lang": "tr", "content_lang": "en",
            "expected_locations": [["filesystem", "a", "H"]],
        },
    ]
    baseline = {
        "cross_lingual": {"recall_at_5": 0.9, "mrr": 0.9}, "mono_lingual": {"recall_at_5": 0.9}
    }

    result = await run_quality_gate(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
        baseline=baseline, tolerance=0.03,
    )

    assert not result.passed
    assert result.failure_reasons


@pytest.mark.asyncio
async def test_run_quality_gate_passes_within_tolerance_of_baseline():
    client = _store_with_two_points()
    questions = [
        {
            "id": "q1", "query": "match0", "query_lang": "tr", "content_lang": "en",
            "expected_locations": [["filesystem", "a", "H"]],
        },
    ]
    baseline = {"cross_lingual": {"recall_at_5": 1.0, "mrr": 1.0}, "mono_lingual": {}}

    result = await run_quality_gate(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
        baseline=baseline, tolerance=0.05,
    )

    assert result.passed


@pytest.mark.asyncio
async def test_run_smoke_counts_hits_and_passes_above_min_hit_rate():
    client = _store_with_two_points()
    questions = [
        {"id": "q1", "query": "match0", "query_lang": "en", "content_lang": "en",
         "expected_locations": [["filesystem", "a", "H"]]},
        {"id": "q2", "query": "match1", "query_lang": "en", "content_lang": "en",
         "expected_locations": [["filesystem", "b", "H"]]},
    ]

    result = await run_smoke(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
        min_hit_rate=0.5,
    )

    assert result.passed
    assert result.hit_count == 2


@pytest.mark.asyncio
async def test_run_smoke_fails_below_min_hit_rate():
    client = _store_with_two_points()
    questions = [
        # "c" was never indexed — the only reliable way to force a genuine
        # miss with just two points in the store (both always come back
        # in a top-5 over a two-point collection regardless of score).
        {"id": "q1", "query": "no match", "query_lang": "en", "content_lang": "en",
         "expected_locations": [["filesystem", "c", "H"]]},
    ]

    result = await run_smoke(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
        min_hit_rate=0.5,
    )

    assert not result.passed


@pytest.mark.asyncio
async def test_run_smoke_not_found_question_is_a_miss_against_a_non_empty_collection():
    """A "hit" for a not-found question requires an EMPTY result set
    (matching the same convention scripts/benchmarks/benchmark_embeddings.py's
    golden-set eval already uses) — since Qdrant's hybrid search always
    returns its top-k ranked candidates from a non-empty collection
    regardless of how weak the match is, a real deployment's "I don't
    know" behavior comes from the LLM generation layer, not retrieval
    ever returning zero rows. This documents that honestly rather than
    asserting a hit that can't actually happen here.
    """
    client = _store_with_two_points()
    questions = [{"id": "nf1", "query": "nothing relevant here", "query_lang": "en",
                  "content_lang": None, "expect_not_found": True, "expected_locations": []}]

    result = await run_smoke(
        questions, _FakeOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
    )

    assert result.hit_count == 0


@pytest.mark.asyncio
async def test_run_smoke_records_errors_and_fails_on_exception():
    client = _store_with_two_points()

    class _BrokenOllama:
        async def embed(self, *a, **k):
            raise RuntimeError("boom")

    questions = [{"id": "q1", "query": "match0", "query_lang": "en", "content_lang": "en",
                  "expected_locations": [["filesystem", "a", "H"]]}]

    result = await run_smoke(
        questions, _BrokenOllama(), _FakeSparseEncoder(), client, COLLECTION, _config(),
    )

    assert not result.passed
    assert result.errors
