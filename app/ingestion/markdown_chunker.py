from pathlib import Path

from app.ingestion.chunker import (
    DEFAULT_CHUNK_SIZE_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    _build_page_text,
    _chunk_page_text,
    compute_doc_id,
)
from app.ingestion.chunking_config import ChunkingConfig
from app.ingestion.models import Chunk
from app.parsing.markdown_parser import extract_blocks
from app.parsing.models import Paragraph


def chunk_markdown_text(
    text: str,
    source_id: str,
    source_type: str,
    doc_id: str,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    chunking_config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """The text-in, chunks-out core — no file access. Reuses chunker.py's
    word/sentence-boundary splitting (_build_page_text/_chunk_page_text) by
    treating each unique heading_path as a surrogate "page": every markdown
    block is grouped under a stable integer id per heading_path (in
    first-seen order), fed through the exact same PDF chunking logic, then
    re-tagged with its real heading_path on the way out.

    doc_id is required here (unlike chunk_markdown_document) — with no file
    to hash, the caller must already know it (e.g. a connector's own
    content hash). Shared by app/ingestion/markdown_chunker.py's own
    file-reading wrapper below, app/ingestion/web_chunker.py (trafilatura's
    markdown output), and app/connectors/notion.py (Notion blocks rendered
    as markdown) — anywhere content arrives as text rather than a path.
    """
    blocks = extract_blocks(text)

    # Sprint 17.5: keyed by (heading_path, heading_occurrence), not
    # heading_path alone — two separate occurrences of the same
    # heading_path (e.g. two independent "# Overview" sections) must get
    # DIFFERENT surrogate "pages", or their blocks get merged into one
    # continuous section and their citation identity becomes
    # indistinguishable. See docs/sprint-17-5-plan.md.
    surrogate_by_heading: dict[tuple[tuple[str, ...], int], int] = {}
    heading_by_surrogate: dict[int, tuple[str, ...]] = {}
    occurrence_by_surrogate: dict[int, int] = {}
    paragraphs_by_surrogate: dict[int, list[Paragraph]] = {}

    for block in blocks:
        key = (block.heading_path, block.heading_occurrence)
        surrogate = surrogate_by_heading.setdefault(key, len(surrogate_by_heading))
        heading_by_surrogate[surrogate] = block.heading_path
        occurrence_by_surrogate[surrogate] = block.heading_occurrence
        paragraphs_by_surrogate.setdefault(surrogate, []).append(
            Paragraph(page_number=surrogate, paragraph_index=block.block_index, text=block.text)
        )

    chunks: list[Chunk] = []
    for surrogate, paragraphs in paragraphs_by_surrogate.items():
        section_text, offsets = _build_page_text(paragraphs)
        if chunking_config is not None and chunking_config.token_aware:
            from app.ingestion.chunker import _token_aware_spans

            spans = _token_aware_spans(
                section_text,
                offsets,
                surrogate,
                chunking_config,
                heading_preserved=True,
            )
        else:
            spans = _chunk_page_text(
                section_text, offsets, surrogate, chunk_size_tokens, overlap_tokens
            )
        heading_path = heading_by_surrogate[surrogate]
        heading_occurrence = occurrence_by_surrogate[surrogate]
        for span in spans:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    source_type=source_type,
                    source_id=source_id,
                    page_number=span.page_number,
                    paragraph_index=span.paragraph_index,
                    char_range=span.char_range,
                    text=span.text,
                    heading_path=heading_path,
                    heading_occurrence=heading_occurrence,
                    document_version=doc_id,
                    token_count=span.token_count,
                    overlap_token_count=span.overlap_token_count,
                    chunking_mode=(chunking_config.mode if chunking_config else None),
                    boundary_strategy=(
                        chunking_config.boundary_strategy if chunking_config else None
                    ),
                    sentence_split=span.sentence_split,
                    heading_preserved=span.heading_preserved,
                    page_crossing=span.page_crossing,
                )
            )

    return chunks


def chunk_markdown_document(
    md_path: str,
    source_id: str,
    source_type: str = "markdown",
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    doc_id: str | None = None,
    chunking_config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """File-reading wrapper around chunk_markdown_text. compute_doc_id is
    reused for the default hash — despite the name, it's just a generic
    sha256-of-file-bytes hash.
    """
    doc_id = doc_id or compute_doc_id(md_path)
    text = Path(md_path).read_text(encoding="utf-8")
    return chunk_markdown_text(
        text,
        source_id,
        source_type,
        doc_id,
        chunk_size_tokens,
        overlap_tokens,
        chunking_config,
    )
