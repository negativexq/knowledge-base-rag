from app.ui.citation_formatting import highlight_citations


def test_highlights_a_single_citation():
    result = highlight_citations("Refunds take 30 days [s.pdf:doc/2/0].")

    assert result == "Refunds take 30 days **[s.pdf:doc/2/0]**."


def test_highlights_multiple_citations():
    result = highlight_citations("Point A [s.pdf:doc/1/0]. Point B [s.pdf:doc/5/1].")

    assert result == "Point A **[s.pdf:doc/1/0]**. Point B **[s.pdf:doc/5/1]**."


def test_leaves_text_without_citations_unchanged():
    text = "I could not find this in the document."

    assert highlight_citations(text) == text


def test_does_not_double_highlight_already_bold_text():
    # sanity: no interaction with other markdown in the text
    result = highlight_citations("**bold** and [s.pdf:doc/3/2]")

    assert result == "**bold** and **[s.pdf:doc/3/2]**"


def test_handles_multi_digit_page_and_paragraph_numbers():
    result = highlight_citations("See [s.pdf:doc/123/45].")

    assert result == "See **[s.pdf:doc/123/45]**."


def test_escapes_dollar_signs_so_they_are_not_read_as_latex():
    result = highlight_citations("Plus tier is $7.99/month [s.pdf:doc/2/0].")

    assert result == "Plus tier is \\$7.99/month **[s.pdf:doc/2/0]**."


def test_highlights_citation_with_source_document_name():
    result = highlight_citations("Knows Python [s.pdf:OmerFaruKOC__CV/1/0].")

    assert result == "Knows Python **[s.pdf:OmerFaruKOC__CV/1/0]**."


def test_highlights_citation_with_non_pdf_source_type():
    result = highlight_citations("See setup steps [s.markdown:readme/1/2].")

    assert result == "See setup steps **[s.markdown:readme/1/2]**."


def test_highlights_citation_with_a_markdown_heading_path_location():
    result = highlight_citations("See [s.markdown:readme/Kurulum/Adım 1].")

    assert result == "See **[s.markdown:readme/Kurulum/Adım 1]**."
