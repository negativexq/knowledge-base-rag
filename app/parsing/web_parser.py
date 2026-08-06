import trafilatura


def extract_main_content(html: str) -> str | None:
    """Strips nav/header/footer/ad/sidebar boilerplate and returns the
    page's main content as markdown text (headings as "#"/"##"/...) — so
    app/ingestion/markdown_chunker.py::chunk_markdown_text can chunk a web
    page exactly like a .md file, reusing Sprint 3's heading-path location
    scheme rather than inventing a new one for web pages.

    include_formatting=True is required for trafilatura to emit heading
    markers at all — verified empirically (its default markdown output is
    unmarked plain text). Returns None if trafilatura can't find enough
    real content to extract (e.g. an empty or non-article page).
    """
    return trafilatura.extract(
        html, output_format="markdown", include_formatting=True, favor_recall=True
    )
