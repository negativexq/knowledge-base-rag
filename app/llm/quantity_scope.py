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
application. The claim shown is a semantic projection, not a new answer. Check the
entity, period, population, source-unit bindings and whether the named-input formula
answers the actual question. Do not recompute a quotient or invent a competing result.
checked_inputs are independently reviewed transcriptions; they are not original PDF text.
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
formatting their scalar/vector result belong to the application.
For list operations, the actual answer list remains visible. Independently checked
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
    return images, list(pages.values())


def semantic_scope_projection(
    payload: dict[str, Any], records: Iterable[QuantityRecord]
) -> tuple[dict[str, Any], list[str]]:
    """Hide computed numbers only for exact server candidates rechecked locally.

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
                record.draft.mode not in {"arithmetic", "count", "list"}
                or record.execution_status != "completed"
            ):
                continue
            try:
                expected = candidate(record).answer_parts[0].model_dump(mode="json")
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
            if record.draft.mode == "list":
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
                    "checked_inputs": semantic_draft(record.draft)["groups"],
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_inventory_count",
                    "input_authority": "independently_checked_original_images"
                    if record.modality == "image"
                    else "independently_checked_source_text",
                    "image_bindings": [b.model_dump() for b in record.image_bindings],
                }
            else:
                operation = {
                    "claim_index": claim["claim_index"],
                    "record_id": record.id,
                    "formula": record.draft.expression,
                    "interpretation": record.draft.interpretation,
                    "result_unit": record.draft.result_unit,
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
            if record.draft.mode != "list":
                claim["claim"] = {
                    "text": (
                        "Computed result under the independently reviewed source-input operation."
                    ),
                    "support_ids": actual["support_ids"],
                }
            # Generated proof text contains the result. The scope model receives
            # checked inputs explicitly and original sources, not the result again.
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
