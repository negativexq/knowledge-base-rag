"""A cited PDF page as an image, with the cited text highlighted when found.

The page comes from a version-pinned snapshot of the indexed file, so the
preview always shows the document version the answer was built from.
"""

from __future__ import annotations

import math

import fitz

PREVIEW_DPI = 110
MAX_PREVIEW_PIXELS = 12_000_000
MAX_HIGHLIGHT_LINES = 4


def _needles(highlight: str) -> list[str]:
    # Long cited passages rarely match verbatim; a few distinctive lines do.
    lines = [" ".join(line.split()) for line in highlight.splitlines()]
    lines = [line[:80] for line in lines if len(line) >= 8]
    return lines[:MAX_HIGHLIGHT_LINES]


def render_preview(
    content: bytes, page_number: int, highlight: str | None = None
) -> tuple[bytes, bool] | None:
    """PNG bytes and whether any highlight text was found, or None."""
    with fitz.open(stream=content, filetype="pdf") as doc:
        if not 1 <= page_number <= doc.page_count:
            return None
        page = doc[page_number - 1]
        width = math.ceil(page.rect.width * PREVIEW_DPI / 72)
        height = math.ceil(page.rect.height * PREVIEW_DPI / 72)
        if width * height > MAX_PREVIEW_PIXELS:
            return None
        found = False
        for needle in _needles(highlight or ""):
            for rect in page.search_for(needle)[:6]:
                page.add_highlight_annot(rect)
                found = True
        png: bytes = page.get_pixmap(dpi=PREVIEW_DPI, annots=True).tobytes("png")
        return png, found
