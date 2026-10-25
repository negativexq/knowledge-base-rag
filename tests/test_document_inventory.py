"""A document plan drives bounded windows and one independent batch review."""

import hashlib
from dataclasses import replace

import fitz
import pytest

from app.llm.adaptive import ResearchClosed
from app.llm.document_inventory import (
    SEARCH_CHECK,
    SEARCH_COLLECT,
    InventoryReview,
    collect_document,
    overview,
    validate_plan,
)
from app.llm.quantities import collect
from app.llm.quantity_scope import checked_scope_images, semantic_scope_projection
from app.llm.quantity_state import DocumentInventoryPlan, QuantitySelection
from app.llm.scope_validation import scope_payload
from app.llm.visual_answer import PdfPages
from tests.test_quantities import active_session


def plan(count=6):
    return DocumentInventoryPlan(
        counting_unit="Individual diagrams",
        output="count_and_pages",
        pages=[
            dict(page=p, action="inspect", reason="Visible diagram") for p in range(1, count + 1)
        ],
    )


def prepared(tmp_path, textless=None):
    path = tmp_path / "manual.pdf"
    with fitz.open() as doc:
        for page in range(1, 7):
            p = doc.new_page()
            if page != textless:
                p.insert_text((30, 40), f"Diagram {page}\nRepeated source label")
            p.draw_rect(fitz.Rect(30, 60, 170, 120))
        doc.save(path)
    active, need_id = active_session(
        "Diagram 1", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active.deps.ledger.blocks[0].payload.update(source_id="manual_pdf", document_version=version)
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    need = active.state.evidence_needs[need_id]
    active.state.evidence_needs[need_id] = need.model_copy(
        update={
            "spec": need.spec.model_copy(
                update={"operation": "count", "inventory_scope": "document"}
            )
        }
    )
    return active, need_id


def calls(active, *, complete=True, stop_check=False):
    seen = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        seen.append(role)
        if role == "quantity_selector":
            assert images and data["document_overview"]["page_count"] == 6
            return QuantitySelection(
                available=True,
                operation_kind="count",
                inventory_scope="document",
                support_ids=["E1.S1"],
                context_support_ids=[],
                pages=[1],
                modality="image",
                document_plan=plan(),
            )
        if role == "extractor":
            assert len(images) == 3 and "previous_inputs" not in data
            assert set(output_type.model_fields) == {"items", "complete"}
            return output_type.model_validate(
                dict(
                    complete=True,
                    items=[
                        dict(
                            label="Repeated source label",
                            page=p,
                            position=1,
                            witness=f"Diagram {p}",
                        )
                        for p in data["window_pages"]
                    ],
                )
            )
        assert role == "quantity_checker" and output_type is InventoryReview
        assert len(data["windows"]) == 2 and len(images) == 7
        assert data["application_operation"]["count_output"] == "count_and_pages"
        assert "plan" not in data and "counting_unit" not in data
        assert data["question"] == active.state.task.question
        assert all("draft" not in w and "count_output" not in w for w in data["windows"])
        if stop_check:
            raise ResearchClosed("TOKEN_RESERVE")
        return InventoryReview(
            windows=[
                dict(window_index=i, inputs="supported", local_coverage="complete")
                for i in range(2)
            ],
            document_coverage="complete" if complete else "incomplete",
            operation="supported",
        )

    active.call = call
    return seen


@pytest.mark.asyncio
async def test_plan_executes_two_windows_with_no_reselection_and_one_batch_check(tmp_path):
    active, need = prepared(tmp_path)
    seen = calls(active)
    answer = await collect(active, need)
    assert answer.answer_parts[0].text == 'Total: 6; pages ["1", "2", "3", "4", "5", "6"]'
    assert seen == [
        "quantity_selector",
        "extractor",
        "extractor",
        "quantity_checker",
    ]
    assert not active.deps.validation(answer).failure_codes
    run = next(iter(active.state.document_inventories.values()))
    assert run.complete and run.aggregate_id
    record = active.state.quantities[run.aggregate_id]
    assert len(record.draft.groups[0].items) == 6
    assert len({b.image_id for b in record.image_bindings}) == 6
    images, metadata = await checked_scope_images(active, [record.id])
    assert len(images) == 7 and metadata[-1]["overview_pages"] == list(range(1, 7))
    payload, ids = semantic_scope_projection(
        scope_payload(active.deps.question, answer.raw_answer(), active.deps.ledger.units), [record]
    )
    assert ids == [record.id]
    assert payload["verified_operations"][0]["count_output"] == "count_and_pages"


@pytest.mark.asyncio
async def test_incomplete_document_review_preserves_all_supported_items_without_total(tmp_path):
    active, need = prepared(tmp_path)
    calls(active, complete=False)
    assert await collect(active, need) is None
    run = next(iter(active.state.document_inventories.values()))
    assert run.reviewed and not run.complete and not run.aggregate_id
    assert len(next(iter(active.state.inventories.values())).items) == 6
    assert all(not r.has_result for r in active.state.quantities.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["supported", "mismatch"])
async def test_inventory_review_uses_question_and_source_without_planner_output_rules(
    tmp_path, operation
):
    active, need = prepared(tmp_path)
    seen = calls(active)
    original = active.call

    async def call(role, output_type, instructions, data, **kwargs):
        result = await original(role, output_type, instructions, data, **kwargs)
        if role == "quantity_checker":
            assert data["application_operation"]["page_unique"] is True
            assert "Record a page for every figure" not in str(data)
            return result.model_copy(update={"operation": operation})
        return result

    active.call = call
    proposed = plan().model_copy(update={
        "counting_unit": "Individual diagrams. Record a page for every figure."
    })
    view = await overview(active, need)
    result = await collect_document(active, need, proposed, view)
    assert seen == ["extractor", "extractor", "quantity_checker"]
    run = next(iter(active.state.document_inventories.values()))
    assert len(next(iter(active.state.inventories.values())).items) == 6
    if operation == "supported":
        assert result is not None and run.complete
        aggregate = active.state.quantities[run.aggregate_id]
        assert aggregate.draft.groups[0].label == "Source objects"
        assert "Record a page for every figure" not in result.raw_answer()
        assert all(
            "Record a page for every figure" not in active.units()[sid].text
            for sid in aggregate.proof_support_ids
        )
    else:
        assert result is None and not run.complete and not run.aggregate_id


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["complete", "budget", "unresolved", "invalid_page"])
async def test_coverage_gap_opens_only_requested_page_and_preserves_checked_windows(tmp_path, case):
    active, need = prepared(tmp_path)
    active.limits.request_limit = 4 if case == "budget" else 10
    proposed = plan().model_copy(update={"pages": [
        p.model_copy(update={"action": "exclude"}) if p.page == 6 else p for p in plan().pages
    ]})
    reads, reviews = [], []

    async def call(role, output_type, instructions, data, **kwargs):
        active.usage.requests += 1
        if role == "extractor":
            pages = data["window_pages"]
            reads.append(pages)
            return output_type.model_validate(dict(complete=True, items=[
                dict(label="Repeated source label", page=p, position=1, witness=f"Diagram {p}")
                for p in pages if p != 6
            ]))
        assert role == "quantity_checker"
        reviews.append(data)
        first = len(reviews) == 1
        return output_type.model_validate(dict(
            windows=[dict(window_index=i, inputs="supported", local_coverage="complete")
                     for i in range(len(data["windows"]))],
            operation="supported",
            document_coverage="incomplete" if first or case == "unresolved" else "complete",
            missing_detail_pages=([7 if case == "invalid_page" else 6] if first else []),
        ))

    active.call = call
    view = await overview(active, need)
    result = await collect_document(active, need, proposed, view)
    run = next(iter(active.state.document_inventories.values()))
    assert reads[:2] == [[1, 2, 3], [4, 5]]
    assert len(next(iter(active.state.inventories.values())).items) == 5
    if case in {"complete", "unresolved"}:
        assert reads == [[1, 2, 3], [4, 5], [6]]
        assert active.usage.requests == 5
        assert reviews[-1]["previous_coverage_review"]["missing_detail_pages"] == [6]
        assert len(run.previous_reviews) == 1
    else:
        assert len(reads) == 2 and len(reviews) == 1 and active.usage.requests == 3
    if case == "complete":
        assert result.answer_parts[0].text == 'Total: 5; pages ["1", "2", "3", "4", "5"]'
        assert run.complete
    else:
        assert result is None and not run.complete and run.aggregate_id is None


@pytest.mark.asyncio
async def test_prepared_windows_resume_after_checker_stop_without_retranscription(tmp_path):
    active, need = prepared(tmp_path)
    seen = calls(active, stop_check=True)
    view = await overview(active, need)
    with pytest.raises(ResearchClosed, match="TOKEN_RESERVE"):
        await collect_document(active, need, plan(), view)
    assert seen == ["extractor", "extractor", "quantity_checker"]
    state = type(active.state).model_validate_json(active.state.model_dump_json())
    active.state = state
    seen = calls(active)
    answer = await collect_document(active, need, plan(), view)
    assert answer and seen == ["quantity_checker"]


def test_page_plan_cannot_hide_unknown_pages_or_repeat_one_page():
    assert validate_plan(plan(), 6) == list(range(1, 7))
    with pytest.raises(ValueError, match="PAGE_COVERAGE_INVALID"):
        validate_plan(plan(5), 6)
    duplicate = plan().model_copy(update={"pages": [plan().pages[0]] * 6})
    with pytest.raises(ValueError, match="PAGE_COVERAGE_INVALID"):
        validate_plan(duplicate, 6)
    uncertain = plan().model_copy(
        update={"pages": [p.model_copy(update={"action": "uncertain"}) for p in plan().pages]}
    )
    assert validate_plan(uncertain, 6) == list(range(1, 7))


@pytest.mark.asyncio
async def test_version_change_is_rejected_before_collection(tmp_path):
    active, need = prepared(tmp_path)
    view = await overview(active, need)
    view["document_version"] = "stale"
    seen = calls(active)
    with pytest.raises(ValueError, match="VERSION_MISMATCH"):
        await collect_document(active, need, plan(), view)
    assert not seen


@pytest.mark.asyncio
async def test_a_global_complete_flag_cannot_override_an_incomplete_local_window(tmp_path):
    active, need = prepared(tmp_path)
    calls(active)
    original = active.call

    async def call(role, output_type, instructions, data, **kwargs):
        result = await original(role, output_type, instructions, data, **kwargs)
        if role == "quantity_checker":
            result = result.model_copy(
                update={
                    "windows": [
                        w.model_copy(update={"local_coverage": "unknown"})
                        if w.window_index == 0
                        else w
                        for w in result.windows
                    ]
                }
            )
        return result

    active.call = call
    assert await collect(active, need) is None
    run = next(iter(active.state.document_inventories.values()))
    assert run.review.document_coverage == "complete" and not run.complete
    assert run.aggregate_id is None


@pytest.mark.asyncio
async def test_source_visibility_is_rechecked_before_resume(tmp_path):
    active, need = prepared(tmp_path)
    seen = calls(active)
    await collect(active, need)
    run = next(iter(active.state.document_inventories.values()))
    for block in active.deps.ledger.blocks:
        block.payload["model_visible"] = False
    with pytest.raises(ValueError):
        await checked_scope_images(active, [run.aggregate_id])
    assert seen.count("extractor") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("compact", [False, True])
async def test_full_verification_accepts_original_detail_and_overview_images(tmp_path, compact):
    active, need = prepared(tmp_path)
    seen = calls(active)
    answer = await collect(active, need)
    active.deps = replace(active.deps, scope_validation_enabled=True)
    active.compact_context = compact
    original = active.call

    async def call(role, output_type, instructions, data, **kwargs):
        if role != "scope_validator":
            return await original(role, output_type, instructions, data, **kwargs)
        seen.append(role)
        assert kwargs["research"] is False
        assert len(kwargs["images"]) == 7
        assert data["source_images"][-1]["overview_pages"] == list(range(1, 7))
        assert data["claims"][0]["claim"]["text"] == answer.answer_parts[0].text
        assert "counts" not in data["claims"][0]["claim"]
        assert "calculation" not in data["claims"][0]["claim"]
        source_id = answer.answer_parts[0].support_ids[1]
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[
                            dict(support_id=source_id, field="text", start_line=2, end_line=2)
                            if compact
                            else dict(support_id=source_id, quote="Repeated source label"),
                            *([dict(
                                support_id=source_id, field="text", start_line=999, end_line=999
                            )] if compact else [])
                        ],
                    )
                ]
            )
        )

    active.call = call
    verified, receipt = await active.verify(answer)
    assert verified == answer and receipt and not receipt.failure_codes
    assert seen[-1] == "scope_validator"



def search_calls(active, assignment):
    seen = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        seen.append(role)
        if role == "quantity_selector":
            return QuantitySelection(
                available=True,
                operation_kind="count",
                inventory_scope="document",
                support_ids=["E1.S1"],
                context_support_ids=[],
                pages=[1],
                modality="text",
                document_plan=plan().model_copy(update={"search_terms": ["diagram"]}),
            )
        if role == "extractor":
            if images:
                raise ResearchClosed("IMAGE_WINDOW")
            assert instructions == SEARCH_COLLECT
            assert [(h["id"], h["page"], h["text"]) for h in data["search_hits"]] == [
                (f"H{p}", p, f"Diagram {p}") for p in range(1, 7)
            ]
            return output_type.model_validate(assignment)
        assert role == "quantity_checker" and not images and "source_images" not in data
        assert instructions == SEARCH_CHECK and "overview_sheet_count" not in data
        assert data["search_reading"] == assignment and len(data["search_hits"]) == 6
        return InventoryReview(
            windows=[dict(window_index=0, inputs="supported", local_coverage="complete")],
            document_coverage="complete",
            operation="supported",
        )

    active.call = call
    return seen


def assignment(last):
    items = [dict(label=f"Diagram {p}", line=f"H{p}", repeats=[]) for p in range(1, 6)]
    excluded = []
    if last == "repeat":
        items[0]["repeats"] = ["H6"]
    elif last == "excluded":
        excluded = [dict(line="H6", reason="Contents entry, not a diagram")]
    return dict(complete=True, items=items, excluded=excluded)


@pytest.mark.asyncio
@pytest.mark.parametrize("last", ["repeat", "excluded"])
async def test_written_labels_are_counted_from_searched_lines_without_page_images(tmp_path, last):
    active, need = prepared(tmp_path)
    seen = search_calls(active, assignment(last))
    answer = await collect(active, need)
    assert seen == ["quantity_selector", "extractor", "quantity_checker"]
    assert answer.answer_parts[0].text == 'Total: 5; pages ["1", "2", "3", "4", "5"]'
    run = next(iter(active.state.document_inventories.values()))
    record = active.state.quantities[run.aggregate_id]
    assert record.modality == "text" and not record.image_bindings
    assert [i.witness for i in record.draft.groups[0].items] == [
        f"Diagram {p}" for p in range(1, 6)
    ]
    assert await checked_scope_images(active, [record.id]) == ([], [])
    payload, _ = semantic_scope_projection(
        scope_payload(active.deps.question, answer.raw_answer(), active.deps.ledger.units), [record]
    )
    assert payload["verified_operations"][0]["input_authority"] == (
        "independently_checked_source_text"
    )


@pytest.mark.asyncio
async def test_every_searched_line_must_be_counted_repeated_or_excluded(tmp_path):
    active, need = prepared(tmp_path)
    search_calls(active, assignment("dropped"))
    with pytest.raises(ValueError, match="INVENTORY_SEARCH_HIT_UNACCOUNTED"):
        await collect(active, need)


@pytest.mark.asyncio
async def test_a_page_without_native_text_keeps_image_windows(tmp_path):
    active, need = prepared(tmp_path, textless=6)
    seen = search_calls(active, assignment("excluded"))
    with pytest.raises(ResearchClosed, match="IMAGE_WINDOW"):
        await collect(active, need)
    assert seen == ["quantity_selector", "extractor"]


@pytest.mark.asyncio
async def test_a_searched_count_over_more_than_three_pages_reaches_scope_review(tmp_path):
    active, need = prepared(tmp_path)
    search_calls(active, assignment("excluded"))
    answer = await collect(active, need)
    active.deps = replace(active.deps, scope_validation_enabled=True)
    source_id = next(
        key for key in answer.answer_parts[0].support_ids
        if active.units()[key].text == "Diagram 1"
    )
    seen = []

    async def call(role, output_type, instructions, data, **kwargs):
        seen.append(role)
        assert not kwargs["images"]
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[dict(support_id=source_id, quote="Diagram 1")],
                    )
                ]
            )
        )

    active.call = call
    verified, receipt = await active.verify(answer)
    assert verified == answer and receipt and not receipt.failure_codes
    assert seen == ["scope_validator"]
