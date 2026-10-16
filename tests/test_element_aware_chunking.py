"""Element-aware chunking packs whole parser elements (paragraphs, list
items, headings) into chunks sized for the reranker's 512-token window, and
splits a long table into row groups that each repeat the table's header
line. The baseline's 500-word windows cut through paragraphs and table rows
and overflow the window, so the cross-encoder truncated what it scored."""

import pytest

import app.ingestion.chunker as chunker
from app.ingestion.chunking_config import ChunkingConfig
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.tokenizer import token_count
from app.llm.embedding_models import qwen3_4b_config
from app.parsing.models import DocumentElement
from app.shared.config import Settings

CONFIG = ChunkingConfig.element_aware_candidate()


def _tokens(text: str) -> int:
    return token_count(text, CONFIG.tokenizer_model, CONFIG.tokenizer_revision)


def _element(kind, page, index, text, path=("Results",)):
    return DocumentElement(
        kind=kind, page_number=page, index=index, text=text, bbox=(0, 0, 1, 1), heading_path=path
    )


def _paragraph(page, index, n_sentences=12):
    body = " ".join(
        f"Item {page}.{index}-{i} reports revenue of {i}.{index} million."
        for i in range(n_sentences)
    )
    return _element("paragraph", page, index, body)


def _chunk(monkeypatch, elements):
    monkeypatch.setattr(chunker, "extract_elements", lambda path, report=None: elements)
    return chunker.chunk_document(
        "unused.pdf", source_id="doc", doc_id="hash", chunking_config=CONFIG
    )


def test_the_config_fits_the_reranker_window_and_is_fingerprinted():
    assert CONFIG.mode == "element_aware"
    assert CONFIG.overlap_tokens == 0
    assert CONFIG.hard_max_tokens <= 448  # leaves room for the query in 512
    assert Settings(_env_file=None, chunking_mode="element_aware").chunking_config() == CONFIG

    embed = qwen3_4b_config(Settings(_env_file=None))
    assert (
        build_pipeline_fingerprint(embed, CONFIG).digest()
        != build_pipeline_fingerprint(embed, ChunkingConfig.current_baseline()).digest()
    )


def test_paragraphs_are_packed_whole_and_never_split_or_repeated(monkeypatch):
    elements = [_paragraph(1, i) for i in range(8)]

    chunks = _chunk(monkeypatch, elements)

    assert len(chunks) > 1
    for element in elements:
        holding = [c for c in chunks if element.text in c.text]
        assert len(holding) == 1, "each paragraph sits whole in exactly one chunk"
    for chunk in chunks:
        assert chunk.token_count == _tokens(chunk.text) <= CONFIG.hard_max_tokens
        assert chunk.chunking_mode == "element_aware"


def test_a_chunk_cites_the_element_it_starts_with(monkeypatch):
    elements = [_paragraph(1, i) for i in range(4)] + [_paragraph(2, i) for i in range(4)]

    chunks = _chunk(monkeypatch, elements)

    for chunk in chunks:
        first = next(e for e in elements if chunk.text.startswith(e.text))
        assert (chunk.page_number, chunk.paragraph_index) == (first.page_number, first.index)


def test_a_heading_stays_with_the_content_under_it(monkeypatch):
    heading = _element("heading", 1, 0, "Results", path=("Results",))
    elements = [heading] + [_paragraph(1, i) for i in range(1, 4)]

    chunks = _chunk(monkeypatch, elements)

    assert chunks[0].text.startswith("Results\n\n" + elements[1].text)


def test_a_paragraph_longer_than_the_window_is_split_at_sentences(monkeypatch):
    long = _paragraph(1, 0, n_sentences=80)

    chunks = _chunk(monkeypatch, [long])

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= CONFIG.hard_max_tokens
        assert chunk.text.endswith(".")


def test_a_long_table_is_split_into_row_groups_that_repeat_its_header(monkeypatch):
    header = "Table: Year | Revenue | Stores"
    rows = [f"Year: {2000 + i} | Revenue: {i * 37} | Stores: {i * 3}" for i in range(120)]
    table = _element("table", 3, 0, "\n".join([header, *rows]))

    chunks = _chunk(monkeypatch, [table])

    assert len(chunks) > 1
    seen = []
    for chunk in chunks:
        lines = chunk.text.split("\n")
        assert lines[0] == header
        assert chunk.token_count <= CONFIG.hard_max_tokens
        seen += lines[1:]
    assert seen == rows, "every row appears once, in order"
    assert len({c.char_range for c in chunks}) == len(chunks), "point ids stay distinct"


def test_a_short_table_stays_one_chunk_apart_from_prose(monkeypatch):
    table = _element("table", 1, 1, "Table: A | B\nA: 1 | B: 2")
    # The paragraph before is prose, too long to be taken as a caption.
    elements = [_paragraph(1, 0, n_sentences=8), table, _paragraph(1, 2, n_sentences=2)]

    chunks = _chunk(monkeypatch, elements)

    assert [c.text for c in chunks if "Table:" in c.text] == [table.text]


@pytest.mark.parametrize("max_length", [None, 512])
def test_the_reranker_max_length_is_configurable(monkeypatch, max_length):
    import app.reranker.cross_encoder as cross_encoder
    import app.wiring as wiring

    captured = {}
    monkeypatch.setattr(
        cross_encoder, "CrossEncoder", lambda *args, **kwargs: captured.update(kwargs)
    )

    wiring.build_reranker(Settings(_env_file=None, reranker_max_length=max_length))

    assert captured.get("max_length") == max_length


def test_a_long_table_without_row_lines_is_split_not_dropped(monkeypatch):
    # v2 run: OCR tables came back as one line; the row grouper found no rows
    # after the header and emitted nothing, so pages 15-16 of a PDF lost all
    # their table text (rows 381 and 831 had no chunk on their evidence page).
    cells = " | ".join(f"Standard RL.{i}: cite textual evidence {i}." for i in range(150))
    table = _element("table", 15, 5, "Table: " + cells)

    chunks = _chunk(monkeypatch, [table])

    assert len(chunks) > 1
    assert all(c.token_count <= CONFIG.hard_max_tokens for c in chunks)
    joined = " ".join(c.text for c in chunks)
    assert all(f"RL.{i}:" in joined for i in range(150))


def test_a_table_keeps_the_caption_line_just_before_it(monkeypatch):
    # v2 run, Best Buy 10-K p.40: "Consolidated Statements of Earnings $ in
    # millions" is a paragraph before the table; packed with the prose above
    # it, the table chunk named no statement and retrieval missed it.
    caption = _element("paragraph", 40, 1, "Consolidated Statements of Earnings $ in millions")
    table = _element("table", 40, 2, "Table: Item | 2023\nItem: Revenue | 2023: 46,298")
    elements = [_paragraph(40, 0, n_sentences=4), caption, table]

    chunks = _chunk(monkeypatch, elements)

    holding = [c for c in chunks if table.text in c.text]
    assert [c.text for c in holding] == [caption.text + "\n\n" + table.text]
    assert all(caption.text not in c.text for c in chunks if c not in holding)


def test_every_row_group_of_a_split_table_repeats_its_caption(monkeypatch):
    caption = _element("paragraph", 3, 0, "Store counts by year")
    header = "Table: Year | Revenue | Stores"
    rows = [f"Year: {2000 + i} | Revenue: {i * 37} | Stores: {i * 3}" for i in range(120)]
    table = _element("table", 3, 1, "\n".join([header, *rows]))

    chunks = _chunk(monkeypatch, [caption, table])

    assert len(chunks) > 1
    assert all(c.text.startswith(caption.text + "\n\n" + header + "\n") for c in chunks)
    assert all(c.token_count <= CONFIG.hard_max_tokens for c in chunks)
