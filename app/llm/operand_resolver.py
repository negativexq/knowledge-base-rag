"""Operand resolution for answers that must be computed.

When the first answer is withheld (the model abstained or the validator
blocked it), a question that asks for a computed figure (a ratio, a
difference, a change, a sum) gets a second, narrower try: the model plans
the calculation as a program over named operands and, for each operand,
copies the value and the row and column labels printed next to it in one
unit. Code checks each operand against its unit's text (value and every
label), searches once for the operands the evidence lacks, computes the
program, and renders one answer part whose calculation the ordinary
support-unit validator checks again. The model never does the arithmetic,
and a value whose labels its unit does not print is never used.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app.evidence.support_units import (
    SupportUnit,
    build_support_units,
    serialize_support_units,
    support_unit_map,
)
from app.evidence.table_facts import Fact, header_line, unit_facts
from app.llm.calculation import Calculation, evaluate_expression, numbers_in
from app.llm.premise import asks_count, missing_question_dates, missing_question_years
from app.llm.prompt import build_messages
from app.retrieval.hybrid_search import SearchResult

Retrieve = Callable[[str], Awaitable[list[SearchResult]]]

RESOLVER_INSTRUCTIONS = """
The question may ask for a number computed from figures the evidence units print
(a ratio, a difference, a change, a sum, a percentage of a total). Plan it as a
program over named operands and return
{"program": ..., "operands": [...], "result_label": ..., "percent": ..., "decimals": ...}.
- "program": an expression over the operand names with + - * / and parentheses
  (and 100, for a percentage), e.g. "(a - b) / b * 100". A named ratio or
  measure (a return, a coverage ratio, EBITDA) is computed from its
  standard definition. Write the program even when some operand values are missing.
  null only when the question does not ask for a computed number.
- Each operand: "name" (a, b, c, ...); "what": the figure in the question's
  words; "value": one figure exactly as one unit prints it, or null (a
  total of several printed figures is one operand per figure in the program,
  never a value like "72 + 980");
  "support_id": that unit, or null; "labels": the row and column labels printed
  next to the value in that unit, copied exactly (the line item, the year);
  "search": when "value" is null, a short search query for the figure, else null.
- "result_label": what the result is, in the question's words, with no numbers
  other than years. "percent": true when the result is a percentage.
  "decimals": the decimals the question asks for, or null.
- A number of people asked for when the units print only their share of a
  group (a survey's "36% rate them as poor"): the share times the group's
  size, "a / 100 * b", where b is the unweighted sample size printed for that
  same group ("Total sample 1,503", "Dem/Lean Dem 710", "(n=537)"). Add or
  subtract shares of the same group before multiplying.
Values and labels are checked against the unit's text; never compute the result.
""".strip()

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_PROGRAM_TOKEN = re.compile(r"[a-z][a-z0-9_]*|\d+(?:\.\d+)?|[+\-*/()\s]")
# Units found by a targeted search are few: the best blocks per missing operand.
RETRIEVED_BLOCKS_PER_OPERAND = 3
DEFAULT_DECIMALS = 2


@dataclass(frozen=True)
class Operand:
    name: str
    what: str
    value: str | None
    support_id: str | None
    labels: tuple[str, ...]
    search: str | None


@dataclass(frozen=True)
class OperandPlan:
    program: str | None
    operands: tuple[Operand, ...]
    result_label: str
    percent: bool
    decimals: int | None


@dataclass
class ResolverTrace:
    raw_outputs: list[str] = field(default_factory=list)
    plan_codes: list[str] = field(default_factory=list)
    operand_codes: dict[str, list[str]] = field(default_factory=dict)
    searches: list[str] = field(default_factory=list)
    retrieved_units: int = 0
    # The searched blocks, for the citation map; not part of the telemetry.
    blocks: list[SearchResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_outputs": self.raw_outputs,
            "plan_codes": self.plan_codes,
            "operand_codes": self.operand_codes,
            "searches": self.searches,
            "retrieved_units": self.retrieved_units,
        }


def resolver_schema(units: list[SupportUnit]) -> dict[str, Any]:
    support_ids = [unit.support_unit_id for unit in units]
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "program": nullable_string,
            "operands": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "what": {"type": "string"},
                        "value": nullable_string,
                        "support_id": {
                            "anyOf": [{"type": "string", "enum": support_ids}, {"type": "null"}]
                        },
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "search": nullable_string,
                    },
                    "required": ["name", "what", "value", "support_id", "labels", "search"],
                },
            },
            "result_label": {"type": "string"},
            "percent": {"type": "boolean"},
            "decimals": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        },
        "required": ["program", "operands", "result_label", "percent", "decimals"],
    }


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse_operand_plan(raw: str) -> OperandPlan:
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("operands", []), list):
        raise ValueError("operand plan must be an object with an operands list")
    operands = tuple(
        Operand(
            name=str(item.get("name", "")).strip(),
            what=str(item.get("what", "")).strip(),
            value=_text(item.get("value")),
            support_id=_text(item.get("support_id")),
            labels=tuple(
                label.strip()
                for label in item.get("labels") or []
                if isinstance(label, str) and label.strip()
            ),
            search=_text(item.get("search")),
        )
        for item in data.get("operands", [])
        if isinstance(item, dict)
    )
    decimals = data.get("decimals")
    return OperandPlan(
        program=_text(data.get("program")),
        operands=operands,
        result_label=str(data.get("result_label", "")).strip(),
        percent=bool(data.get("percent")),
        decimals=decimals if isinstance(decimals, int) and 0 <= decimals <= 6 else None,
    )


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def block_texts(units: list[SupportUnit]) -> dict[str, str]:
    """Each evidence block's text, from its units: a table's header row is a
    unit of the block its rows belong to."""
    texts: dict[str, list[str]] = {}
    for unit in units:
        texts.setdefault(unit.parent_evidence_block_id, []).append(unit.text)
    return {block: "\n".join(parts) for block, parts in texts.items()}


def _names(fact: Fact, labels: list[str]) -> bool:
    """Every label is in the fact's row, column or section, and one is in its
    row."""
    row, column, section = (_normalized(text) for text in (fact.row, fact.column, fact.section))
    return any(label in row for label in labels) and all(
        label in row or label in column or (section and label in section) for label in labels
    )


def bound_fact(
    operand: Operand,
    available: dict[str, SupportUnit],
    blocks: dict[str, str] | None = None,
) -> tuple[list[str], Fact | None]:
    """Failure codes for one operand, and the table fact it is bound to.

    A value its unit prints in a table row binds only to the one fact (value,
    row label, column) its labels name; a value whose row or column cannot be
    read is unresolved. A value printed only in prose binds when the unit
    prints a label and every other label is in the unit or its block.
    """
    if operand.value is None or operand.support_id is None:
        return ["OPERAND_MISSING"], None
    unit = available.get(operand.support_id)
    if unit is None or not unit.model_visible or not unit.authorized:
        return ["OPERAND_UNIT_UNAVAILABLE"], None
    values = numbers_in(operand.value)
    if len(values) != 1:
        return ["OPERAND_VALUE_NOT_A_NUMBER"], None
    if values[0] not in numbers_in(unit.text):
        return ["OPERAND_VALUE_NOT_IN_UNIT"], None
    if not operand.labels:
        return ["OPERAND_LABELS_MISSING"], None
    block = (blocks or {}).get(unit.parent_evidence_block_id, unit.text)
    labels = [_normalized(label) for label in operand.labels]
    table = unit_facts(unit.text, header_line(block))
    candidates = [fact for fact in table.facts if fact.value == values[0]]
    if candidates or values[0] in table.unresolved:
        named = [fact for fact in candidates if _names(fact, labels)]
        if values[0] in table.unresolved and len(named) <= 1:
            return ["OPERAND_FACT_UNRESOLVED"], None
        if len(named) > 1:
            return ["OPERAND_FACT_AMBIGUOUS"], None
        if not named:
            return ["OPERAND_LABEL_NOT_IN_UNIT"], None
        return [], named[0]
    unit_text = _normalized(unit.text)
    block_text = _normalized(block)
    if not any(label in unit_text for label in labels) or any(
        label not in unit_text and label not in block_text for label in labels
    ):
        return ["OPERAND_LABEL_NOT_IN_UNIT"], None
    return [], None


def bind_operand(
    operand: Operand,
    available: dict[str, SupportUnit],
    blocks: dict[str, str] | None = None,
) -> list[str]:
    """Failure codes for one operand; empty when it is bound."""
    return bound_fact(operand, available, blocks)[0]


def plan_codes(plan: OperandPlan) -> list[str]:
    """Failure codes for the plan's shape; empty when the program uses only
    its operands' names and allowed operators."""
    if plan.program is None:
        return ["NO_CALCULATION_ASKED"]
    names = [operand.name for operand in plan.operands]
    if not names or len(set(names)) != len(names) or not all(_NAME.match(n) for n in names):
        return ["OPERAND_NAMES_INVALID"]
    tokens = _PROGRAM_TOKEN.findall(plan.program)
    if "".join(tokens) != plan.program:
        return ["PROGRAM_INVALID"]
    used = {token for token in tokens if _NAME.match(token)}
    if not used or not used <= set(names):
        return ["PROGRAM_INVALID"]
    return []


def count_shape_codes(question: str, plan: OperandPlan) -> list[str]:
    """A question that asks how many is not answered by a percentage."""
    return ["PERCENT_PLAN_FOR_COUNT_QUESTION"] if asks_count(question) and plan.percent else []


def _shaped(question: str, plan: OperandPlan) -> OperandPlan:
    """A count is a whole number unless the question asks for decimals."""
    if asks_count(question) and plan.decimals is None:
        return replace(plan, decimals=0)
    return plan


def _format(value: float, decimals: int | None) -> str:
    """At the asked decimals; otherwise a whole number as is, else two."""
    if decimals is None:
        decimals = 0 if float(value).is_integer() else DEFAULT_DECIMALS
    return f"{value:,.{decimals}f}"


def compute(plan: OperandPlan) -> Calculation:
    """The program with each operand's value in place of its name, and its
    result at the asked (or default) precision."""
    values = {
        operand.name: str(numbers_in(operand.value or "")[0]).removesuffix(".0")
        for operand in plan.operands
    }
    expression = re.sub(
        r"[a-z][a-z0-9_]*", lambda match: values[match.group(0)], plan.program or ""
    )
    result = evaluate_expression(expression)
    return Calculation(expression=expression, result=_format(result, plan.decimals))


def render_part_text(plan: OperandPlan, calculation: Calculation) -> str:
    result = f"{calculation.result}{'%' if plan.percent else ''}"
    operands = "; ".join(
        f"{operand.what}: {operand.value}" for operand in plan.operands if operand.value
    )
    label = plan.result_label.rstrip(".") or "Result"
    return f"{label}: {result} ({operands})."


def _retrieved_blocks(blocks: list[SearchResult], offset: int) -> list[SearchResult]:
    """Blocks from a targeted search, with evidence ids that cannot collide
    with the first answer's ("R1", "R2", ...)."""
    return [
        replace(block, payload={**block.payload, "evidence_id": f"R{offset + index}"})
        for index, block in enumerate(blocks, 1)
    ]


async def _plan(
    question: str,
    units: list[SupportUnit],
    provider: Any,
    generation_kwargs: dict[str, Any],
    prompt_version: str,
    context_serializer: Any,
    trace: ResolverTrace,
) -> OperandPlan | None:
    messages = build_messages(
        question,
        units,
        version=prompt_version,
        context_serializer=context_serializer or serialize_support_units,
        system_prompt_suffix=RESOLVER_INSTRUCTIONS,
    )
    raw = await provider.chat_json(messages, schema=resolver_schema(units), **generation_kwargs)
    trace.raw_outputs.append(raw)
    try:
        return parse_operand_plan(raw)
    except (ValueError, json.JSONDecodeError):
        trace.plan_codes.append("PLAN_SCHEMA_INVALID")
        return None


def _bind_all(
    plan: OperandPlan, units: list[SupportUnit], trace: ResolverTrace
) -> tuple[list[Operand], list[Fact]]:
    available = support_unit_map(units)
    blocks = block_texts(units)
    missing = []
    facts = []
    for operand in plan.operands:
        codes, fact = bound_fact(operand, available, blocks)
        trace.operand_codes[operand.name] = codes
        if codes:
            missing.append(operand)
        elif fact is not None:
            facts.append(fact)
    return missing, facts


async def resolve_operands(
    question: str,
    units: list[SupportUnit],
    provider: Any,
    *,
    generation_kwargs: dict[str, Any],
    prompt_version: str,
    context_serializer: Any,
    retrieve: Retrieve | None = None,
) -> tuple[OperandPlan | None, Calculation | None, list[SupportUnit], ResolverTrace]:
    """Plan, bind, search once for what is missing, bind again, compute.
    Returns the plan and calculation only when every operand is bound."""
    trace = ResolverTrace()
    plan = await _plan(
        question, units, provider, generation_kwargs, prompt_version, context_serializer, trace
    )
    if plan is None or (codes := plan_codes(plan) or count_shape_codes(question, plan)):
        trace.plan_codes.extend(codes if plan is not None else [])
        return None, None, units, trace
    plan = _shaped(question, plan)
    missing, facts = _bind_all(plan, units, trace)
    if missing and retrieve is not None:
        retrieved: list[SearchResult] = []
        for operand in missing:
            query = operand.search or f"{operand.what} {' '.join(operand.labels)}".strip()
            trace.searches.append(query)
            found = (await retrieve(query))[:RETRIEVED_BLOCKS_PER_OPERAND]
            retrieved.extend(_retrieved_blocks(found, len(retrieved)))
        trace.blocks = retrieved
        new_units = build_support_units(retrieved)
        trace.retrieved_units = len(new_units)
        if new_units:
            units = [*units, *new_units]
            plan = await _plan(
                question,
                units,
                provider,
                generation_kwargs,
                prompt_version,
                context_serializer,
                trace,
            )
            if plan is None or (codes := plan_codes(plan) or count_shape_codes(question, plan)):
                trace.plan_codes.extend(codes if plan is not None else [])
                return None, None, units, trace
            plan = _shaped(question, plan)
            missing, facts = _bind_all(plan, units, trace)
    if missing:
        return plan, None, units, trace
    if len({fact.scale for fact in facts if fact.scale}) > 1:
        trace.plan_codes.append("OPERAND_SCALE_MISMATCH")
        return plan, None, units, trace
    try:
        calculation = compute(plan)
    except (ValueError, ZeroDivisionError, KeyError, IndexError):
        trace.plan_codes.append("PROGRAM_NOT_COMPUTABLE")
        return plan, None, units, trace
    return plan, calculation, units, trace


def question_premise_missing(question: str, units: list[SupportUnit]) -> bool:
    texts = [unit.text for unit in units]
    return bool(missing_question_years(question, texts) or missing_question_dates(question, texts))
