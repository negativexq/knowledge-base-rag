import fitz

from app.parsing.models import Paragraph

TEXT_BLOCK_TYPE = 0


def extract_paragraphs(pdf_path: str) -> list[Paragraph]:
    """Extract paragraphs per page, in reading order.

    Only PDFs with an extractable text layer are supported. A page with no
    text layer (e.g. a scanned image) yields no paragraphs and is silently
    skipped — OCR fallback is out of scope for this sprint.
    """
    paragraphs: list[Paragraph] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = [b for b in page.get_text("blocks") if b[6] == TEXT_BLOCK_TYPE]
            blocks.sort(key=lambda b: (round(b[1], 1), b[0]))

            paragraph_index = 0
            for block in blocks:
                text = " ".join(line.strip() for line in block[4].splitlines() if line.strip())
                if not text:
                    continue
                paragraphs.append(
                    Paragraph(page_number=page_number, paragraph_index=paragraph_index, text=text)
                )
                paragraph_index += 1

    return paragraphs
