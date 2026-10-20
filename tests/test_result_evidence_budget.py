"""Checked proofs share the hard budget without competing with raw source expansion."""

import hashlib

import fitz
import pytest

from app.llm.adaptive import finalize_research
from app.llm.agentic import EvidenceLedger
from app.llm.quantities import collect
from app.llm.quantity_state import QuantityCheck, QuantitySource
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import block
from tests.test_quantities import active_session, label_draft


def test_reserve_is_inside_total_and_cannot_be_spent_by_raw_sources():
    ledger = EvidenceLedger(len, 300, result_reserve_tokens=100)
    assert ledger.add([block("s" * 160)])
    assert ledger.remaining_tokens == 0 and ledger.remaining_result_tokens == 100
    assert not ledger.add([block("x", id="raw")])
    assert ledger.add([block("proof" * 12, id="proof")], checked_result=True)
    assert ledger.remaining_tokens == 0 and ledger.remaining_result_tokens == 0
    assert not ledger.add([block("x", id="overflow")], checked_result=True)


def test_oversized_or_duplicate_proof_does_not_spend_reservation():
    ledger = EvidenceLedger(len, 300, result_reserve_tokens=100)
    ledger.add([block("s" * 160)])
    assert not ledger.add([block("p" * 61, id="large")], checked_result=True)
    assert ledger.remaining_result_tokens == 100
    proof = block("p" * 10, id="proof")
    assert ledger.add([proof], checked_result=True)
    remaining = ledger.remaining_result_tokens
    assert not ledger.add([proof], checked_result=True)
    assert ledger.remaining_result_tokens == remaining


def test_proof_reservation_does_not_bypass_authorization():
    from app.security.models import RetrievalContext

    ledger = EvidenceLedger(
        len,
        300,
        context=RetrievalContext("a"),
        source_ids=frozenset({"manual"}),
        result_reserve_tokens=100,
    )
    assert not ledger.add([block("proof", tenant_id="other")], checked_result=True)
    assert not ledger.add([block("proof", source_id="other")], checked_result=True)
    assert ledger.remaining_result_tokens == 300


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_full_raw_budget_preserves_checked_image_proof_for_finalization(tmp_path, accepted):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Blue box: Verifier\nBlue box: Analyzer")
        pdf.save(path)
    active, need = active_session(
        "Parser omits colors", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    seed = active.deps.ledger.blocks[0]
    seed.payload.update(
        source_id="manual_pdf", document_version=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    ledger = EvidenceLedger(
        lambda t: len(t.split()),
        1800,
        context=active.deps.ledger.context,
        source_ids=frozenset({"manual_pdf"}),
        result_reserve_tokens=1400,
    )
    ledger.add([seed])
    ledger.add(
        [
            block(
                "noise " * (ledger.remaining_tokens - 40),
                id="noise",
                source_id="manual_pdf",
                document_version=seed.payload["document_version"],
            )
        ]
    )
    assert ledger.remaining_tokens == 0
    active.deps.ledger = ledger
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                operation_kind="list",
                support_ids=["E1.S1"],
                modality="image",
                pages=[1],
            )
        if role == "quantity_collector":
            raw = label_draft().model_dump(
                include={"mode", "complete", "items", "list_order", "list_unique"}
            )
            for item in raw["items"]:
                item.pop("page")
                item.pop("source_ranges")
                item["image_ids"] = [data["source_images"][0]["image_id"]]
            return output_type.model_validate(raw)
        assert role == "quantity_checker"  # No finalizer or repeated answer call.
        return QuantityCheck(
            accepted=accepted, complete=accepted, reason="supported" if accepted else "unreadable"
        )

    active.call = call
    result = await collect(active, need, repairs_left=0)
    record = next(iter(active.state.quantities.values()))
    if accepted:
        assert record.proof_support_ids and result is not None
        assert ledger.remaining_result_tokens >= 0
        active.state.research_stop = "REQUEST_RESERVE"
        active.state = type(active.state).model_validate_json(active.state.model_dump_json())
        final, _ = await finalize_research(active)
        assert final.raw_answer() == result.raw_answer()
    else:
        assert result is None and not record.proof_support_ids
        assert ledger.remaining_result_tokens == 1400
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
