import pytest

from app.llm.prompt import NOT_FOUND_PHRASE, build_context, build_messages, load_system_prompt
from app.retrieval.hybrid_search import SearchResult


def _result(
    page: int, paragraph: int, text: str, source_type: str = "pdf", source_id: str = "doc"
) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_type": source_type,
            "source_id": source_id,
        },
    )


def test_build_context_labels_each_chunk_with_page_and_paragraph():
    chunks = [
        _result(2, 0, "First chunk text."),
        _result(5, 1, "Second chunk text."),
    ]

    context = build_context(chunks)

    assert "Sayfa 2, Paragraf 0" in context
    assert "Sayfa 5, Paragraf 1" in context
    assert "First chunk text." in context
    assert "Second chunk text." in context


def test_build_context_includes_a_ready_made_citation_tag_per_chunk():
    """Regression guard: the model must not have to compose the citation
    tag itself (it was found to transcribe these incorrectly in real
    usage) — build_context hands it an exact, copy-paste-ready tag instead.
    """
    chunks = [_result(2, 0, "First chunk text.", source_type="pdf", source_id="handbook")]

    context = build_context(chunks)

    assert "[s.pdf:handbook/2/0]" in context


def test_build_context_empty_chunks_produces_empty_string():
    assert build_context([]) == ""


def test_build_messages_includes_system_and_user_roles():
    chunks = [_result(1, 0, "Some context.")]

    messages = build_messages("What is this about?", chunks, version="v1")

    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]
    assert "What is this about?" in messages[1]["content"]
    assert "Some context." in messages[1]["content"]


def test_build_messages_v1_system_prompt_mentions_citation_format_and_not_found_phrase():
    messages = build_messages("question", [_result(1, 0, "text")], version="v1")

    system_content = messages[0]["content"]
    assert "[s." in system_content
    assert NOT_FOUND_PHRASE in system_content


def test_load_system_prompt_v1_preserves_citation_rule_fixes():
    prompt = load_system_prompt("v1")

    assert "CITATION RULE" in prompt
    assert "citation tag" in prompt
    assert "copy" in prompt.lower()
    assert "Do not write" in prompt and "Kaynak" in prompt
    assert NOT_FOUND_PHRASE in prompt


def test_load_system_prompt_v1_warns_against_repeating_the_tag_per_word():
    prompt = load_system_prompt("v1")

    assert "once" in prompt.lower()
    assert "not after every word" in prompt.lower() or "not after each word" in prompt.lower()


def test_load_system_prompt_v2_is_a_genuinely_different_shorter_variant():
    v1 = load_system_prompt("v1")
    v2 = load_system_prompt("v2")

    assert v1 != v2
    assert len(v2) < len(v1)
    # v2 deliberately omits the explicit worked example from v1
    assert "Do not write" not in v2
    assert NOT_FOUND_PHRASE in v2


def test_load_system_prompt_unknown_version_raises():
    with pytest.raises(FileNotFoundError):
        load_system_prompt("v99")


def test_build_messages_uses_the_requested_version():
    chunks = [_result(1, 0, "text")]

    v1_messages = build_messages("question", chunks, version="v1")
    v2_messages = build_messages("question", chunks, version="v2")

    assert v1_messages[0]["content"] == load_system_prompt("v1")
    assert v2_messages[0]["content"] == load_system_prompt("v2")
    assert v1_messages[0]["content"] != v2_messages[0]["content"]


def test_build_context_uses_doc_fallback_when_source_fields_missing():
    chunk = SearchResult(
        score=0.9, payload={"page_number": 1, "paragraph_index": 0, "text": "text"}
    )

    context = build_context([chunk])

    assert "[s.doc:doc/1/0]" in context


def test_build_context_labels_a_markdown_chunk_with_its_heading_path():
    chunk = SearchResult(
        score=0.9,
        payload={
            "page_number": 0,
            "paragraph_index": 0,
            "heading_path": ["Kurulum", "Adım 1"],
            "text": "Do this first.",
            "source_type": "markdown",
            "source_id": "readme",
        },
    )

    context = build_context([chunk])

    assert "Bölüm: Kurulum > Adım 1" in context
    assert "[s.markdown:readme/Kurulum/Adım 1]" in context
    assert "Sayfa" not in context
