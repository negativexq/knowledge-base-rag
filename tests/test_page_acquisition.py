"""Complete page context and cursor coverage are application data, not model summaries."""

import hashlib
from types import SimpleNamespace

import fitz
import pytest

from app.evidence.documents import DocumentResult
from app.llm.page_acquisition import attach_original_context, read_complete_page
from app.llm.quantities import collect
from app.llm.quantity_state import QuantityAssessment, QuantitySource
from app.llm.research_state import ResearchState
from tests.test_adaptive import block
from tests.test_quantity_units import scaled
from tests.test_source_acquisition import native_session


@pytest.mark.asyncio
async def test_page_cursor_keeps_header_and_last_row_without_repeated_first_slice(tmp_path):
    active, _, _ = native_session(tmp_path)
    version = active.units()["E1.S1"].document_version
    offsets = []

    async def read(request):
        offsets.append(request.offset)
        return DocumentResult(
            [
                block(
                    "Amounts in millions" if request.offset == 0 else "North 3",
                    id=f"chunk-{request.offset}",
                    source_id="manual_pdf",
                    document_version=version,
                    page_end=1,
                )
            ],
            [],
            has_more=request.offset == 0,
            next_offset=20 if request.offset == 0 else None,
        )

    active.deps.documents = SimpleNamespace(read=read)
    result = await read_complete_page(active, "E1.S1", 1)
    assert offsets == [0, 20] and not result.has_more
    assert [b.payload["text"] for b in result.blocks] == ["Amounts in millions", "North 3"]
    active.state = ResearchState.model_validate_json(active.state.model_dump_json())
    assert not (await read_complete_page(active, "E1.S1", 1)).has_more
    assert offsets == [0, 20]


@pytest.mark.asyncio
async def test_budget_stop_keeps_missing_cursor_and_resumes_checkpoint(tmp_path):
    active, _, _ = native_session(tmp_path)
    version = active.units()["E1.S1"].document_version
    offsets = []

    async def read(request):
        offsets.append(request.offset)
        return DocumentResult(
            [
                block(
                    f"Row {request.offset}",
                    id=str(request.offset),
                    source_id="manual_pdf",
                    document_version=version,
                    page_end=1,
                )
            ],
            [],
            has_more=request.offset == 0,
            next_offset=20 if request.offset == 0 else None,
        )

    active.deps.documents = SimpleNamespace(read=read)
    active.deps.observations.tool_calls = active.policy.max_tool_attempts - 1
    first = await read_complete_page(active, "E1.S1", 1)
    assert first.has_more and first.next_offset == 20
    checkpoint = next(iter(active.state.page_read_checkpoints.values()))
    assert checkpoint.stop_reason == "tool_budget" and checkpoint.offsets == [0]
    active.state = ResearchState.model_validate_json(active.state.model_dump_json())
    # A new authorized request/turn supplies its own budget; this tool never resets it.
    active.deps.observations.tool_calls = 0
    second = await read_complete_page(active, "E1.S1", 1)
    assert not second.has_more and len(second.blocks) == 2 and offsets == [0, 20]


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", [None, 0, -1, 2001])
async def test_invalid_cursor_never_implies_complete_or_repeats_reads(tmp_path, cursor):
    active, _, calls = native_session(tmp_path)
    version = active.units()["E1.S1"].document_version

    async def read(request):
        calls.append(request)
        return DocumentResult(
            [
                block(
                    "Partial row",
                    id="part",
                    source_id="manual_pdf",
                    document_version=version,
                    page_end=1,
                )
            ],
            [],
            has_more=True,
            next_offset=cursor,
        )

    active.deps.documents = SimpleNamespace(read=read)
    result = await read_complete_page(active, "E1.S1", 1)
    assert result.has_more and len(calls) == 1
    assert (await read_complete_page(active, "E1.S1", 1)).has_more
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_foreign_chunks_cannot_survive_cursor_checkpoint(tmp_path):
    active, _, _ = native_session(tmp_path)
    version = active.units()["E1.S1"].document_version

    async def read(request):
        return DocumentResult(
            [
                block(
                    "Secret",
                    id="secret",
                    source_id="manual_pdf",
                    document_version=version,
                    tenant_id="other",
                    page_end=1,
                )
            ],
            [],
        )

    active.deps.documents = SimpleNamespace(read=read)
    result = await read_complete_page(active, "E1.S1", 1)
    assert not result.blocks
    assert not next(iter(active.state.page_read_checkpoints.values())).chunks


@pytest.mark.asyncio
async def test_native_context_supplies_unit_and_period_before_first_extraction(tmp_path):
    active, need, _ = native_session(tmp_path)
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Amounts in millions of USD\n2023\nNorth 3")
        pdf.new_page().insert_text((30, 30), "Amounts in millions of USD\n2023\nSouth 7")
        pdf.save(path)
    seed = active.deps.ledger.blocks[0]
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    seed.payload["document_version"] = version

    async def read(request):
        return DocumentResult(
            [
                block(
                    "North 3" if request.page == 1 else "South 7",
                    id=f"page-{request.page}",
                    source_id="manual_pdf",
                    document_version=version,
                    page_number=request.page,
                    page_end=request.page,
                )
            ],
            [],
        )

    active.deps.documents = SimpleNamespace(read=read)
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"], pages=[1, 2])
        context = str(data["context_sources"])
        assert "Amounts in millions of USD" in context and "2023" in context
        assert all(not r["has_more"] for r in data["source_page_coverage"])
        if role == "quantity_collector":
            return scaled("a + b", "USD", scales=("1000000", "1000000"), units=("USD", "USD"))
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need, repairs_left=0)
    assert result is not None and result.answer_parts[0].text == "10000000.000 USD"
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
    assert all(r.support_ids and not r.limited for r in active.state.page_contexts)
    before = active.deps.ledger.remaining_tokens
    selection = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1, 2])
    await attach_original_context(active, selection)
    assert active.deps.ledger.remaining_tokens == before


@pytest.mark.asyncio
async def test_missing_object_search_advances_cursor_and_retains_prior_candidates():
    from app.llm.quantity_sources import complete_sources
    from tests.test_quantities import active_session
    from tests.test_quantity_completion import missing_record

    active, _ = active_session("Debt total without lease note")
    parent = missing_record()
    offsets = []

    async def read(request):
        offsets.append(request.offset)
        return DocumentResult(
            [
                block(
                    "Current and noncurrent lease liabilities in the note " + str(request.offset),
                    id=f"note-{request.offset}",
                    page_number=2 + request.offset,
                    page_end=2 + request.offset,
                )
            ],
            [],
            has_more=request.offset == 0,
            next_offset=3 if request.offset == 0 else None,
        )

    active.deps.documents = SimpleNamespace(read=read)
    first = await complete_sources(active, parent)
    second = await complete_sources(active, parent.model_copy(update={"id": "retry"}))
    assert offsets == [0, 3] and second.next_offset is None and not second.has_more
    assert set(first.candidate_support_ids) <= set(second.candidate_support_ids)
    third = await complete_sources(active, parent.model_copy(update={"id": "again"}))
    assert third.status == "unresolved" and offsets == [0, 3]


@pytest.mark.asyncio
async def test_gap_search_targets_one_missing_input_instead_of_repeating_whole_question():
    from app.llm.quantity_sources import complete_sources
    from tests.test_quantities import active_session
    from tests.test_quantity_completion import missing_record

    active, need_id = active_session("North 3; South is in the note")
    from app.llm.research_state import NeedConstraint

    active.state.task = active.state.task.model_copy(
        update={"question": "What is North's total for 2023?"}
    )
    need = active.state.evidence_needs[need_id]
    active.state.evidence_needs[need_id] = need.model_copy(
        update={
            "spec": need.spec.model_copy(
                update={
                    "constraints": [
                        NeedConstraint(dimension="entity", value="North", question_quote="North"),
                        NeedConstraint(dimension="period", value="2023", question_quote="2023"),
                    ]
                }
            )
        }
    )
    parent = missing_record().model_copy(update={"need_id": need_id})
    queries = []

    async def read(request):
        queries.append(request.query)
        return DocumentResult([], [])

    active.deps.documents = SimpleNamespace(read=read)
    await complete_sources(active, parent)
    assert queries == [parent.draft.operands[1].label + " North 2023"]
