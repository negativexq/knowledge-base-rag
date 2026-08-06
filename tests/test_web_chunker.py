from app.ingestion.web_chunker import chunk_web_page, compute_html_hash

_REALISTIC_PAGE = """<!DOCTYPE html>
<html><head><title>Kurulum Rehberi - Ornek Site</title></head><body>
<nav>Home | About | Contact | Blog | Support</nav>
<header>Site Header Ad Banner Here Buy Now</header>
<article>
<h1>Kurulum Rehberi</h1>
<p>Bu bir giris paragrafidir, kurulum hakkinda genel bilgi verir ve okuyucuya ne
yapacagini anlatir. Bu paragraf yeterince uzun olmali ki trafilatura bunu gercek
icerik olarak taniyip cikarsin.</p>
<h2>Adim 1: Bagimliliklari Kurun</h2>
<p>Once bagimliliklari yukleyin ve ortami hazirlayin. Bu adim onemlidir cunku
sonraki adimlarin calismasi buna baglidir. Detayli aciklama burada devam eder
ve okuyucuya rehberlik eder.</p>
</article>
<footer>Copyright 2024 - Privacy Policy - Terms of Service</footer>
</body></html>"""


def test_chunk_web_page_produces_heading_tagged_chunks():
    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="example_com_guide")

    heading_paths = {chunk.heading_path for chunk in chunks}
    assert ("Kurulum Rehberi",) in heading_paths
    assert ("Kurulum Rehberi", "Adim 1: Bagimliliklari Kurun") in heading_paths


def test_chunk_web_page_excludes_boilerplate_text():
    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="example_com_guide")

    all_text = " ".join(chunk.text for chunk in chunks)
    assert "Copyright 2024" not in all_text
    assert "Home | About" not in all_text


def test_chunk_web_page_defaults_source_type_to_web():
    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="doc")

    assert all(chunk.source_type == "web" for chunk in chunks)


def test_chunk_web_page_uses_html_hash_as_default_doc_id():
    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="doc")

    assert all(chunk.doc_id == compute_html_hash(_REALISTIC_PAGE) for chunk in chunks)


def test_chunk_web_page_accepts_an_explicit_doc_id_override():
    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="doc", doc_id="explicit-hash")

    assert all(chunk.doc_id == "explicit-hash" for chunk in chunks)


def test_chunk_web_page_with_no_extractable_content_returns_no_chunks():
    empty_page = "<html><body></body></html>"

    assert chunk_web_page(empty_page, source_id="doc") == []


def test_chunk_web_page_citation_location_uses_heading_path():
    from app.llm.citation_location import location_for

    chunks = chunk_web_page(_REALISTIC_PAGE, source_id="doc")
    intro_chunk = next(c for c in chunks if c.heading_path == ("Kurulum Rehberi",))
    payload = {
        "page_number": intro_chunk.page_number,
        "paragraph_index": intro_chunk.paragraph_index,
        "heading_path": list(intro_chunk.heading_path),
    }

    assert location_for(payload) == "Kurulum Rehberi"
