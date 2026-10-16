from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Paragraph:
    page_number: int
    paragraph_index: int
    text: str


@dataclass(frozen=True)
class DocumentElement:
    """One structural element of a parsed document, in reading order.

    ``kind`` is "heading", "paragraph", "table" or "furniture" (running
    headers, footers and page numbers). ``index`` is the element's position
    among its page's content elements (the paragraph index citations use);
    furniture has index -1.
    ``heading_path`` is the stack of headings the element sits under; a
    heading's own path ends with itself. ``table_rows`` holds a table's
    cleaned cells, row by row. ``flags`` records how the text was obtained
    when it was not the plain text layer, e.g. "ocr:garbled_text".
    """

    kind: str
    page_number: int
    index: int
    text: str
    bbox: tuple[float, float, float, float]
    heading_level: int | None = None
    heading_path: tuple[str, ...] = ()
    table_rows: tuple[tuple[str, ...], ...] = ()
    flags: tuple[str, ...] = ()


@dataclass
class ParseReport:
    """Quality signals from one document parse, filled in by the parser.

    ``needs_review`` flags a document whose text was partly lost: pages
    skipped (a scan without OCR, or OCR failed), garbled blocks dropped, or
    pages that produced no content at all.
    """

    pages: int = 0
    ocr_pages: dict[str, int] = field(default_factory=dict)
    skipped_pages: int = 0
    garbled_blocks_dropped: int = 0
    empty_pages: int = 0
    headings: int = 0
    tables: int = 0
    furniture: int = 0
    heading_source: str = "none"

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "ocr_pages": dict(self.ocr_pages),
            "skipped_pages": self.skipped_pages,
            "garbled_blocks_dropped": self.garbled_blocks_dropped,
            "empty_pages": self.empty_pages,
            "headings": self.headings,
            "tables": self.tables,
            "furniture": self.furniture,
            "heading_source": self.heading_source,
            "needs_review": bool(
                self.skipped_pages or self.garbled_blocks_dropped or self.empty_pages
            ),
        }
