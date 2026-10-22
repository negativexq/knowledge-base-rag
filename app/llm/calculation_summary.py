"""Browser-facing summaries of application calculations.

Only values the application already checked and computed are listed: the
formula, its result and each input with the support unit it was read from.
Source witnesses and model text are left out.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.llm.research_state import ResearchState


def _proof(units: Mapping[str, Any], block_id: str) -> list[str]:
    return [sid for sid, u in units.items() if block_id in getattr(u, "contributing_chunk_ids", ())]


def _label(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def calculation_summaries(state: ResearchState, units: Mapping[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for result in state.computations.values():
        if result.plan.mode != "arithmetic":
            continue
        inputs = []
        for item in result.plan.inputs:
            fact = state.facts.get(item.fact_id)
            if fact is None:
                continue
            obs = fact.observation
            inputs.append(
                {
                    "name": item.name,
                    "label": _label(obs.category, obs.series, obs.period),
                    "value": obs.value,
                    "unit": obs.unit,
                    "support_id": fact.evidence.support_id,
                    "page": fact.evidence.page,
                }
            )
        proof = _proof(units, "calculation-" + result.id)
        summaries.append(
            {
                "id": result.id[:16],
                "expression": result.plan.expression,
                "result": result.value,
                "unit": result.plan.output_unit,
                "inputs": inputs,
                "support_ids": sorted({*proof, *(i["support_id"] for i in inputs)}),
            }
        )
    for result in state.text_computations.values():
        summaries.append(
            {
                "id": result.id[:16],
                "expression": result.plan.expression,
                "result": result.value,
                "unit": "",
                "inputs": [
                    {
                        "name": "",
                        "label": "",
                        "value": None,
                        "unit": "",
                        "support_id": ref.support_id,
                        "page": ref.page,
                    }
                    for ref in result.sources
                ],
                "support_ids": sorted(
                    {*result.proof_support_ids, *(r.support_id for r in result.sources)}
                ),
            }
        )
    for record in state.quantities.values():
        draft = record.draft
        if (
            draft.mode != "arithmetic"
            or record.execution_status != "completed"
            or record.review_status == "rejected"
            or not record.values
        ):
            continue
        inputs = []
        for operand in draft.operands:
            support = next((r.support_id for r in operand.source_ranges), None)
            inputs.append(
                {
                    "name": operand.name,
                    "label": operand.label,
                    "value": operand.value,
                    "unit": operand.unit,
                    "support_id": support
                    or (record.support_ids[0] if record.support_ids else None),
                    "page": operand.page,
                }
            )
        summaries.append(
            {
                "id": record.id[:16],
                "expression": record.expression or draft.expression,
                "result": record.values[0],
                "unit": draft.result_unit,
                "inputs": inputs,
                "support_ids": sorted(
                    {*record.proof_support_ids, *record.support_ids}
                    | {i["support_id"] for i in inputs if i["support_id"]}
                ),
            }
        )
    return summaries
