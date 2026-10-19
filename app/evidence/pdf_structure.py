"""Bounded structural inspection of an immutable, version-checked PDF snapshot.

Detected images are image regions, not an asserted inventory of semantic figures.
Every region ID is reconstructed by the server; no file paths or arbitrary crops
are accepted from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import fitz

from app.llm.visual_answer import MAX_SNAPSHOT_RENDER_PIXELS, RENDER_DPI, PdfSnapshot
from app.parsing.pdf_lock import serialized_pdf
from app.parsing.pdf_parser import _clean_rows, _table_text, _with_external_header

MAX_ITEMS = 50
MAX_TABLE_CELLS = 20000
MAX_PAGE_AREA = 12_000_000


@dataclass(frozen=True)
class PdfElement:
    element_id: str
    kind: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str = ""
    rows: tuple[tuple[str, ...], ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "kind": self.kind,
            "page": self.page,
            "bbox": list(self.bbox),
            "label": self.text[:500],
        }


class PdfStructure:
    def __init__(self, snapshot: PdfSnapshot):
        self.snapshot = snapshot

    def _elements(self, doc: fitz.Document, page_number: int) -> list[PdfElement]:
        if not 1 <= page_number <= min(doc.page_count, 2000):
            raise ValueError("PDF_PAGE_OUT_OF_RANGE")
        page = doc[page_number - 1]
        if page.rect.width * page.rect.height > MAX_PAGE_AREA:
            raise ValueError("PDF_PAGE_TOO_LARGE")
        elements: list[PdfElement] = []
        for i, table in enumerate(page.find_tables().tables[:MAX_ITEMS], 1):
            # Bound cell materialization; oversized tables remain discoverable regions.
            rows: tuple[tuple[str, ...], ...] = ()
            if table.row_count * table.col_count <= MAX_TABLE_CELLS:
                rows = tuple(tuple(row) for row in _clean_rows(_with_external_header(table)))
            elements.append(
                PdfElement(
                    f"P{page_number}.T{i}",
                    "table",
                    page_number,
                    tuple(table.bbox),
                    rows[0][0] if rows and rows[0] else "",
                    rows,
                )
            )
        for i, image in enumerate(page.get_image_info()[:MAX_ITEMS], 1):
            elements.append(
                PdfElement(
                    f"P{page_number}.I{i}",
                    "image",
                    page_number,
                    tuple(image["bbox"]),
                )
            )
        for i, block in enumerate(page.get_text("blocks")[:2000], 1):
            if block[6] != 0:
                continue
            text = str(block[4]).strip()
            # These are caption candidates, never accepted as figure counts.
            if re.match(r"^(?:fig(?:ure)?\.?|table|şekil|tablo)\s*\d", text, re.I):
                elements.append(
                    PdfElement(
                        f"P{page_number}.C{i}",
                        "caption",
                        page_number,
                        tuple(block[:4]),
                        text,
                    )
                )
        for i, (_, title, page_ref) in enumerate(doc.get_toc()[:2000], 1):
            if page_ref == page_number:
                elements.append(
                    PdfElement(
                        f"P{page_number}.H{i}",
                        "heading",
                        page_number,
                        tuple(page.rect),
                        title,
                    )
                )
        return elements

    @serialized_pdf
    def page_quality(self, page_number: int) -> dict[str, Any]:
        """Cheap original-page provenance check, not an OCR accuracy guarantee."""
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            if not 1 <= page_number <= min(doc.page_count, 2000):
                raise ValueError("PDF_PAGE_OUT_OF_RANGE")
            page = doc[page_number - 1]
            area = page.rect.width * page.rect.height
            if area > MAX_PAGE_AREA:
                raise ValueError("PDF_PAGE_TOO_LARGE")
            native_chars = len(page.get_text().strip())
            image_area = sum(
                max(0, (fitz.Rect(info["bbox"]) & page.rect).get_area())
                for info in page.get_image_info()[:MAX_ITEMS]
            )
            coverage = min(1.0, image_area / max(1, area))
            return {
                "page": page_number,
                "native_text_chars": native_chars,
                "image_area_fraction": coverage,
                "requires_image": native_chars == 0 or (native_chars < 40 and coverage >= 0.5),
            }

    @serialized_pdf
    def list(self, page: int = 1, offset: int = 0) -> dict[str, Any]:
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            elements = self._elements(doc, page)
            selected = elements[offset : offset + MAX_ITEMS]
            more = len(elements) > offset + len(selected)
            next_page = page if more else page + 1
            has_more = more or page < min(doc.page_count, 2000)
            return {
                "elements": [e.summary() for e in selected],
                "page": page,
                "has_more": has_more,
                "next_page": next_page if has_more else None,
                "next_offset": offset + len(selected) if more else 0,
                "scan_limited": doc.page_count > 2000,
                "complete_figure_inventory": False,
                "limitations": "Detected ruled tables, embedded images, caption candidates and "
                "bookmarks only. Vector figures, unruled tables and semantic figure counts "
                "may be missing. Inspect page images before drawing conclusions.",
            }

    @serialized_pdf
    def element(self, element_id: str) -> PdfElement:
        match = re.fullmatch(r"P([1-9]\d{0,3})\.[TICH]([1-9]\d{0,3})", element_id)
        if not match:
            raise ValueError("UNKNOWN_ELEMENT_ID")
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            for element in self._elements(doc, int(match[1])):
                if element.element_id == element_id:
                    return element
        raise ValueError("UNKNOWN_ELEMENT_ID")

    @serialized_pdf
    def table(self, element_id: str, offset: int = 0) -> dict[str, Any]:
        element = self.element(element_id)
        if element.kind != "table" or not element.rows:
            raise ValueError("TABLE_STRUCTURE_UNAVAILABLE")
        header, *data = element.rows
        rows = data[offset : offset + MAX_ITEMS]
        # Do not serialize a huge cell or silently truncate away a qualifier.
        while rows and sum(len(cell) for row in [header, *rows] for cell in row) > 30000:
            rows.pop()
        if not rows and offset < len(data):
            raise ValueError("TABLE_ROW_TOO_LARGE")
        more = offset + len(rows) < len(data)
        context: list[str] = []
        context_limited = False
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            area = fitz.Rect(element.bbox)
            for block in doc[element.page - 1].get_text("blocks")[:2000]:
                if block[6] != 0 or fitz.Rect(block[:4]).intersects(area):
                    continue
                text = str(block[4]).strip()
                if sum(map(len, context)) + len(text) > 12000:
                    context_limited = True
                    continue
                if text:
                    context.append(text)
        return {
            **element.summary(),
            "header": list(header),
            "rows": [list(r) for r in rows],
            "row_offset": offset,
            "has_more": more,
            "next_offset": offset + len(rows) if more else None,
            "text": _table_text([list(header), *(list(r) for r in rows)]),
            "context_text": "\n\n".join(context),
            "context_limited": context_limited,
            "context_required": "Headers are extracted, not inferred. Units, periods, "
            "merged headers and footnotes must be checked against surrounding text/page images.",
        }

    @serialized_pdf
    def render(self, element_id: str) -> tuple[PdfElement, bytes]:
        element = self.element(element_id)
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            page = doc[element.page - 1]
            # Include nearby headings/notes around the detected region.
            clip = (fitz.Rect(element.bbox) + (-48, -72, 48, 72)) & page.rect
            if (
                clip.is_empty
                or clip.width * clip.height * (RENDER_DPI / 72) ** 2 > MAX_SNAPSHOT_RENDER_PIXELS
            ):
                raise ValueError("PDF_REGION_TOO_LARGE")
            return element, page.get_pixmap(dpi=RENDER_DPI, clip=clip).tobytes("png")
