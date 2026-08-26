# ruff: noqa: E501

"""Render committed PDF source Markdown into deterministic, selectable PDFs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
PDF_SOURCE_DIR = CORPUS_DIR / "pdf-sources"

PDF_SOURCES = {
    "enterprise-contract-guide": ("enterprise-contract-guide.md", "enterprise-contract-guide.pdf"),
    "product-guide-en": ("product-guide-en.md", "product-guide-en.pdf"),
    "regional-returns-eu": ("regional-returns-eu.md", "regional-returns-eu.pdf"),
    "regional-returns-tr": ("regional-returns-tr.md", "regional-returns-tr.pdf"),
    "returns-manual-tr": ("returns-manual-tr.md", "returns-manual-tr.pdf"),
}


def _sections(source: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in source.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            if heading:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = match.group(1), []
        elif not line.startswith("# "):
            body.append(line)
    if heading:
        sections.append((heading, "\n".join(body).strip()))
    if not sections:
        raise ValueError("PDF source must contain at least one level-two section")
    return sections


def _font_file() -> str | None:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    return next((candidate for candidate in candidates if Path(candidate).is_file()), None)


def render_pdf(source_path: Path, output_path: Path) -> None:
    source = source_path.read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in source.splitlines() if line.startswith("# ")), source_path.stem)
    document = fitz.open()
    font_file = _font_file()
    for page_number, (heading, body) in enumerate(_sections(source), start=1):
        page = document.new_page(width=595, height=842)
        text = f"{title}\n\n{page_number}. {heading}\n\n{body}"
        kwargs = {"fontsize": 9, "fontname": "negativex-font" if font_file else "helv"}
        if font_file:
            kwargs["fontfile"] = font_file
        result = page.insert_textbox(fitz.Rect(34, 30, 561, 812), text, **kwargs)
        if result < 0:
            document.close()
            raise ValueError(f"section does not fit on one page: {source_path.name} / {heading}")
    document.set_metadata(
        {"title": title, "author": "Negativex Documentation", "subject": "Operations reference"}
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    document.close()


def render_all(output_dir: Path = CORPUS_DIR) -> list[Path]:
    rendered: list[Path] = []
    for source_name, pdf_name in PDF_SOURCES.values():
        output_path = output_dir / pdf_name
        render_pdf(PDF_SOURCE_DIR / source_name, output_path)
        rendered.append(output_path)
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description="Render evaluation PDF source files")
    parser.add_argument("--output-dir", type=Path, default=CORPUS_DIR)
    args = parser.parse_args()
    paths = render_all(args.output_dir)
    print(f"Rendered {len(paths)} PDFs from committed Markdown sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
