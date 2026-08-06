import fitz
import pytest


def _sentence(marker: str, sentence_index: int, word_count: int) -> str:
    words = [f"{marker}-s{sentence_index}w{i}" for i in range(word_count)]
    return " ".join(words) + "."


def _paragraph_text(marker: str, sentence_count: int, words_per_sentence: int) -> str:
    return " ".join(
        _sentence(marker, s, words_per_sentence) for s in range(sentence_count)
    )


@pytest.fixture
def sample_pdf(tmp_path) -> str:
    """A small multi-page PDF used to exercise parsing and chunking.

    - Page 1: two short paragraphs (PAGE1-PARA0, PAGE1-PARA1)
    - Page 2: one long paragraph (PAGE2-PARA0), long enough to span multiple
      chunks when a small chunk size is used in tests
    - Page 3: two short paragraphs (PAGE3-PARA0, PAGE3-PARA1)
    - Page 4: no text layer at all (simulates a scanned/image-only page,
      which is out of scope and must be silently skipped)
    """
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_textbox(
        fitz.Rect(50, 50, 550, 150), _paragraph_text("PAGE1-PARA0", 2, 6), fontsize=11
    )
    page1.insert_textbox(
        fitz.Rect(50, 250, 550, 350), _paragraph_text("PAGE1-PARA1", 2, 6), fontsize=11
    )

    page2 = doc.new_page()
    page2.insert_textbox(
        fitz.Rect(50, 50, 550, 700), _paragraph_text("PAGE2-PARA0", 12, 8), fontsize=11
    )

    page3 = doc.new_page()
    page3.insert_textbox(
        fitz.Rect(50, 50, 550, 150), _paragraph_text("PAGE3-PARA0", 2, 6), fontsize=11
    )
    page3.insert_textbox(
        fitz.Rect(50, 250, 550, 350), _paragraph_text("PAGE3-PARA1", 2, 6), fontsize=11
    )

    page4 = doc.new_page()
    page4.draw_rect(fitz.Rect(50, 50, 200, 200), fill=(0, 0, 0))

    pdf_path = tmp_path / "sample.pdf"
    doc.save(pdf_path)
    doc.close()
    return str(pdf_path)
