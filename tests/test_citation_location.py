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


def test_real_overview_hash_2_heading_does_not_collide_with_synthetic_suffix():
    """Sprint 17.6: the Sprint 17.5 scheme's real collision — a document
    can have a heading ACTUALLY named "Overview#2" (occurrence 0, no
    synthetic suffix applied) which used to produce the exact same string
    as the SECOND occurrence of a plain "Overview" heading (which gets
    the synthetic "#2" suffix). Escaping the real "#" inside the heading
    component keeps them distinct.
    """
    real_heading = location_for({"heading_path": ["Overview#2"], "heading_occurrence": 0})
    second_occurrence_of_overview = location_for(
        {"heading_path": ["Overview"], "heading_occurrence": 1}
    )

    assert real_heading == "Overview\\#2"
    assert second_occurrence_of_overview == "Overview#2"
    assert real_heading != second_occurrence_of_overview


def test_a_heading_component_containing_a_slash_does_not_collide_with_nested_headings():
    """Sprint 17.6: a single heading component containing "/" (e.g. a
    real "## A/B" Markdown heading, heading_path=("A/B",)) used to
    produce the identical joined location as two separate NESTED
    components heading_path=("A", "B") — both were "A/B". Escaping the
    real "/" inside a component keeps them distinct.
    """
    single_component_with_slash = location_for({"heading_path": ["A/B"]})
    nested_components = location_for({"heading_path": ["A", "B"]})

    assert single_component_with_slash == "A\\/B"
    assert nested_components == "A/B"
    assert single_component_with_slash != nested_components


def test_ordinary_headings_without_reserved_characters_are_unaffected_by_escaping():
    """Escaping is a no-op for the common case — a heading path with no
    "/", "#", or "\\" in any component round-trips to the exact string it
    always produced.
    """
    assert location_for({"heading_path": ["Kimlik Doğrulama", "Token Süresi"]}) == (
        "Kimlik Doğrulama/Token Süresi"
    )
