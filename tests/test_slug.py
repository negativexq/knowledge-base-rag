from app.shared.slug import slugify


def test_strips_extension():
    assert slugify("handbook.pdf") == "handbook"


def test_collapses_non_word_characters():
    assert slugify("Omer Faruk KOC - CV.pdf") == "Omer_Faruk_KOC_-_CV"


def test_empty_stem_falls_back_to_doc():
    assert slugify(".pdf") == "doc"
