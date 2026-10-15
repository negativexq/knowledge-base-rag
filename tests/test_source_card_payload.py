"""A source card for a merged evidence block shows the retrieved (anchor)
chunk: its location is the anchor's, so its snippet must be the anchor's
text too, not the start of the document. A block spanning several sections
also lists them, so the card can say so."""

from app.api.chat import source_payload
from app.evidence.section_aware import SectionAwareEvidenceBuilder
from app.retrieval.hybrid_search import SearchResult


def _chunk(chunk_id: str, text: str, paragraph: int, heading: list[str]) -> SearchResult:
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
            "heading_path": heading,
        },
    )


INSTALL = _chunk("c1", "Nimbus CLI pip ile kurulur.", 0, ["Kurulum"])
TOKEN = _chunk(
    "c2", "Erişim token'ları 90 gün geçerlidir.", 1, ["Kimlik Doğrulama", "Token Süresi"]
)
SYNC = _chunk("c3", "nimbus sync push klasörü yükler.", 2, ["Senkronizasyon"])


def test_a_merged_block_shows_its_anchor_text_and_location():
    block = SectionAwareEvidenceBuilder._block(TOKEN, [INSTALL, TOKEN, SYNC])

    card = source_payload(1, block)

    assert card["heading_path"] == ["Kimlik Doğrulama", "Token Süresi"]
    assert card["snippet"] == "Erişim token'ları 90 gün geçerlidir."
    assert card["section_labels"] == [
        "Kurulum",
        "Kimlik Doğrulama > Token Süresi",
        "Senkronizasyon",
    ]


def test_a_single_section_block_lists_one_section():
    block = SectionAwareEvidenceBuilder._block(TOKEN, [TOKEN])

    card = source_payload(1, block)

    assert card["snippet"] == "Erişim token'ları 90 gün geçerlidir."
    assert card["section_labels"] == ["Kimlik Doğrulama > Token Süresi"]


def test_a_truncated_or_plain_chunk_keeps_its_own_text():
    block = SectionAwareEvidenceBuilder._block(TOKEN, [INSTALL, TOKEN])
    SectionAwareEvidenceBuilder._truncate_block(block, 3)

    assert source_payload(1, block)["snippet"] == "Nimbus CLI pip"
    assert source_payload(1, INSTALL)["snippet"] == "Nimbus CLI pip ile kurulur."
    assert source_payload(1, INSTALL)["section_labels"] == ["Kurulum"]
