"""Bounded structural inspection of an immutable, version-checked PDF snapshot.

Detected images are image regions, not an asserted inventory of semantic figures.
Every region ID is reconstructed by the server; no file paths or arbitrary crops
are accepted from the model.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import fitz

from app.llm.visual_answer import MAX_SNAPSHOT_RENDER_PIXELS, RENDER_DPI, PdfSnapshot
from app.parsing.pdf_lock import serialized_pdf
from app.parsing.pdf_parser import _clean_rows, _table_text, _with_external_header

MAX_ITEMS = 50
MAX_TABLE_CELLS = 20000
MAX_PAGE_AREA = 12_000_000


def numbered_labels(text: str) -> list[str]:
    """Literal numbered labels are location aids, never an inventory total."""
    return list(dict.fromkeys(re.findall(r"\b[A-Za-z][A-Za-z-]{1,30}\s*#\s*\d+", text)))[:40]


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

    @serialized_pdf
    def inventory_overview(self) -> dict[str, Any] | None:
        """Bounded full-page contact sheets, not an asserted semantic inventory."""
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            if not 1 <= doc.page_count <= 36:
                return None
            images = []
            for start in range(0, doc.page_count, 12):
                with fitz.open() as sheet:
                    page = sheet.new_page(width=900, height=1680)
                    for i, number in enumerate(range(start, min(start + 12, doc.page_count))):
                        left, top = (i % 3) * 300, (i // 3) * 420
                        page.insert_text(
                            (left + 8, top + 13), f"Physical page {number+1}", fontsize=10
                        )
                        if doc[number].get_contents():
                            page.show_pdf_page(
                                fitz.Rect(left + 3, top + 20, left + 297, top + 417), doc, number
                            )
                    images.append(page.get_pixmap().tobytes("png"))
            return {"page_count": doc.page_count, "images": images}

    @serialized_pdf
    def inventory_context(self, pages: list[int]) -> dict[str, Any]:
        """Literal native lines and typography, never a semantic inventory assertion."""
        if not pages or len(pages) > 3 or len(set(pages)) != len(pages):
            raise ValueError("PDF_INVENTORY_PAGE_LIMIT")
        result = []
        remaining = 24000
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            for number in pages:
                if not 1 <= number <= min(doc.page_count, 2000):
                    raise ValueError("PDF_PAGE_OUT_OF_RANGE")
                page = doc[number - 1]
                lines: list[dict[str, Any]] = []
                limited = False
                for block in page.get_text("dict")["blocks"]:
                    if block["type"] != 0:
                        continue
                    for line in block["lines"]:
                        text = "".join(s["text"] for s in line["spans"]).strip()
                        if not text:
                            continue
                        if len(text) > remaining or len(lines) >= 500:
                            limited = True
                            continue
                        remaining -= len(text)
                        size = max(s["size"] for s in line["spans"])
                        bold = all(s["flags"] & 16 for s in line["spans"] if s["text"].strip())
                        caption = bool(re.match(r"^(?:fig(?:ure)?\.?|table)\s*\d", text, re.I))
                        lines.append(
                            dict(
                                id=f"P{number}.L{len(lines)+1}",
                                text=text,
                                bbox=[
                                    round(
                                        v / (page.rect.width if i % 2 == 0 else page.rect.height), 4
                                    )
                                    for i, v in enumerate(line["bbox"])
                                ],
                                size=round(size, 2),
                                heading=bool(bold or (text.isupper() and len(text) > 3)),
                                caption=caption,
                            )
                        )
                result.append(dict(page=number, lines=lines, limited=limited))
            return dict(
                page_count=doc.page_count,
                pages=result,
                authority="native PDF text/typography; reading order can be ambiguous",
            )

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
    def page_catalog(self, pages: list[int], query: str = "") -> list[dict[str, Any]]:
        """Exact native location hints, not summaries or answer evidence."""
        if not pages or len(pages) > 36 or len(set(pages)) != len(pages):
            raise ValueError("PDF_CATALOG_PAGE_LIMIT")
        budget = min(600, 12000 // len(pages))
        result = []
        with fitz.open(stream=self.snapshot.content, filetype="pdf") as doc:
            page_lines = {}
            for number in pages:
                if not 1 <= number <= min(doc.page_count, 2000):
                    raise ValueError("PDF_PAGE_OUT_OF_RANGE")
                page = doc[number - 1]
                if page.rect.width * page.rect.height > MAX_PAGE_AREA:
                    raise ValueError("PDF_PAGE_TOO_LARGE")
                lines = [line.strip() for line in page.get_text(sort=True).splitlines()]
                lines = [line for line in lines if line]
                page_lines[number] = lines
            terms = {w[:4] for w in re.findall(r"[a-z]{3,}", query.casefold())}
            matches = {
                number: [
                    {term for term in terms if re.search(r"\b" + re.escape(term), line, re.I)}
                    for line in lines
                ] for number, lines in page_lines.items()
            }
            frequency = Counter(
                term for groups in matches.values() for term in set().union(*groups)
            )
            for number, lines in page_lines.items():
                scores = [
                    sum(
                        math.log((1 + len(pages)) / (1 + frequency[t]))
                        if len(pages) > 1 else 1 for t in group
                    )
                    for group in matches[number]
                ]
                # Repeated report names and survey footers must not hide the
                # page's actual question-specific labels in the same small budget.
                relevant = sorted(
                    (i for i, score in enumerate(scores) if score > 0),
                    key=lambda i: -scores[i],
                )[:2]
                indexes = list(
                    dict.fromkeys(
                        relevant
                        + [
                            i
                            for pair in zip(
                                range(min(3, len(lines))),
                                range(len(lines) - 1, max(-1, len(lines) - 4), -1),
                            )
                            for i in pair
                        ]
                    )
                )
                chosen: list[int] = []
                size = 0
                for i in indexes:
                    if len(chosen) < 6 and len(lines[i]) <= 160 and size + len(lines[i]) <= budget:
                        chosen.append(i)
                        size += len(lines[i])
                labels = []
                for label in numbered_labels("\n".join(lines)):
                    if size + len(label) <= budget:
                        labels.append(label)
                        size += len(label)
                result.append(
                    dict(
                        physical_page=number,
                        pdf_page_label=page.get_label(),
                        native_lines=[lines[i] for i in sorted(chosen)],
                        numbered_items=labels,
                    )
                )
        return result

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
