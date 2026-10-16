"""The metadata event of the support-ID answer path lists the support units
the model was given, so the UI can resolve an "[E1.S4]" citation to its
source card (``source_rank`` is the 1-based position in the ``sources``
event), its own section and its own text."""

import json

import pytest

from app.evidence.section_aware import SectionAwareEvidenceBuilder
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult


def _chunk(chunk_id: str, text: str, paragraph: int, heading: list[str], source: str):
    return SearchResult(
        score=0.9,
        id=chunk_id,
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": source,
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "page_number": 1,
            "paragraph_index": paragraph,
            "heading_path": heading,
        },
    )


INSTALL = _chunk("c1", "Nimbus CLI pip ile kurulur.", 0, ["Kurulum"], "nimbus_cli_md")
TOKEN = _chunk(
    "c2",
    "Erişim token'ları 90 gün geçerlidir.",
    1,
    ["Kimlik Doğrulama", "Token Süresi"],
    "nimbus_cli_md",
)
PDF = SearchResult(
    score=0.5,
    id="p1",
    payload={
        "text": "Free accounts include 15GB of storage.",
        "source_type": "filesystem",
        "source_id": "nimbus_handbook_pdf",
        "document_version": "v1",
        "tenant_id": "tenant-a",
        "page_number": 3,
        "paragraph_index": 0,
    },
)


def _blocks() -> list[SearchResult]:
    merged = SectionAwareEvidenceBuilder._block(TOKEN, [INSTALL, TOKEN])
    merged.payload["evidence_id"] = "E1"
    pdf = SectionAwareEvidenceBuilder._block(PDF, [PDF])
    pdf.payload["evidence_id"] = "E2"
    return [merged, pdf]


class _Provider:
    last_call_observation = None

    def __init__(self):
        self.messages = None

    async def chat_json(self, messages, model, **kwargs):
        self.messages = messages
        return json.dumps(
            {"answer_parts": [{"text": "90 gün.", "support_ids": ["E1.S2"]}], "abstain": False}
        )


async def _metadata(**kwargs) -> dict:
    events = [
        event
        async for event in stream_support_unit_answer(
            "Token ne kadar geçerli?",
            _blocks(),
            _Provider(),
            model="qwen",
            validator_version="baseline",
            **kwargs,
        )
    ]
    [metadata] = [e for e in events if e["type"] == "metadata"]
    return metadata


@pytest.mark.asyncio
async def test_metadata_maps_every_support_id_to_its_source_section_and_text():
    metadata = await _metadata()

    assert metadata["support_units"] == [
        {
            "support_id": "E1.S1",
            "source_rank": 1,
            "source_type": "filesystem",
            "source_id": "nimbus_cli_md",
            "section_label": "Kurulum",
            "page_number": 1,
            "page_end": 1,
            "text": "Nimbus CLI pip ile kurulur.",
        },
        {
            "support_id": "E1.S2",
            "source_rank": 1,
            "source_type": "filesystem",
            "source_id": "nimbus_cli_md",
            "section_label": "Kimlik Doğrulama > Token Süresi",
            "page_number": 1,
            "page_end": 1,
            "text": "Erişim token'ları 90 gün geçerlidir.",
        },
        {
            "support_id": "E2.S1",
            "source_rank": 2,
            "source_type": "filesystem",
            "source_id": "nimbus_handbook_pdf",
            "section_label": "page 3",
            "page_number": 3,
            "page_end": 3,
            "text": "Free accounts include 15GB of storage.",
        },
    ]


@pytest.mark.asyncio
async def test_units_dropped_to_fit_the_context_are_not_listed():
    metadata = await _metadata(num_ctx=1, count_tokens=lambda text: len(text.split()))

    assert [unit["support_id"] for unit in metadata["support_units"]] == ["E1.S1"]
