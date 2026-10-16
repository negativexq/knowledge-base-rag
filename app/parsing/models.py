from dataclasses import dataclass


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
