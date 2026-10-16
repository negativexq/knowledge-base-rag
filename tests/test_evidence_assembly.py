"""Evidence assembly keeps what the reranker found most relevant. A pilot
audit (gpt-6-luna, MMLongBench) found the builder merged a document's anchors
in page order and cut the merged text from the end, so the top-ranked chunk
on a later page was dropped (the gold table on page 8 of row 639), and the
cut re-joined words with single spaces, so the whole block became one support
unit labelled with the anchor's page. Now anchors are kept in rank order, a
cut keeps chunk and paragraph boundaries, every unit carries its own page,
and the source scroll pages through large documents."""

import pytest
from qdrant_client.http import models as qmodels

from app.evidence.section_aware import SectionAwareEvidenceBuilder
from app.evidence.support_units import build_support_units
from app.llm.provider import default_evidence_tokens
from app.llm.structured_output import support_unit_citation_map
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext
from app.shared.config import Settings


def chunk(chunk_id: str, page: int, text: str) -> SearchResult:
    return SearchResult(
        score=1.0,
        id=chunk_id,
        payload={
            "source_type": "filesystem",
            "source_id": "paper_pdf",
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "section_path": ["4 Experiments"],
            "page_number": page,
            "paragraph_index": 0,
            "text": text,
        },
    )


def words(label: str, count: int) -> str:
    return " ".join(f"{label}{index}" for index in range(count))


def builder(budget: int) -> SectionAwareEvidenceBuilder:
    instance = SectionAwareEvidenceBuilder.__new__(SectionAwareEvidenceBuilder)
    instance._token_budget = budget
    instance._scroll_source = lambda anchor, context: []
    return instance


@pytest.mark.asyncio
async def test_the_top_ranked_anchor_survives_the_budget_even_on_a_later_page():
    # Rank order: the page 8 table first, then earlier pages.
    table = chunk("p8", 8, "Subtask 2% Semantic errors " + words("t", 296))
    anchors = [table, chunk("p5", 5, words("a", 300)), chunk("p6", 6, words("b", 300))]

    result = await builder(700).build(anchors, RetrievalContext("tenant-a"))

    text = "\n\n".join(block.payload["text"] for block in result.blocks)
    assert table.payload["text"] in text
    assert result.context_tokens <= 700


@pytest.mark.asyncio
async def test_a_cut_keeps_paragraphs_so_units_stay_small():
    first = chunk("p1", 1, words("x", 200) + "\n\n" + words("y", 200))
    second = chunk("p2", 2, words("z", 400))

    result = await builder(600).build([first, second], RetrievalContext("tenant-a"))
    units = build_support_units(result.blocks)

    assert result.truncated_block_count >= 1
    assert len(units) >= 3


@pytest.mark.asyncio
async def test_every_unit_carries_the_page_of_its_own_chunk():
    anchors = [chunk("p8", 8, "Table on page eight."), chunk("p5", 5, "Prose on page five.")]

    result = await builder(1000).build(anchors, RetrievalContext("tenant-a"))
    units = build_support_units(result.blocks)
    cited = support_unit_citation_map(units, result.blocks)

    assert {unit.text: unit.page_number for unit in units} == {
        "Prose on page five.": 5,
        "Table on page eight.": 8,
    }
    assert {entry["text"]: entry["page_number"] for entry in cited} == {
        "Prose on page five.": 5,
        "Table on page eight.": 8,
    }


def test_the_source_scroll_pages_through_a_large_document():
    pages = {
        None: ([qmodels.Record(id=1, payload={"tenant_id": "tenant-a"})], 2),
        2: ([qmodels.Record(id=2, payload={"tenant_id": "tenant-a"})], None),
    }

    class Client:
        def scroll(self, *, offset=None, **_):
            return pages[offset]

    instance = SectionAwareEvidenceBuilder(Client(), "kb", token_budget=100)

    points = instance._scroll_source(chunk("p1", 1, "x"), RetrievalContext("tenant-a"))

    assert [point.id for point in points] == ["1", "2"]


def test_the_evidence_budget_follows_the_generator():
    local = Settings(generation_provider="ollama", pipeline_v2_context_token_budget=1600)
    cloud = Settings(generation_provider="openai", cloud_evidence_token_budget=12000)

    assert default_evidence_tokens(local) == 1600
    assert default_evidence_tokens(cloud) == 12000
