import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, replace
from functools import cache

import fitz

from app.parsing.models import DocumentElement, Paragraph, ParseReport

logger = logging.getLogger(__name__)

TEXT_BLOCK_TYPE = 0
# Recorded in the ingestion pipeline fingerprint (app/ingestion/fingerprint.py)
# through pdf_parser_version(); bump it whenever extraction output changes so
# existing PDFs are re-indexed.
PDF_PARSER_VERSION = "pymupdf_elements_v7"
# Tesseract languages for scanned pages (installed in the backend image as
# tesseract-ocr-tur / tesseract-ocr-eng) and the render resolution; 300 dpi
# is Tesseract's recommended input resolution.
OCR_LANGUAGES = "tur+eng"
OCR_DPI = 300
# A text block inside a table's area counts as held by the table when this
# share of its words appears in the table's cells.
TABLE_HELD_SHARE = 0.8
# Page quality gate. A text layer whose visible characters are mostly
# control characters comes from a font without a Unicode mapping; a page
# with almost no text but hundreds of vector paths usually has its text
# drawn as outlines. Both are read with OCR when it is available.
GARBLED_RATIO = 0.3
GARBLED_MIN_CHARS = 50
VECTOR_TEXT_MAX_CHARS = 200
VECTOR_TEXT_MIN_DRAWINGS = 300
# Heading detection: a block is a heading when its text is clearly larger
# than the document's body text, short, and not repeated on most pages.
HEADING_MIN_DELTA = 1.5
HEADING_MAX_WORDS = 15
HEADING_MIN_LETTER_RATIO = 0.6
# A whole-bold short block at body size is a heading too (papers and
# reports often set section titles in bold body text).
BOLD_FLAG = 16
# A standalone short block that starts with section numbering ("2.",
# "3.1", "IV.") is a heading even without any styling; its depth is the
# number of numbering parts.
SECTION_NUMBER = re.compile(r"^((?:\d+\.)*\d+\.?|[IVXLC]+\.)\s+[^\W\d_]")
NUMBERED_HEADING_MAX_WORDS = 10
# Cells of an unruled table row are separated by a visible gap.
ROW_CELL_MIN_GAP = 6.0
RUNNING_TEXT_MIN_PAGES = 3
# Running text only counts as page furniture inside the top or bottom
# margin band (this share of the page height).
MARGIN_BAND = 0.1
# A short "Label:" block is kept with the value printed directly under it.
LABEL_MAX_WORDS = 5
# OCR layout, in multiples of the page's median line height: bands are cut
# at vertical gaps of OCR_BAND_GAP, and columns at gutters of OCR_COLUMN_GAP
# (word groups on one line that far apart are kept as separate pieces).
OCR_BAND_GAP = 1.2
OCR_COLUMN_GAP = 2.0
# A table cell is short; a long line of prose beside a table is not a cell.
OCR_TABLE_CELL_MAX_WORDS = 8
# OCR boxes jitter by a few points; cells within this distance line up.
OCR_ALIGN_TOLERANCE = 4.0
# A cell holding only a number (amounts, percentages, "(61.71)", "--").
NUMBER = re.compile(r"^[~(+\-\u2013\u2014]*\s*[\d.,]*\d[\d.,]*\)?%?$|^[-\u2013\u2014]+$")

_Box = tuple[float, float, float, float]


@cache
def ocr_available() -> bool:
    """True when Tesseract and every OCR_LANGUAGES model are installed."""
    try:
        tessdata = fitz.get_tessdata()
    except RuntimeError:
        return False
    return all(
        os.path.exists(os.path.join(tessdata, f"{language}.traineddata"))
        for language in OCR_LANGUAGES.split("+")
    )


def pdf_parser_version() -> str:
    """The parser identity for the pipeline fingerprint. OCR availability is
    part of it: the same scanned PDF yields text with OCR and nothing
    without, so moving between the two must re-index."""
    if ocr_available():
        return f"{PDF_PARSER_VERSION}+ocr_tesseract_{OCR_LANGUAGES}"
    return PDF_PARSER_VERSION


def _ocr_lines(page: fitz.Page) -> list[tuple[_Box, str]]:
    """Tesseract's word groups with their boxes. MuPDF's OCR blocks are not
    used: they put everything on one visual line into one block, columns
    included, so the layout is rebuilt in _ocr_layout."""
    textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=OCR_DPI, full=True)
    lines = []
    for block in page.get_text("dict", textpage=textpage)["blocks"]:
        if block["type"] != TEXT_BLOCK_TYPE:
            continue
        for line in block["lines"]:
            if text := _line_text(line, word_spans=True):
                lines.append((tuple(line["bbox"]), text))
    return lines


def _union(entries: list[tuple[_Box, str]]) -> _Box:
    return (
        min(box[0] for box, _ in entries),
        min(box[1] for box, _ in entries),
        max(box[2] for box, _ in entries),
        max(box[3] for box, _ in entries),
    )


def _visual_lines(entries: list[tuple[_Box, str]]) -> list[list[tuple[_Box, str]]]:
    """Group boxes into visual lines (boxes whose middle falls in the first
    box's band), each sorted left to right."""
    rows: list[list[tuple[_Box, str]]] = []
    for entry in sorted(entries, key=lambda entry: (entry[0][1], entry[0][0])):
        box = entry[0]
        middle = (box[1] + box[3]) / 2
        if rows and rows[-1][0][0][1] <= middle <= rows[-1][0][0][3]:
            rows[-1].append(entry)
        else:
            rows.append([entry])
    return [sorted(row, key=lambda entry: entry[0][0]) for row in rows]


def _split_at_gaps(
    entries: list[tuple[_Box, str]], axis: int, gap: float
) -> list[list[tuple[_Box, str]]]:
    """Split boxes where nothing covers a stretch of at least `gap` along
    the axis (0: x, columns; 1: y, bands), in reading order."""
    groups: list[list[tuple[_Box, str]]] = []
    end = 0.0
    for entry in sorted(entries, key=lambda entry: entry[0][axis]):
        start, stop = entry[0][axis], entry[0][axis + 2]
        if groups and start - end < gap:
            groups[-1].append(entry)
            end = max(end, stop)
        else:
            groups.append([entry])
            end = stop
    return groups


def _ocr_table(entries: list[tuple[_Box, str]]) -> str | None:
    """Rows of three or more cells that line up, as on the text layer
    (_block_text), when they are at least half of the region's lines."""
    rows = _visual_lines(entries)
    cells = [
        [box for box, _ in row]
        for row in rows
        if len(row) >= 3 and all(len(text.split()) <= OCR_TABLE_CELL_MAX_WORDS for _, text in row)
    ]
    if len(cells) < 2 or 2 * len(cells) < len(rows):
        return None
    # Numbers are usually right-aligned, so a cell lines up with another
    # row's cell by its left or its right edge.
    aligned = total = 0
    for index, row in enumerate(cells):
        others = [box for other, boxes in enumerate(cells) if other != index for box in boxes]
        total += len(row)
        aligned += sum(
            1
            for box in row
            if any(
                abs(box[0] - other[0]) <= OCR_ALIGN_TOLERANCE
                or abs(box[2] - other[2]) <= OCR_ALIGN_TOLERANCE
                for other in others
            )
        )
    if aligned < 0.6 * total:
        return None
    return "\n".join(" | ".join(text for _, text in row) for row in rows)


def _splits(rows: list[list[tuple[_Box, str]]], gutter: float) -> bool:
    """True when lines spanning more than one line split into columns."""
    return len(rows) > 1 and len(_split_at_gaps([e for row in rows for e in row], 0, gutter)) > 1


def _ocr_regions(entries: list[tuple[_Box, str]], height: float) -> list[tuple[_Box, str]]:
    """Recursive XY-cut: split into bands at wide vertical gaps, keep aligned
    tables whole, then split into columns at gutters; what is left reads as
    one paragraph. Neighbouring columns that together form a table (a table
    printed beside prose) are joined back into that table."""
    bands = _split_at_gaps(entries, 1, OCR_BAND_GAP * height)
    if len(bands) > 1:
        return [region for band in bands for region in _ocr_regions(band, height)]
    if table := _ocr_table(entries):
        return [(_union(entries), table)]
    rows = _visual_lines(entries)
    if len(rows) == 1:
        return [(_union(entries), " ".join(text for _, text in rows[0]))]
    columns = []
    for column in _split_at_gaps(entries, 0, OCR_COLUMN_GAP * height):
        # A column of numbers is not text to read on its own: it belongs to
        # the labels on its left.
        if columns and 2 * sum(bool(NUMBER.match(text)) for _, text in column) > len(column):
            columns[-1] = columns[-1] + column
        else:
            columns.append(column)
    if len(columns) == 1:
        # Single-piece lines right above or below columns (prose running
        # across the gutter) block both cuts: cut them off where the rest
        # splits into columns.
        gutter = OCR_COLUMN_GAP * height
        cuts = [
            cut
            for cut in range(1, len(rows))
            if all(len(row) == 1 for row in rows[:cut]) and _splits(rows[cut:], gutter)
        ]
        cuts += [
            cut
            for cut in range(len(rows) - 1, 0, -1)
            if all(len(row) == 1 for row in rows[cut:]) and _splits(rows[:cut], gutter)
        ]
        if cuts:
            top, bottom = rows[: cuts[0]], rows[cuts[0] :]
            return [
                region
                for part in (top, bottom)
                for region in _ocr_regions([entry for row in part for entry in row], height)
            ]
        text = _join_lines([" ".join(text for _, text in row) for row in rows])
        return [(_union(entries), text)]
    regions: list[tuple[_Box, str]] = []
    start = 0
    while start < len(columns):
        for stop in range(len(columns), start + 1, -1):
            group = [entry for column in columns[start:stop] for entry in column]
            if table := _ocr_table(group):
                regions.append((_union(group), table))
                start = stop
                break
        else:
            regions.extend(_ocr_regions(columns[start], height))
            start += 1
    return regions


def _ocr_layout(lines: list[tuple[_Box, str]]) -> list[tuple[_Box, str]]:
    """Paragraphs of an OCR'd page in reading order. Word groups on one line
    are joined unless a wide gap separates them (a separate column)."""
    if not lines:
        return []
    heights = sorted(box[3] - box[1] for box, _ in lines)
    height = heights[len(heights) // 2]
    segments = []
    for row in _visual_lines(lines):
        current = [row[0]]
        for entry in row[1:]:
            if entry[0][0] - _union(current)[2] >= OCR_COLUMN_GAP * height:
                segments.append(current)
                current = [entry]
            else:
                current.append(entry)
        segments.append(current)
    joined = [(_union(segment), " ".join(text for _, text in segment)) for segment in segments]
    return _ocr_regions(joined, height)


def _visible(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def _is_garbled(text: str) -> bool:
    visible = _visible(text)
    if len(visible) < GARBLED_MIN_CHARS:
        return False
    control = sum(1 for ch in visible if ord(ch) < 32 or 0xE000 <= ord(ch) <= 0xF8FF)
    return control / len(visible) >= GARBLED_RATIO


def _ocr_reason(page: fitz.Page) -> str | None:
    """Why this page's text layer cannot be trusted, or None when it can."""
    text = page.get_text("text")
    if not text.strip():
        return "no_text_layer" if page.get_images() else None
    if _is_garbled(text):
        return "garbled_text"
    if (
        len(_visible(text)) < VECTOR_TEXT_MAX_CHARS
        and len(page.get_drawings()) >= VECTOR_TEXT_MIN_DRAWINGS
    ):
        return "vector_text"
    return None


@dataclass
class _Item:
    """A block on its way to becoming an element."""

    bbox: tuple[float, float, float, float]
    text: str
    kind: str = "paragraph"
    size: float | None = None
    bold: bool = False
    label: bool = False
    rows: tuple[tuple[str, ...], ...] = ()
    flags: tuple[str, ...] = ()


def _rows(lines: list[dict]) -> list[list[dict]]:
    """Group a block's lines into visual rows (lines that share a band)."""
    rows: list[list[dict]] = []
    for line in sorted(lines, key=lambda line: (line["bbox"][1], line["bbox"][0])):
        top, bottom = line["bbox"][1], line["bbox"][3]
        middle = (top + bottom) / 2
        if rows and rows[-1][0]["bbox"][1] <= middle <= rows[-1][0]["bbox"][3]:
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(row, key=lambda line: line["bbox"][0]) for row in rows]


# A word broken at a line end: a lowercase letter, a hyphen, then a line
# that starts with a lowercase letter ("pri-" / "marily").
_BROKEN_WORD_END = re.compile(r"(?<=[^\W\d_])-$")
_BROKEN_WORD_START = re.compile(r"^[^\W\d_]")


def _join_lines(lines: list[str]) -> str:
    """Lines of prose joined with spaces; a hyphen that breaks a word across
    two lines is removed and the halves joined. Only a lowercase continuation
    counts, so "Covid-" / "19" and "CAN-" / "Bus" keep their hyphen."""
    text = ""
    for line in lines:
        if not line:
            continue
        if (
            text
            and _BROKEN_WORD_END.search(text)
            and text[-2].islower()
            and _BROKEN_WORD_START.match(line)
            and line[0].islower()
        ):
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return text


def _line_text(line: dict, word_spans: bool = False) -> str:
    """A line's text with whitespace collapsed. On the text layer spans are
    joined as written, since a span boundary can fall inside a word (a drop
    cap, a kerning run). Tesseract sets a font size per word, so in OCR
    output a span boundary is always a word boundary, even where neither
    span carries the space ("of" + "Travancore")."""
    joiner = " " if word_spans else ""
    return " ".join(joiner.join(span["text"] for span in line["spans"]).split())


def _columns_align(cell_starts: list[list[float]]) -> bool:
    """True when at least two rows of cells share column positions: most
    cells start where a cell of another row starts. Justified prose split
    into pieces does not line up like this."""
    if len(cell_starts) < 2:
        return False
    aligned = total = 0
    for index, starts in enumerate(cell_starts):
        others = [x for other, row in enumerate(cell_starts) if other != index for x in row]
        total += len(starts)
        aligned += sum(1 for x in starts if any(abs(x - y) <= 3 for y in others))
    return aligned >= 0.6 * total


def _block_text(lines: list[dict]) -> str:
    """Prose is joined into one line; rows of three or more short cells
    (a table without rules) keep one row per line, cells joined by " | "."""
    rows = []
    cell_starts: list[list[float]] = []
    for row in _rows(lines):
        cells = [line for line in row if _line_text(line)]
        if not cells:
            continue
        gaps = [b["bbox"][0] - a["bbox"][2] for a, b in zip(cells, cells[1:])]
        if len(cells) >= 3 and min(gaps) >= ROW_CELL_MIN_GAP:
            cell_starts.append([line["bbox"][0] for line in cells])
        rows.append([_line_text(line) for line in cells])
    if _columns_align(cell_starts):
        return "\n".join(" | ".join(row) for row in rows)
    return _join_lines([_line_text(line) for line in lines])


def _dominant_size(lines: list[dict]) -> float | None:
    sizes: Counter[float] = Counter()
    for line in lines:
        for span in line["spans"]:
            sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else None


def _is_bold(lines: list[dict]) -> bool:
    chars = [
        (len(span["text"].strip()), bool(span["flags"] & BOLD_FLAG))
        for line in lines
        for span in line["spans"]
    ]
    total = sum(count for count, _ in chars)
    return total > 0 and sum(count for count, bold in chars if bold) >= 0.8 * total


def _text_layer_items(
    page: fitz.Page, drop_garbled: bool = False, report: ParseReport | None = None
) -> list[_Item]:
    items = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != TEXT_BLOCK_TYPE:
            continue
        text = _block_text(block["lines"])
        if not text:
            continue
        if drop_garbled and _is_garbled(text):
            if report is not None:
                report.garbled_blocks_dropped += 1
            continue
        items.append(
            _Item(
                tuple(block["bbox"]),
                text,
                size=_dominant_size(block["lines"]),
                bold=_is_bold(block["lines"]),
            )
        )
    return items


def _ocr_items(page: fitz.Page, reason: str) -> list[_Item]:
    return [
        _Item(box, text, flags=(f"ocr:{reason}",)) for box, text in _ocr_layout(_ocr_lines(page))
    ]


def _page_items(
    page: fitz.Page, pdf_path: str, page_number: int, report: ParseReport
) -> list[_Item]:
    reason = _ocr_reason(page)
    if reason is None:
        return _text_layer_items(page)
    name = os.path.basename(pdf_path)

    def skipped() -> list[_Item]:
        report.skipped_pages += 1
        return []

    fallback = {
        "no_text_layer": skipped,
        "garbled_text": lambda: _text_layer_items(page, drop_garbled=True, report=report),
        "vector_text": lambda: _text_layer_items(page),
    }[reason]
    if not ocr_available():
        if reason == "no_text_layer":
            logger.warning(
                "Skipping %s page %d: it has no text layer and OCR is not available",
                name,
                page_number,
            )
        elif reason == "garbled_text":
            logger.warning(
                "Dropping garbled text on %s page %d: OCR is not available", name, page_number
            )
        return fallback()
    try:
        items = _ocr_items(page, reason)
    except Exception:
        logger.warning("OCR failed on %s page %d (%s)", name, page_number, reason, exc_info=True)
        if reason == "no_text_layer":
            logger.warning("Skipping %s page %d: OCR failed", name, page_number)
        return fallback()
    report.ocr_pages[reason] = report.ocr_pages.get(reason, 0) + 1
    return items


def _is_label(item: _Item) -> bool:
    return (
        item.kind == "paragraph"
        and item.text.endswith(":")
        and "\n" not in item.text
        and len(item.text.split()) <= LABEL_MAX_WORDS
    )


def _merge_labels(items: list[_Item]) -> list[_Item]:
    """Keep a short "Label:" block with the value block directly under it,
    so the pair stays one unit for chunking and evidence."""
    merged: list[_Item] = []
    index = 0
    while index < len(items):
        item = items[index]
        following = items[index + 1] if index + 1 < len(items) else None
        if following is not None and _is_label(item) and following.kind == "paragraph":
            height = item.bbox[3] - item.bbox[1]
            gap = following.bbox[1] - item.bbox[3]
            aligned = abs(following.bbox[0] - item.bbox[0]) <= 50
            if 0 <= gap <= 2.5 * height and aligned:
                bbox = (
                    min(item.bbox[0], following.bbox[0]),
                    item.bbox[1],
                    max(item.bbox[2], following.bbox[2]),
                    following.bbox[3],
                )
                merged.append(
                    replace(following, bbox=bbox, text=f"{item.text} {following.text}", label=True)
                )
                index += 2
                continue
        merged.append(item)
        index += 1
    return merged


def _normalized(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


def _heading_levels(pages: list[list[_Item]]) -> dict[tuple[float, bool], int]:
    """Map heading styles (font size, bold) to levels, largest first, or {}
    when nothing stands out from the body text. A style is a heading style
    when it is clearly larger than the body, or bold at about body size."""
    sizes: Counter[float] = Counter()
    styles: set[tuple[float, bool]] = set()
    for items in pages:
        for item in items:
            if item.size is not None and item.kind == "paragraph":
                sizes[item.size] += len(item.text)
                if _is_heading_text(item.text):
                    styles.add((item.size, item.bold))
    if not sizes:
        return {}
    body = sizes.most_common(1)[0][0]
    heading_styles = sorted(
        (
            (size, bold)
            for size, bold in styles
            if size >= body + HEADING_MIN_DELTA or (bold and size >= body - 0.5)
        ),
        key=lambda style: (-style[0], not style[1]),
    )
    return {style: level for level, style in enumerate(heading_styles[:6], 1)}


def _numbering_depth(text: str) -> int | None:
    match = SECTION_NUMBER.match(text)
    if not match or len(text.split()) > NUMBERED_HEADING_MAX_WORDS:
        return None
    return len([part for part in match.group(1).split(".") if part])


def _toc_titles(doc: fitz.Document) -> dict[int, list[tuple[int, str]]]:
    """Bookmarks by page: {page_number: [(level, normalized title)]}."""
    titles: dict[int, list[tuple[int, str]]] = {}
    for level, title, page_number in doc.get_toc(simple=True):
        if title.strip() and page_number > 0:
            titles.setdefault(page_number, []).append((level, _normalized(title)))
    return titles


def _toc_level(text: str, entries: list[tuple[int, str]]) -> int | None:
    normalized = _normalized(text)
    for level, title in entries:
        if normalized == title or (
            len(normalized) >= 4 and (title.startswith(normalized) or normalized.startswith(title))
        ):
            return level
    return None


def _in_margin(item: _Item, page_height: float) -> bool:
    return item.bbox[3] <= page_height * MARGIN_BAND or item.bbox[1] >= page_height * (
        1 - MARGIN_BAND
    )


def _running_texts(pages: list[list[_Item]], heights: list[float]) -> set[str]:
    """Margin texts repeated on at least half the pages (running headers,
    footers, page numbers; digits are ignored when comparing)."""
    if len(pages) < RUNNING_TEXT_MIN_PAGES:
        return set()
    seen: Counter[str] = Counter()
    for items, height in zip(pages, heights):
        seen.update({_normalized(item.text) for item in items if _in_margin(item, height)})
    threshold = max(RUNNING_TEXT_MIN_PAGES, len(pages) / 2)
    return {text for text, count in seen.items() if count >= threshold}


def _is_heading_text(text: str) -> bool:
    visible = _visible(text)
    letters = sum(ch.isalpha() for ch in visible)
    return (
        "\n" not in text
        and len(text.split()) <= HEADING_MAX_WORDS
        and not text.endswith((".", ",", ";", ":"))
        and bool(visible)
        and letters / len(visible) >= HEADING_MIN_LETTER_RATIO
        and any(sum(ch.isalpha() for ch in word) >= 3 for word in text.split())
    )


def extract_elements(pdf_path: str, report: ParseReport | None = None) -> list[DocumentElement]:
    """Parse a PDF into typed elements in reading order.

    Ruled tables (PyMuPDF's line-based table finder) become one table
    element each; text blocks inside a table's area are dropped so cells are
    not emitted twice. Blocks laid out as rows of short cells keep their
    rows. A short "Label:" block is merged with the value under it.

    Every page passes a quality gate first: a page with no text layer (a
    scan), a garbled text layer (a font without a Unicode mapping) or text
    drawn as vector outlines is read with Tesseract OCR when it is
    installed. Without OCR, a scan is skipped with a warning, garbled blocks
    are dropped with a warning, and a vector page keeps what text it has.

    Headings come from the PDF's bookmarks when it has them (a block whose
    text matches a bookmark title on that page, at the bookmark's level).
    Otherwise a heading is a short block clearly larger than the body text,
    or entirely bold at about body size; distinct styles become levels. A
    short block starting with section numbering ("2.", "3.1") is a heading
    too, nested by its numbering depth below the styled levels.
    Text repeated on most pages inside the top or bottom margin (running
    headers, footers, page numbers) becomes a "furniture" element with
    index -1: never a heading, and left out of paragraphs and chunks. Every
    other element records the heading path it sits under.
    """
    report = report if report is not None else ParseReport()
    pages: list[list[_Item]] = []
    heights: list[float] = []
    with fitz.open(pdf_path) as doc:
        toc = _toc_titles(doc)
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            tables = [
                _Item(tuple(table.bbox), text, kind="table", rows=tuple(map(tuple, rows)))
                for table in page.find_tables().tables
                if (text := _table_text(rows := _clean_rows(table.extract())))
            ]
            items = tables + _outside_tables(
                _page_items(page, pdf_path, page_number, report), tables
            )
            items.sort(key=lambda item: (round(item.bbox[1], 1), item.bbox[0]))
            pages.append(_merge_labels(items))
            heights.append(page.rect.height)

    levels = {} if toc else _heading_levels(pages)
    report.pages = len(pages)
    running = _running_texts(pages, heights)
    elements: list[DocumentElement] = []
    stack: list[tuple[int, str]] = []
    for page_index, items in enumerate(pages):
        index = 0
        for item in items:
            if (
                item.kind == "paragraph"
                and _in_margin(item, heights[page_index])
                and _normalized(item.text) in running
            ):
                elements.append(
                    DocumentElement(
                        kind="furniture",
                        page_number=page_index + 1,
                        index=-1,
                        text=item.text,
                        bbox=item.bbox,
                        flags=item.flags,
                    )
                )
                continue
            if item.kind != "paragraph" or item.label:
                level = None
            elif toc:
                level = _toc_level(item.text, toc.get(page_index + 1, []))
            else:
                level = levels.get((item.size, item.bold)) if item.size is not None else None
                if level is None and (depth := _numbering_depth(item.text)) is not None:
                    level = len(levels) + depth
            is_heading = (
                level is not None
                and _is_heading_text(item.text)
                and _normalized(item.text) not in running
            )
            if is_heading:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, item.text))
            elements.append(
                DocumentElement(
                    kind="heading" if is_heading else item.kind,
                    page_number=page_index + 1,
                    index=index,
                    text=item.text,
                    bbox=item.bbox,
                    heading_level=level if is_heading else None,
                    heading_path=tuple(text for _, text in stack),
                    table_rows=item.rows,
                    flags=item.flags,
                )
            )
            index += 1
    content_pages = {e.page_number for e in elements if e.kind != "furniture"}
    report.empty_pages = report.pages - len(content_pages)
    report.headings = sum(e.kind == "heading" for e in elements)
    report.tables = sum(e.kind == "table" for e in elements)
    report.furniture = sum(e.kind == "furniture" for e in elements)
    if report.headings:
        report.heading_source = "bookmarks" if toc else "layout"
    return elements


def extract_paragraphs(pdf_path: str) -> list[Paragraph]:
    """The content element texts (page furniture left out) as paragraphs,
    per page and in reading order."""
    return [
        Paragraph(page_number=element.page_number, paragraph_index=element.index, text=element.text)
        for element in extract_elements(pdf_path)
        if element.kind != "furniture"
    ]


def _cell(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _clean_rows(rows: list[list[object]]) -> list[list[str]]:
    cleaned = [[_cell(value) for value in row] for row in rows]
    return [row for row in cleaned if any(row)]


def _table_text(rows: list[list[str]]) -> str:
    """One line naming the columns, then one line per data row that repeats
    each column header next to its value ("Plan: Free | Storage: 15GB"), so
    any single row still carries its meaning after chunking. The first row
    is taken as the header. A column with no header keeps its bare value
    rather than a made-up name; empty cells and empty columns are left out."""
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    used = [c for c in range(width) if any(row[c] for row in rows)]
    rows = [[row[c] for c in used] for row in rows]
    header = rows[0]
    lines = [re.sub(r"\|\s+(?=\|)", "| ", "Table: " + " | ".join(header)).rstrip()]
    for row in rows[1:]:
        cells = [f"{name}: {value}" if name else value for name, value in zip(header, row) if value]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _outside_tables(items: list[_Item], tables: list[_Item]) -> list[_Item]:
    """The text blocks a table does not already hold. A block inside a
    table's area is dropped only when its words are in that table's cells;
    otherwise the table missed it (a decorative page frame detected as a
    one-cell table holds only its title) and the block is kept."""
    kept = []
    for item in items:
        holders = [t for t in tables if _inside_any(item.bbox, [t])]
        words = _words(item.text)
        if holders and any(
            len(words & _words(t.text)) >= TABLE_HELD_SHARE * len(words) for t in holders
        ):
            continue
        kept.append(item)
    return kept


def _inside_any(bbox: tuple, tables: list[_Item]) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return any(
        t.bbox[0] <= center_x <= t.bbox[2] and t.bbox[1] <= center_y <= t.bbox[3] for t in tables
    )
