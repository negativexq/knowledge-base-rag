import hashlib
import re
from dataclasses import dataclass

from app.ingestion.models import Chunk
from app.parsing.models import Paragraph
from app.parsing.pdf_parser import extract_paragraphs

# Provisional defaults — a whitespace-split word count is used as a stand-in
# for real LLM tokens. Not a final decision: revisit once evaluation
# (Sprint 9) gives real signal on what chunk size/overlap works.
DEFAULT_CHUNK_SIZE_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50  # 10% of DEFAULT_CHUNK_SIZE_TOKENS

_SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]?(?=\s|$)')
_SENTENCE_BOUNDARY_LOOKAHEAD = 300


def compute_doc_id(pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _build_page_text(paragraphs: list[Paragraph]) -> tuple[str, list[tuple[int, int, int]]]:
    """Join a page's paragraphs into one string, tracking each paragraph's char span."""
    parts: list[str] = []
    offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for paragraph in paragraphs:
        start = cursor
        parts.append(paragraph.text)
        cursor += len(paragraph.text)
        offsets.append((paragraph.paragraph_index, start, cursor))
        parts.append("\n\n")
        cursor += 2
    return "".join(parts), offsets


def _paragraph_index_for_char(offsets: list[tuple[int, int, int]], char_pos: int) -> int:
    for paragraph_index, start, end in offsets:
        if start <= char_pos < end:
            return paragraph_index
    preceding = [idx for idx, start, _ in offsets if start <= char_pos]
    return preceding[-1] if preceding else offsets[0][0]


def _extend_to_sentence_end(text: str, pos: int) -> int:
    """Push a chunk boundary forward to the next sentence end, so a sentence
    is never split across two chunks. Falls back to the word boundary if no
    sentence end appears within a reasonable lookahead.
    """
    window_end = min(len(text), pos + _SENTENCE_BOUNDARY_LOOKAHEAD)
    match = _SENTENCE_END_RE.search(text, pos, window_end)
    if match:
        return match.end()
    return pos


@dataclass(frozen=True)
class ChunkSpan:
    """A chunk's position/text within one "unit" of a document (a PDF page,
    or — reused by app/ingestion/markdown_chunker.py — a markdown heading
    section), before doc_id/source_type/source_id/heading_path are stamped
    onto it. Kept separate from Chunk so this module's word/sentence-
    boundary splitting logic (_build_page_text, _chunk_page_text,
    _extend_to_sentence_end) can be reused for markdown without markdown
    sections pretending to be PDF pages at the Chunk level.
    """

    page_number: int
    paragraph_index: int
    char_range: tuple[int, int]
    text: str


def _chunk_page_text(
    page_text: str,
    offsets: list[tuple[int, int, int]],
    page_number: int,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[ChunkSpan]:
    words = list(re.finditer(r"\S+", page_text))
    if not words:
        return []

    step = max(chunk_size_tokens - overlap_tokens, 1)
    spans: list[ChunkSpan] = []
    i = 0
    while i < len(words):
        j = min(i + chunk_size_tokens, len(words))
        start_char = words[i].start()
        end_char = words[j - 1].end()
        if j < len(words):
            end_char = _extend_to_sentence_end(page_text, end_char)

        text = page_text[start_char:end_char].strip()
        if text:
            paragraph_index = _paragraph_index_for_char(offsets, start_char)
            spans.append(
                ChunkSpan(
                    page_number=page_number,
                    paragraph_index=paragraph_index,
                    char_range=(start_char, end_char),
                    text=text,
                )
            )

        if j >= len(words):
            break
        i += step

    return spans


def chunk_document(
    pdf_path: str,
    source_id: str,
    source_type: str = "pdf",
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    doc_id: str | None = None,
) -> list[Chunk]:
    doc_id = doc_id or compute_doc_id(pdf_path)
    paragraphs = extract_paragraphs(pdf_path)

    paragraphs_by_page: dict[int, list[Paragraph]] = {}
    for paragraph in paragraphs:
        paragraphs_by_page.setdefault(paragraph.page_number, []).append(paragraph)

    spans: list[ChunkSpan] = []
    for page_number, page_paragraphs in paragraphs_by_page.items():
        page_text, offsets = _build_page_text(page_paragraphs)
        spans.extend(
            _chunk_page_text(page_text, offsets, page_number, chunk_size_tokens, overlap_tokens)
        )

    return [
        Chunk(
            doc_id=doc_id,
            source_type=source_type,
            source_id=source_id,
            page_number=span.page_number,
            paragraph_index=span.paragraph_index,
            char_range=span.char_range,
            text=span.text,
        )
        for span in spans
    ]
