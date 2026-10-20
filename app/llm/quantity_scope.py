"""Scope-only model views of exact, application-owned arithmetic candidates."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from decimal import DecimalException
from typing import Any

from app.llm.quantities import candidate, execute, semantic_draft
from app.llm.quantity_state import QuantityRecord

INSTRUCTIONS = """For verified_operations, arithmetic execution and rounding belong to the
application. The claim shown is a semantic projection, not a new answer. Check the
entity, period, population, source-unit bindings and whether the named-input formula
answers the actual question. Do not recompute a quotient or invent a competing result.
checked_inputs are independently reviewed transcriptions; they are not original PDF text.
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
                    "source_support_ids": record.support_ids,
                    "context_support_ids": record.context_support_ids,
                    "execution_authority": "application_decimal",
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
