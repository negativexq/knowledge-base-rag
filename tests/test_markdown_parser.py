from app.parsing.markdown_parser import extract_blocks


def test_content_before_any_heading_has_empty_heading_path():
    blocks = extract_blocks("Intro paragraph before any heading.")

    assert len(blocks) == 1
    assert blocks[0].heading_path == ()
    assert blocks[0].block_index == 0


def test_paragraph_under_a_single_h1_heading():
    text = "# Kurulum\n\nBu bir kurulum paragrafıdır."

    blocks = extract_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].heading_path == ("Kurulum",)
    assert blocks[0].text == "Bu bir kurulum paragrafıdır."


def test_multiple_paragraphs_under_the_same_heading_get_sequential_block_index():
    text = "# Kurulum\n\nFirst paragraph.\n\nSecond paragraph."

    blocks = extract_blocks(text)

    assert [b.block_index for b in blocks] == [0, 1]
    assert all(b.heading_path == ("Kurulum",) for b in blocks)


def test_nested_headings_build_a_heading_path_stack():
    text = "# Kurulum\n\n## Adım 1\n\nDo this first."

    blocks = extract_blocks(text)

    assert len(blocks) == 1
    assert blocks[0].heading_path == ("Kurulum", "Adım 1")


def test_a_second_h1_section_resets_the_heading_stack():
    text = "# A\n\nFirst.\n\n# B\n\nSecond."

    blocks = extract_blocks(text)

    assert [b.heading_path for b in blocks] == [("A",), ("B",)]


def test_returning_to_a_shallower_heading_drops_deeper_siblings():
    text = "# A\n\n## Sub\n\nDeep text.\n\n# B\n\nBack to top level."

    blocks = extract_blocks(text)

    assert [b.heading_path for b in blocks] == [("A", "Sub"), ("B",)]


def test_block_index_restarts_at_zero_for_each_new_heading_path():
    text = "# A\n\nA1.\n\nA2.\n\n## Sub\n\nSub1."

    blocks = extract_blocks(text)

    assert [(b.heading_path, b.block_index) for b in blocks] == [
        (("A",), 0),
        (("A",), 1),
        (("A", "Sub"), 0),
    ]


def test_heading_level_skip_is_treated_as_a_child_of_the_nearest_shallower_heading():
    text = "# A\n\n### Deep\n\nText under a level-skipped heading."

    blocks = extract_blocks(text)

    assert blocks[0].heading_path == ("A", "Deep")


def test_fenced_code_block_is_kept_as_a_single_block_not_split_on_blank_lines():
    text = "# A\n\n```\nline one\n\nline two\n```"

    blocks = extract_blocks(text)

    assert len(blocks) == 1
    assert "line one" in blocks[0].text
    assert "line two" in blocks[0].text


def test_empty_document_produces_no_blocks():
    assert extract_blocks("") == []


def test_blank_only_document_produces_no_blocks():
    assert extract_blocks("\n\n   \n\n") == []


def test_repeated_heading_path_gets_distinct_occurrence_numbers():
    """Sprint 17.5: the same heading_path (here "Overview", reached via
    two separate, non-adjacent H1 sections) used to be indistinguishable
    — block_index restarted at 0 for the second occurrence just like the
    first, with nothing marking them as different sections.
    """
    text = (
        "# Overview\n\nFirst overview text.\n\n"
        "# Other\n\nUnrelated.\n\n"
        "# Overview\n\nSecond overview text."
    )

    blocks = extract_blocks(text)

    assert [(b.heading_path, b.heading_occurrence, b.text) for b in blocks] == [
        (("Overview",), 0, "First overview text."),
        (("Other",), 0, "Unrelated."),
        (("Overview",), 1, "Second overview text."),
    ]


def test_non_repeated_headings_keep_occurrence_zero():
    text = "# A\n\nFirst.\n\n# B\n\nSecond."

    blocks = extract_blocks(text)

    assert all(b.heading_occurrence == 0 for b in blocks)
