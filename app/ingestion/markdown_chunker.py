from pathlib import Path

from app.ingestion.chunker import (
    DEFAULT_CHUNK_SIZE_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    ChunkSpan,
    _build_page_text,
    _chunk_page_text,
    compute_doc_id,
)
from app.ingestion.models import Chunk
from app.parsing.markdown_parser import extract_blocks
from app.parsing.models import Paragraph


def chunk_markdown_document(
    md_path: str,
    source_id: str,
    source_type: str = "markdown",
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    doc_id: str | None = None,
) -> list[Chunk]:
    """Reuses chunker.py's word/sentence-boundary splitting
    (_build_page_text/_chunk_page_text) by treating each unique
    heading_path as a surrogate "page": every markdown block is grouped
    under a stable integer id per heading_path (in first-seen order), fed
    through the exact same PDF chunking logic, then re-tagged with its real
    heading_path on the way out. compute_doc_id is reused too — despite the
    name, it's just a generic sha256-of-file-bytes hash.
    """
    doc_id = doc_id or compute_doc_id(md_path)
    text = Path(md_path).read_text(encoding="utf-8")
    blocks = extract_blocks(text)

    surrogate_by_heading: dict[tuple[str, ...], int] = {}
    heading_by_surrogate: dict[int, tuple[str, ...]] = {}
    paragraphs_by_surrogate: dict[int, list[Paragraph]] = {}

    for block in blocks:
        surrogate = surrogate_by_heading.setdefault(block.heading_path, len(surrogate_by_heading))
        heading_by_surrogate[surrogate] = block.heading_path
        paragraphs_by_surrogate.setdefault(surrogate, []).append(
            Paragraph(page_number=surrogate, paragraph_index=block.block_index, text=block.text)
        )

    chunks: list[Chunk] = []
    for surrogate, paragraphs in paragraphs_by_surrogate.items():
        section_text, offsets = _build_page_text(paragraphs)
        spans: list[ChunkSpan] = _chunk_page_text(
            section_text, offsets, surrogate, chunk_size_tokens, overlap_tokens
        )
        heading_path = heading_by_surrogate[surrogate]
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
                )
            )

    return chunks
