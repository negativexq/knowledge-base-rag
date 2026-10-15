"""Each support unit carries the section of the chunk it came from, in a form
the model can read. A small source merged in full into one evidence block
used to label every unit with the anchor's section (the installation
paragraph was sent as "Kimlik Doğrulama/Token Süresi"), and the label was a
Python tuple repr: "['heading', ('Kimlik Doğrulama', 'Token Süresi'), 0]"."""

from app.evidence.section_aware import SectionAwareEvidenceBuilder
from app.evidence.support_units import build_support_units, serialize_support_units
from app.retrieval.hybrid_search import SearchResult


def _chunk(chunk_id: str, text: str, paragraph: int, **payload) -> SearchResult:
    return SearchResult(
        score=0.9,
        id=chunk_id,
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": "nimbus_cli_md",
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "page_number": 1,
            "paragraph_index": paragraph,
            **payload,
        },
    )


INSTALL = _chunk(
    "c-install",
    "Nimbus CLI, pip install nimbus-cli komutuyla kurulur.",
    0,
    heading_path=["Kurulum"],
)
TOKEN = _chunk(
    "c-token",
    "Erişim token'ları 90 gün geçerlidir.\n\nSüre dolunca yeniden giriş gerekir.",
    1,
    heading_path=["Kimlik Doğrulama", "Token Süresi"],
)


def _merged_block() -> SearchResult:
    """The token chunk is the retrieved anchor; the small source is merged."""
    block = SectionAwareEvidenceBuilder._block(TOKEN, [INSTALL, TOKEN])
    block.payload["evidence_id"] = "E1"
    return block


def test_units_of_a_merged_block_keep_their_own_chunk_section():
    units = build_support_units([_merged_block()])

    assert [(u.support_unit_id, u.section_label) for u in units] == [
        ("E1.S1", "Kurulum"),
        ("E1.S2", "Kimlik Doğrulama > Token Süresi"),
        ("E1.S3", "Kimlik Doğrulama > Token Süresi"),
    ]
    assert [u.contributing_chunk_ids for u in units] == [
        ("c-install",),
        ("c-token",),
        ("c-token",),
    ]
    assert units[0].section_id != units[1].section_id


def test_ids_and_texts_are_unchanged_by_per_chunk_splitting():
    block = _merged_block()
    units = build_support_units([block])

    assert [u.text for u in units] == [part.strip() for part in block.payload["text"].split("\n\n")]


def test_the_model_sees_a_readable_section_label():
    serialized = serialize_support_units(build_support_units([_merged_block()]))

    assert "section: Kurulum\n" in serialized
    assert "section: Kimlik Doğrulama > Token Süresi\n" in serialized
    assert "('" not in serialized
    assert "['heading'" not in serialized


def test_a_pdf_chunk_without_headings_is_labelled_by_page():
    pdf = _chunk("c-pdf", "İade süresi 30 gündür.", 0, page_number=3)
    block = SectionAwareEvidenceBuilder._block(pdf, [pdf])
    block.payload["evidence_id"] = "E1"

    [unit] = build_support_units([block])

    assert unit.section_label == "page 3"
    assert "section: page 3\n" in serialize_support_units([unit])


def test_a_truncated_block_falls_back_to_the_block_section():
    block = _merged_block()
    SectionAwareEvidenceBuilder._truncate_block(block, 4)

    [unit] = build_support_units([block])

    assert unit.section_label == "Kimlik Doğrulama > Token Süresi"
    assert unit.contributing_chunk_ids == ("c-install", "c-token")


def test_a_plain_chunk_with_a_heading_path_is_readable():
    plain = _chunk("c-plain", "Kural.", 0, heading_path=["Policy", "Returns"])
    plain.payload["evidence_id"] = "E1"

    [unit] = build_support_units([plain])

    assert unit.section_label == "Policy > Returns"
    assert unit.contributing_chunk_ids == ("c-plain",)
