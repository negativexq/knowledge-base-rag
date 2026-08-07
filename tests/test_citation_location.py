from app.llm.citation_location import location_for


def test_pdf_style_payload_falls_back_to_page_paragraph():
    payload = {"page_number": 3, "paragraph_index": 1, "heading_path": []}

    assert location_for(payload) == "3/1"


def test_markdown_heading_path_joins_with_slash():
    payload = {"heading_path": ["Kurulum", "Adım 1"], "heading_occurrence": 0}

    assert location_for(payload) == "Kurulum/Adım 1"


def test_first_occurrence_has_no_suffix_backward_compatible():
    """A heading that never repeats keeps the exact location string it
    always produced — no payload even needs a heading_occurrence key
    (older ingested points won't have one).
    """
    assert location_for({"heading_path": ["Overview"]}) == "Overview"
    assert location_for({"heading_path": ["Overview"], "heading_occurrence": 0}) == "Overview"


def test_repeated_heading_gets_a_distinguishing_suffix():
    """Sprint 17.5: two independent sections sharing the same heading_path
    used to produce the IDENTICAL location string
    (`[s.filesystem:doc/Overview]` for both), making their citations
    indistinguishable. heading_occurrence breaks the tie.
    """
    first = location_for({"heading_path": ["Overview"], "heading_occurrence": 0})
    second = location_for({"heading_path": ["Overview"], "heading_occurrence": 1})

    assert first == "Overview"
    assert second == "Overview#2"
    assert first != second
