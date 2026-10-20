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
The original source IDs remain available for source-grounded witnesses and objections.
An explicitly declared, independently reviewed conventional formula is an interpretation,
not a claim that the document defines or reports that metric. It need not appear in the
document when the question leaves the convention open. It must not conflict with an
explicit question/source definition; reject a materially unjustified interpretation.
Different defensible conventions alone are not a contradiction. Never certify a reported
source metric by substituting an unstated calculation for it.
"""


async def checked_scope_images(
    session: AdaptiveSession, record_ids: list[str]
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
                record.draft.mode not in {"arithmetic", "count"}
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
            if record.draft.mode == "count":
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
            claim["claim"] = {
                "text": "Computed result under the independently reviewed source-input operation.",
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
