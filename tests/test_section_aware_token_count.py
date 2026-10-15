"""The evidence budget is counted with a real tokenizer when one is given.
A word count undercounts Turkish by about 2.5-3x, so a "1200-token" budget
selected 3000+ tokens and the answer prompt overflowed the context window."""

import pytest

from app.evidence.section_aware import SectionAwareEvidenceBuilder
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext


def chunk(chunk_id: str, text: str, heading: str = "Policy", paragraph: int = 0) -> SearchResult:
    return SearchResult(
        score=1.0,
        id=chunk_id,
        payload={
            "source_type": "filesystem",
            "source_id": "source-a",
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "heading_path": [heading],
            "heading_occurrence": 0,
            "page_number": 1,
            "paragraph_index": paragraph,
            "text": text,
        },
    )


def three_per_word(text: str) -> int:
    """Stand-in tokenizer: every word is three tokens (Turkish-like)."""
    return 3 * len(text.split())


def builder(budget: int, count_tokens=None, source: list[SearchResult] | None = None):
    instance = SectionAwareEvidenceBuilder(
        client=None, collection_name="test", token_budget=budget, count_tokens=count_tokens
    )
    instance._scroll_source = lambda anchor, context: source or [anchor]
    return instance


@pytest.mark.asyncio
async def test_budget_is_counted_with_the_given_tokenizer():
    anchor = chunk("a", "kelime " * 500)

    result = await builder(1200, three_per_word).build([anchor], RetrievalContext("tenant-a"))

    [block] = result.blocks
    assert block.payload["truncated"] is True
    assert result.context_tokens <= 1200
    assert result.context_tokens == three_per_word(block.payload["text"])
    assert block.payload["visible_token_count"] == three_per_word(block.payload["text"])
    assert block.payload["original_token_count"] == 1500


@pytest.mark.asyncio
async def test_without_a_tokenizer_the_budget_is_a_word_count():
    anchor = chunk("a", "kelime " * 500)

    result = await builder(1200).build([anchor], RetrievalContext("tenant-a"))

    assert result.blocks[0].payload.get("truncated") is not True
    assert result.context_tokens == 500


def test_truncation_keeps_whole_words_within_the_token_limit():
    block = SectionAwareEvidenceBuilder._block(chunk("a", "bir iki üç dört beş"), [chunk("a", "x")])
    block.payload["text"] = "bir iki üç dört beş"

    SectionAwareEvidenceBuilder._truncate_block(block, 10, three_per_word)

    assert block.payload["text"] == "bir iki üç"
    assert block.payload["visible_token_count"] == 9


@pytest.mark.asyncio
async def test_small_source_merge_is_decided_in_real_tokens():
    """Two 300-word sections: 600 words fit a 1200 budget, 1800 tokens do not,
    so with the tokenizer only the anchor's own section is used."""
    anchor = chunk("a", "a " * 300, heading="Anchor", paragraph=1)
    other = chunk("b", "b " * 300, heading="Other", paragraph=0)

    by_words = await builder(1200, source=[anchor, other]).build(
        [anchor], RetrievalContext("tenant-a")
    )
    by_tokens = await builder(1200, three_per_word, source=[anchor, other]).build(
        [anchor], RetrievalContext("tenant-a")
    )

    assert by_words.blocks[0].payload["contributing_chunk_ids"] == ["b", "a"]
    assert by_tokens.blocks[0].payload["contributing_chunk_ids"] == ["a"]


@pytest.mark.asyncio
async def test_each_distinct_text_is_tokenized_once():
    calls: list[str] = []

    def counting(text: str) -> int:
        calls.append(text)
        return three_per_word(text)

    source = [chunk(str(i), f"parça {i} " * 20, heading=f"H{i}", paragraph=i) for i in range(8)]

    await builder(4000, counting, source=source).build(source[:2], RetrievalContext("tenant-a"))

    assert len(calls) == len(set(calls))
