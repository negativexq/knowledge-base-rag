from app.parsing.web_parser import extract_main_content

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
<h2>Adim 2: Konfigurasyon</h2>
<p>Sonra konfigurasyon dosyasini duzenleyin ve gerekli ayarlari yapin. Bu da
onemli bir adimdir ve dikkatli yapilmalidir cunku hatalar sorun cikarabilir.</p>
</article>
<footer>Copyright 2024 - Privacy Policy - Terms of Service - Contact Us</footer>
<aside>Related articles: Article 1, Article 2, Article 3 - sidebar spam content here</aside>
</body></html>"""


def test_extracts_headings_as_markdown_markers():
    content = extract_main_content(_REALISTIC_PAGE)

    assert content is not None
    assert "# Kurulum Rehberi" in content
    assert "## Adim 1: Bagimliliklari Kurun" in content
    assert "## Adim 2: Konfigurasyon" in content


def test_strips_navigation_boilerplate():
    content = extract_main_content(_REALISTIC_PAGE)

    assert "Home | About" not in content


def test_strips_footer_boilerplate():
    content = extract_main_content(_REALISTIC_PAGE)

    assert "Copyright 2024" not in content
    assert "Privacy Policy" not in content


def test_strips_sidebar_boilerplate():
    content = extract_main_content(_REALISTIC_PAGE)

    assert "sidebar spam" not in content


def test_keeps_real_article_content():
    content = extract_main_content(_REALISTIC_PAGE)

    assert "bagimliliklari yukleyin" in content
    assert "konfigurasyon dosyasini duzenleyin" in content


def test_returns_none_for_a_page_with_no_content_at_all():
    assert extract_main_content("<html><body></body></html>") is None
