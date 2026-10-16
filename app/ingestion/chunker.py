import hashlib
import re
from dataclasses import dataclass, replace

from app.ingestion.chunking_config import ChunkingConfig
from app.ingestion.models import Chunk
from app.ingestion.tokenizer import token_offsets
from app.parsing.models import DocumentElement, Paragraph, ParseReport
from app.parsing.pdf_parser import extract_elements

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
    token_count: int | None = None
    overlap_token_count: int | None = None
    sentence_split: bool | None = None
    heading_preserved: bool | None = None
    page_crossing: bool | None = None


def _sentence_end_positions(text: str, start: int, end: int) -> list[int]:
    """Return sentence-ending character positions in a bounded window."""
    pattern = re.compile(r"[.!?。！？][\"'’”»\)\]]?(?=\s|$)")
    return [match.end() for match in pattern.finditer(text, start, end)]


def _token_aware_spans(
    page_text: str,
    offsets: list[tuple[int, int, int]],
    page_number: int,
    config: ChunkingConfig,
    heading_preserved: bool | None = None,
) -> list[ChunkSpan]:
    """Split one page/heading section using real tokenizer offsets.

    Character ranges are retained from the original text, rather than
    decoding token IDs back to text. This preserves citation locations and
    Unicode source text while keeping the token boundary deterministic.
    """
    tokenizer_offsets = token_offsets(page_text, config.tokenizer_model, config.tokenizer_revision)
    if not tokenizer_offsets:
        return []
    hard_max = config.hard_max_tokens or config.target_tokens
    token_ends = [end for _, end in tokenizer_offsets]
    spans: list[ChunkSpan] = []
    start_token = 0
    while start_token < len(tokenizer_offsets):
        target_token = min(start_token + config.target_tokens, len(tokenizer_offsets))
        hard_token = min(start_token + hard_max, len(tokenizer_offsets))
        end_token = target_token
        sentence_split = False
        if target_token < len(tokenizer_offsets) and target_token < hard_token:
            target_char = tokenizer_offsets[target_token - 1][1]
            hard_char = tokenizer_offsets[hard_token - 1][1]
            sentence_ends = _sentence_end_positions(page_text, target_char, hard_char)
            if sentence_ends:
                sentence_end = sentence_ends[0]
                while end_token < hard_token and token_ends[end_token - 1] < sentence_end:
                    end_token += 1
        end_token = min(end_token, hard_token)
        start_char = tokenizer_offsets[start_token][0]
        end_char = tokenizer_offsets[end_token - 1][1]
        text = page_text[start_char:end_char].strip()
        if text:
            # A true value means this non-final boundary had to cut through
            # a sentence because no sentence ending fit below hard_max.
            sentence_split = bool(
                end_token < len(tokenizer_offsets)
                and not re.search(r"[.!?。！？][\"\'’”»\)\]]?$", text)
            )
            paragraph_index = _paragraph_index_for_char(offsets, start_char)
            actual_count = end_token - start_token
            previous_end = spans[-1].char_range[1] if spans else None
            overlap_count = 0
            if previous_end is not None and start_char < previous_end:
                overlap_start = max(start_char, tokenizer_offsets[start_token][0])
                overlap_count = max(
                    0,
                    min(previous_end, end_char) - overlap_start,
                )
                # The char count above is only a defensive diagnostic. The
                # actual token overlap is known from the token window.
                overlap_count = min(config.overlap_tokens, actual_count)
            spans.append(
                ChunkSpan(
                    page_number=page_number,
                    paragraph_index=paragraph_index,
                    char_range=(start_char, end_char),
                    text=text,
                    token_count=actual_count,
                    overlap_token_count=overlap_count,
                    sentence_split=sentence_split,
                    heading_preserved=heading_preserved,
                    page_crossing=False,
                )
            )
        if end_token >= len(tokenizer_offsets):
            break
        next_start = max(start_token + 1, end_token - config.overlap_tokens)
        if next_start <= start_token:
            next_start = start_token + 1
        start_token = next_start
    return spans


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


def _document_sections(
    elements: list[DocumentElement],
) -> list[tuple[tuple[str, ...], list[DocumentElement]]]:
    """Split a document's content elements into sections, in order.

    A section is a run of elements under the same heading path; it may
    continue across a page break. A run made only of headings (a title with
    no body of its own before its first subsection) joins the next section,
    so headings stay with content. Elements under no heading are kept
    page-bound, since nothing says the text continues."""
    runs: list[tuple[tuple[str, ...], list[DocumentElement]]] = []
    for element in elements:
        previous = runs[-1] if runs else None
        continues = (
            previous is not None
            and previous[0] == element.heading_path
            and (element.heading_path or previous[1][-1].page_number == element.page_number)
        )
        if continues:
            previous[1].append(element)
        else:
            runs.append((element.heading_path, [element]))

    merged: list[tuple[tuple[str, ...], list[DocumentElement]]] = []
    pending: list[DocumentElement] = []
    for path, run in runs:
        if all(element.kind == "heading" for element in run):
            pending.extend(run)
            continue
        merged.append((path, pending + run))
        pending = []
    if pending:
        merged.append((pending[-1].heading_path, pending))
    return merged


def _page_offsets(elements: list[DocumentElement]) -> dict[tuple[int, int], int]:
    """Char offset of every content element in its page text (paragraphs
    joined by a blank line, as _build_page_text does)."""
    offsets: dict[tuple[int, int], int] = {}
    cursor: dict[int, int] = {}
    for element in elements:
        start = cursor.get(element.page_number, 0)
        offsets[(element.page_number, element.index)] = start
        cursor[element.page_number] = start + len(element.text) + 2
    return offsets


def chunk_document(
    pdf_path: str,
    source_id: str,
    source_type: str = "pdf",
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    doc_id: str | None = None,
    chunking_config: ChunkingConfig | None = None,
    report: ParseReport | None = None,
) -> list[Chunk]:
    """Chunk a PDF section by section: a chunk never mixes two sections, and
    a section that continues on the next page is chunked as one text, so a
    chunk may cross the page break (page_crossing, page_end).

    page_number, paragraph_index and char_range[0] name where a chunk starts
    in its first page's text: that is the citation anchor. char_range[1] is
    in the same page text for a chunk within one page; for a crossing chunk
    it is char_range[0] plus the chunk's length in the section text."""
    doc_id = doc_id or compute_doc_id(pdf_path)
    elements = [e for e in extract_elements(pdf_path, report=report) if e.kind != "furniture"]
    page_offsets = _page_offsets(elements)

    rows: list[tuple[ChunkSpan, tuple[str, ...], int]] = []
    for section_path, run in _document_sections(elements):
        # Split the section as one text; paragraph keys are run positions.
        keyed = [
            Paragraph(page_number=0, paragraph_index=i, text=e.text) for i, e in enumerate(run)
        ]
        section_text, offsets = _build_page_text(keyed)
        starts = {key: start for key, start, _ in offsets}
        first_page = run[0].page_number
        if chunking_config is not None and chunking_config.token_aware:
            section_spans = _token_aware_spans(section_text, offsets, first_page, chunking_config)
        else:
            section_spans = _chunk_page_text(
                section_text, offsets, first_page, chunk_size_tokens, overlap_tokens
            )
        for span in section_spans:
            start, end = span.char_range
            first = run[span.paragraph_index]
            last_key = _paragraph_index_for_char(offsets, max(start, end - 1))
            last = run[last_key]
            local_start = page_offsets[(first.page_number, first.index)] + (
                start - starts[span.paragraph_index]
            )
            crossing = last.page_number != first.page_number
            local_end = (
                local_start + (end - start)
                if crossing
                else page_offsets[(last.page_number, last.index)] + (end - starts[last_key])
            )
            rows.append(
                (
                    replace(
                        span,
                        page_number=first.page_number,
                        paragraph_index=first.index,
                        char_range=(local_start, local_end),
                        page_crossing=crossing,
                    ),
                    section_path,
                    last.page_number,
                )
            )
    rows.sort(key=lambda row: (row[0].page_number, row[0].char_range[0]))
    spans = [(span, section_path) for span, section_path, _ in rows]
    page_ends = [page_end for _, _, page_end in rows]

    return [
        Chunk(
            doc_id=doc_id,
            source_type=source_type,
            source_id=source_id,
            page_number=span.page_number,
            paragraph_index=span.paragraph_index,
            char_range=span.char_range,
            text=span.text,
            document_version=doc_id,
            token_count=span.token_count,
            overlap_token_count=span.overlap_token_count,
            chunking_mode=(chunking_config.mode if chunking_config else None),
            boundary_strategy=(chunking_config.boundary_strategy if chunking_config else None),
            sentence_split=span.sentence_split,
            heading_preserved=span.heading_preserved,
            page_crossing=span.page_crossing,
            section_path=section_path,
            page_end=page_end,
        )
        for (span, section_path), page_end in zip(spans, page_ends)
    ]
