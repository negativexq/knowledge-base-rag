from app.parsing.pdf_parser import extract_paragraphs


def test_extracts_paragraphs_with_correct_page_numbers(sample_pdf):
    paragraphs = extract_paragraphs(sample_pdf)

    page_numbers = {p.page_number for p in paragraphs}
    assert page_numbers == {1, 2, 3}  # page 4 has no text layer, so it's absent


def test_preserves_paragraph_boundaries_on_a_multi_paragraph_page(sample_pdf):
    paragraphs = extract_paragraphs(sample_pdf)

    page1_paragraphs = [p for p in paragraphs if p.page_number == 1]
    assert len(page1_paragraphs) == 2
    assert "PAGE1-PARA0" in page1_paragraphs[0].text
    assert "PAGE1-PARA1" in page1_paragraphs[1].text
    assert "PAGE1-PARA1" not in page1_paragraphs[0].text


def test_paragraph_index_is_sequential_per_page(sample_pdf):
    paragraphs = extract_paragraphs(sample_pdf)

    page3_paragraphs = [p for p in paragraphs if p.page_number == 3]
    assert [p.paragraph_index for p in page3_paragraphs] == [0, 1]


def test_page_with_no_text_layer_is_skipped(sample_pdf):
    paragraphs = extract_paragraphs(sample_pdf)

    assert all(p.page_number != 4 for p in paragraphs)
