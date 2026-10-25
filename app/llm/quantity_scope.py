"""Scope-only model views of exact, application-owned arithmetic candidates."""

from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Iterable
from decimal import DecimalException
from typing import TYPE_CHECKING, Any

from app.llm.quantities import candidate, execute, semantic_draft
from app.llm.quantity_numbers import normalize_inputs
from app.llm.quantity_state import QuantityRecord
from app.llm.quantity_units import arithmetic_conversion
from app.llm.research_state import EvidenceRef

if TYPE_CHECKING:
    from app.llm.adaptive import AdaptiveSession

INSTRUCTIONS = """For verified_operations, arithmetic execution and rounding belong to the
application. The actual published result remains visible for answer coverage; its
presence is not a claim that the PDF prints the computed number. The claim shown is
a semantic projection, not a new answer. Check the
entity, period, population, source-unit bindings and whether the named-input formula
answers the actual question. Do not recompute a quotient or invent a competing result.
checked_inputs are independently reviewed transcriptions; they are not original PDF text.
For result_kind=approximate, the output is a declared derived estimate, not an exact
observed count. Check each rate's population/denominator_population and conditional
base chain against the original source. A weighted/rounded rate applied to a compatible
sample can support that qualified estimate; do not require the source to print the
derived headcount. A combined subgroup base cannot establish a constituent subgroup's
count. Approximate wording does not repair a missing or incompatible base. Evaluate
the source's actual described metric, not a hypothetical finer distinction absent
from both the question's intent and the source's measurement.
For lookup, the application picks the choice whose score_expression is the select_mode
extreme and publishes that choice's value_operand; check that each choice's score inputs
and output value bind the question's entity, population and period.
For select, the application publishes the label of the checked input at the select_mode
extreme; check that each input binds the question's entity, population and period.
For arithmetic with input_authority=independently_checked_original_images, image_bindings
identify the original document/version/pages already reviewed. Check the formula and
the inputs' entity, period and unit relationships. Missing indexed/OCR text alone is
not a contradiction of independently checked image inputs. The supplied source_images
are those same original version-bound pages. For an input bound to a reviewed image,
the original image and checked transcription take precedence over differing digits
in indexed/parser text. Parser text is derivative context, not a competing original
reading. Use each input's image_ids/source_ranges to distinguish visual inputs from
retained text inputs. Do not reject solely because parser digits disagree; use the
original page to assess the binding. A concrete contradictory
source binding or unsupported interpretation still requires rejection.
For count operations, checked_inputs includes independently reviewed source items and
boundaries. Verify that this inventory's category, location and coverage answer the
question. Do not reject a checked image item merely because the indexed text omitted
it or require the image transcription to be printed as a numeric total. Concrete
source contradictions remain grounds for rejection. Counting checked items and
formatting their scalar/vector result belong to the application. The actual published
count/page-list text stays visible for material-answer coverage. Calculation/count
proof fields are omitted from that semantic view, not the answer itself.
With coverage_authority=application_native_text_search, search_coverage is the
application's own search of every page's native text: its terms, matching lines, repeats
and exclusions are the inventory boundary in place of closure_basis.
Numeric read operations retain numeric operands and their labels separately. For
read operations, the application owns numeric ordering and display rounding; check
the original inputs' identities, units and source bindings rather than requiring
the rounded array to be printed verbatim in the document. The actual array remains
visible for semantic review. Textual lists also remain visible. Independently checked
labels do not establish the requested visual condition or object identity. Inspect
the supplied original pages for the question's conditions and the item's location;
the collector's description is a proposal, not independent evidence of those facts.
The original source IDs remain available for source-grounded witnesses and objections.
An explicitly declared, independently reviewed conventional formula is an interpretation,
not a claim that the document defines or reports that metric. It need not appear in the
document when the question leaves the convention open. It must not conflict with an
explicit question/source definition; reject a materially unjustified interpretation.
Different defensible conventions alone are not a contradiction. Never certify a reported
source metric by substituting an unstated calculation for it.
"""


def checked_visual_fact_sources(session: AdaptiveSession) -> dict[str, EvidenceRef]:
    """Recover original provenance only for admitted, independently checked facts."""
    units = session.units()
    bound = {fid for need in session.state.evidence_needs.values() for fid in need.fact_ids}
    scoped = session.need_workflow is not None and session.state.need_planning == "ready"
    parents = {
        unit.support_unit_id: block.payload.get("parent_support_id")
        for unit in units.values()
        for block in session.deps.ledger.blocks
        if block.payload["evidence_id"] == unit.evidence_id
        and block.payload.get("reading_method") == "image_checked"
    }
    sources = {}
    for fact in session.state.facts.values():
        key = fact.evidence.support_id
        if fact.method != "image_checked" or (scoped and fact.id not in bound):
            continue
        parent = parents.get(key)
        if not parent:
            continue
        for extraction in session.state.extractions:
            ref = extraction.evidence
            if (
                extraction.method == "image_checked"
                and ref.support_id == parent
                and (ref.source_id, ref.document_version, ref.page)
                == (fact.evidence.source_id, fact.evidence.document_version, fact.evidence.page)
                and any(
                    0 <= i < len(extraction.extraction.values)
                    and extraction.extraction.values[i] == fact.observation
                    for i in extraction.accepted_indexes
                )
            ):
                sources[key] = ref
                break
    return sources


async def checked_scope_images(
    session: AdaptiveSession,
    record_ids: list[str],
    fact_sources: dict[str, EvidenceRef] | None = None,
) -> tuple[list[bytes], list[dict[str, Any]]]:
    """Reuse only reviewed original pages in the existing semantic scope call."""
    pages: dict[tuple[str, str, int], dict[str, Any]] = {}
    units = session.units()
    for record_id in record_ids:
        record = session.state.quantities[record_id]
        if record.modality != "image":
            continue
        if not record.image_bindings:
            raise ValueError("CHECKED_IMAGE_BINDING_UNAVAILABLE")
        for binding in record.image_bindings:
            session.require(binding.support_ids)
            if (
                not record.document_version
                or (binding.source_id, binding.document_version)
                != (record.source_id, record.document_version)
                or any(
                    not units[key].authorized
                    or not units[key].model_visible
                    or (units[key].source_id, units[key].document_version)
                    != (binding.source_id, binding.document_version)
                    or not units[key].page_number
                    or not units[key].page_number
                    <= binding.physical_page
                    <= (units[key].page_end or units[key].page_number)
                    for key in binding.support_ids
                )
            ):
                raise ValueError("CHECKED_IMAGE_BINDING_STALE")
            identity = (binding.source_id, record.document_version, binding.physical_page)
            page = pages.setdefault(identity, {**binding.model_dump(), "reviewed_bindings": []})
            page["reviewed_bindings"].append({"record_id": record.id, "image_id": binding.image_id})
    for key, ref in (fact_sources or {}).items():
        session.require([key, ref.support_id])
        derived, original = units[key], units[ref.support_id]
        if (
            not ref.document_version
            or ref.page is None
            or any(
                not unit.authorized
                or not unit.model_visible
                or (unit.source_id, unit.document_version) != (ref.source_id, ref.document_version)
                or not unit.page_number
                or not unit.page_number <= ref.page <= (unit.page_end or unit.page_number)
                for unit in [derived, original]
            )
        ):
            raise ValueError("CHECKED_IMAGE_BINDING_STALE")
        page = pages.setdefault(
            (ref.source_id, ref.document_version, ref.page),
            {
                "source_id": ref.source_id,
                "document_version": ref.document_version,
                "physical_page": ref.page,
                "support_ids": [ref.support_id],
                "reviewed_bindings": [],
            },
        )
        page.setdefault("fact_support_ids", []).append(key)
    images = []
    for page in pages.values():
        structure, _ = await session.deps.pdf_structure(page["support_ids"][0])
        async with asyncio.timeout(
            min(session.policy.tool_timeout_seconds, max(0, session.deadline - time.monotonic()))
        ):
            image = await asyncio.to_thread(
                structure.snapshot, page["source_id"], page["physical_page"]
            )
        if image is None:
            raise ValueError("CHECKED_IMAGE_PAGE_UNAVAILABLE")
        images.append(image)
        page["image_id"] = f"scope_image_{len(images)}"
    source_images = list(pages.values())
    for run in session.state.document_inventories.values():
        if (
            not run.complete
            or run.aggregate_id not in record_ids
            or session.state.quantities[run.aggregate_id].modality != "image"
        ):
            continue
        session.require([run.seed_support_id])
        seed = units[run.seed_support_id]
        if (seed.source_id, seed.document_version) != (run.source_id, run.document_version):
            raise ValueError("CHECKED_IMAGE_BINDING_STALE")
        structure, _ = await session.deps.pdf_structure(run.seed_support_id)
        overview = await asyncio.to_thread(structure.inventory_overview)
        if overview is None or overview["page_count"] != run.page_count:
            raise ValueError("CHECKED_IMAGE_BINDING_STALE")
        for index, png in enumerate(overview["images"]):
            images.append(png)
            source_images.append(
                {
                    "image_id": f"scope_image_{len(images)}",
                    "source_id": run.source_id,
                    "document_version": run.document_version,
                    "overview_pages": list(
                        range(index * 12 + 1, min((index + 1) * 12, run.page_count) + 1)
                    ),
                    "reviewed_bindings": [{"record_id": run.aggregate_id, "image_id": "overview"}],
                    "document_plan": run.plan.model_dump(),
                }
            )
    return images, source_images


def semantic_scope_projection(
    payload: dict[str, Any], records: Iterable[QuantityRecord]
) -> tuple[dict[str, Any], list[str]]:
    """Keep exact server output visible, separating execution from source authority.

    The original payload remains the release fingerprint. Ordinary/model-written
    claims, stale results and changed units/formulas keep full scope validation.
    Positive semantic support is still mandatory; nothing is auto-approved.
    """
    projected = copy.deepcopy(payload)
    verified = []
    records = list(records)
    for claim in projected["claims"]:
        actual = claim["claim"]
        for record in records:
            if (
                record.draft.mode not in {"arithmetic", "count", "list", "lookup", "read", "select"}
                or record.execution_status != "completed"
            ):
                continue
            try:
                answer = candidate(record)
                if answer.abstain or len(answer.answer_parts) != 1:
                    continue
                expected = answer.answer_parts[0].claim_dict()
                values, expression = execute(record.draft)
            except (ValueError, DecimalException):
                continue
            if values != record.values or expression != record.expression:
                continue
            if (
                arithmetic_conversion(record.draft, normalize_inputs(record.draft))
                != record.arithmetic_conversion
            ):
                continue
            if actual != expected:
                continue
            if record.draft.mode == "read":
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "operation": "read",
                    "checked_inputs": semantic_draft(record.draft)["operands"],
                    "output_order": record.draft.output_order,
                    "output_decimals": record.draft.output_decimals,
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                }
            elif record.draft.mode == "lookup":
                checked = semantic_draft(record.draft)
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "operation": "lookup",
                    "select_mode": record.draft.select_mode,
                    "checked_inputs": checked["operands"],
                    "choices": checked["choices"],
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_lookup",
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                }
            elif record.draft.mode == "select":
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "operation": "select",
                    "select_mode": record.draft.select_mode,
                    "checked_inputs": semantic_draft(record.draft)["operands"],
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_selection",
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                }
            elif record.draft.mode == "list":
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "operation": "list",
                    "checked_inputs": semantic_draft(record.draft),
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                }
            elif record.draft.mode == "count":
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "operation": "count",
                    "count_mode": record.draft.count_mode,
                    "count_output": record.draft.count_output,
                    "document_inventory_id": record.document_inventory_id,
                    "checked_inputs": semantic_draft(record.draft)["groups"],
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_inventory_count",
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                    **(
                        {
                            "coverage_authority": "application_native_text_search",
                            "search_coverage": record.search_coverage,
                        }
                        if record.search_coverage
                        else {}
                    ),
                }
            else:
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "formula": record.draft.expression,
                    "interpretation": record.draft.interpretation,
                    "result_unit": record.draft.result_unit,
                    "result_kind": record.draft.result_kind,
                    "decimals": record.draft.decimals,
                    "checked_inputs": semantic_draft(record.draft)["operands"],
                    "unit_conversion": record.arithmetic_conversion.model_dump()
                    if record.arithmetic_conversion
                    else None,
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_decimal",
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                    "definition_policy": (
                        "declared_interpretation_unless_question_or_source_conflicts"
                    ),
                }
            if record.draft.mode in {"arithmetic", "count"}:
                claim["claim"] = {
                    "text": actual["text"],
                    "support_ids": actual["support_ids"],
                }
            # Generated proofs cannot establish original-source relationships.
            # Keep the actual answer visible while supplying checked inputs and
            # original sources as independent authority for semantic bindings.
            claim["cited_evidence"] = [
                u
                for u in claim["cited_evidence"]
                if u["support_unit_id"] not in record.proof_support_ids
            ]
            verified.append(operation)
            break
    if verified:
        projected["verified_operations"] = verified
    return projected, [o["record_id"] for o in verified]
