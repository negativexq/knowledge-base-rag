"""Application-owned research data; never an LLM-authored conversation summary."""

from __future__ import annotations

import ast
import hashlib
import json
import operator
import re
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm.answer_repair import AnswerRepair
from app.llm.quantity_state import QuantityCatalogPage, QuantityRecord, QuantitySourceInspection
from app.llm.scope_diagnostics import ScopeDiagnostic


class ResearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskSpec(ResearchRecord):
    question: str = Field(min_length=1, max_length=16000)


class EvidenceRef(ResearchRecord):
    support_id: str
    source_id: str
    document_version: str | None = None
    page: int | None = None


class ObservedValue(ResearchRecord):
    category: str = Field(min_length=1, max_length=500)
    series: str = Field(default="", max_length=500)
    period: str = Field(default="", max_length=200)
    value: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="", max_length=100)
    scale: str = Field(default="", max_length=100)
    qualifiers: list[str] = Field(default_factory=list, max_length=10)
    witness: str = Field(default="", max_length=2000)
    status: Literal["readable", "unreadable", "ambiguous"] = "ambiguous"

    @model_validator(mode="before")
    @classmethod
    def infer_omitted_status(cls, value: Any) -> Any:
        # Omission is formatting, not an independent proof of source accuracy.
        # Both source checking and need relevance checking still run afterwards.
        if isinstance(value, dict) and "status" not in value:
            status = (
                "readable"
                if value.get("value") is not None and value.get("witness")
                else "ambiguous"
            )
            return {**value, "status": status}
        return value

    @model_validator(mode="after")
    def readable_value(self) -> ObservedValue:
        if self.status == "readable" and (self.value is None or not self.witness.strip()):
            raise ValueError("Readable observations require a value and a source witness")
        if self.status != "readable" and self.value is not None:
            raise ValueError("Uncertain values must be null, never guessed")
        return self


class DataExtraction(ResearchRecord):
    title: str = Field(default="", max_length=500)
    notes: list[str] = Field(default_factory=list, max_length=30)
    values: list[ObservedValue] = Field(default_factory=list, max_length=100)
    complete: bool = False


class ExtractedFact(ResearchRecord):
    id: str
    observation: ObservedValue
    evidence: EvidenceRef
    method: Literal["text_witness", "image_checked"]


class ExtractionRecord(ResearchRecord):
    """Retain partial/unreadable observations without admitting them as facts."""

    evidence: EvidenceRef
    extraction: DataExtraction
    accepted_indexes: list[int]
    method: Literal["text_witness", "image_checked"]


class CalculationInput(ResearchRecord):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    fact_id: str = Field(min_length=1, max_length=100)


class ComputationPlan(ResearchRecord):
    mode: Literal["arithmetic", "display"] = "arithmetic"
    expression: str = Field(min_length=1, max_length=500)
    inputs: list[CalculationInput] = Field(min_length=1, max_length=20)
    output_unit: str = Field(default="", max_length=100)
    decimals: int = Field(default=3, ge=0, le=10)


class ComputationResult(ResearchRecord):
    id: str
    plan: ComputationPlan
    value: str
    # Numeric expression after explicit, dimension-checked conversions.
    expanded_expression: str
    support_ids: list[str]


class ResearchEvent(ResearchRecord):
    operation: str
    signature: str
    status: Literal["ok", "partial", "not_found", "error", "blocked"]
    added_support_ids: list[str] = Field(default_factory=list)
    detail: str = ""


class ReadCoverage(ResearchRecord):
    source_id: str
    document_version: str | None
    chunk_ids: list[str]
    support_ids: list[str]


class ReadRecovery(ResearchRecord):
    reason: Literal["REPEATED_READ", "READ_NO_NEW_EVIDENCE"]
    blocked_signature: str
    support_ids: list[str]
    status: Literal["pending", "search_requested", "answer_requested", "stopped", "failed"] = (
        "pending"
    )


class SearchEvidence(ResearchRecord):
    query: str
    need_id: str = ""
    admitted_support_ids: list[str]
    selected_support_ids: list[str]


class TextCalculationPlan(ResearchRecord):
    support_ids: list[str] = Field(min_length=1, max_length=12)
    expression: str = Field(min_length=1, max_length=500)
    decimals: int = Field(default=3, ge=0, le=10)


class TextCalculationResult(ResearchRecord):
    id: str
    plan: TextCalculationPlan
    value: str
    sources: list[EvidenceRef]
    proof_support_ids: list[str] = Field(default_factory=list)


class NeedConstraint(ResearchRecord):
    dimension: Literal["entity", "metric", "period", "population", "condition", "unit"]
    value: str = Field(min_length=1, max_length=300)
    question_quote: str = Field(min_length=1, max_length=500)


class NumericPresentation(ResearchRecord):
    decimals: int | None = Field(default=None, ge=0, le=10)
    order: Literal["source", "ascending", "descending"] = "source"
    question_quote: str = Field(min_length=1, max_length=500)


NeedField = Literal["category", "series", "period", "value", "unit", "scale"]


def default_requested_fields() -> list[NeedField]:
    return ["category", "value"]


class EvidenceNeedSpec(ResearchRecord):
    description: str = Field(min_length=1, max_length=600)
    requested_fields: list[NeedField] = Field(
        default_factory=default_requested_fields,
        min_length=1,
        max_length=6,
        description="Unknown axes to discover in the source, not fixed scope restrictions",
    )
    constraints: list[NeedConstraint] = Field(min_length=1, max_length=12)
    operation: Literal["lookup", "compare", "calculate", "sort", "count"] = "lookup"
    presentation: NumericPresentation | None = None


class EvidenceNeed(ResearchRecord):
    id: str
    spec: EvidenceNeedSpec
    status: Literal["unresolved", "partial", "satisfied"] = "unresolved"
    fact_ids: list[str] = Field(default_factory=list)


class ConstraintCheck(ResearchRecord):
    constraint_index: int = Field(ge=0)
    verdict: Literal["supported", "mismatch", "unknown"]


class SourceMatch(ResearchRecord):
    page: int | None = Field(default=None, ge=1, le=2000)
    title: str = Field(default="", max_length=600)
    kind: Literal["text", "table", "chart", "unknown"] = "unknown"
    element_id: str = Field(default="", max_length=30)
    checks: list[ConstraintCheck] = Field(max_length=12)

    def matches(self, spec: EvidenceNeedSpec) -> bool:
        checks = {c.constraint_index: c.verdict for c in self.checks}
        return (
            len(checks) == len(self.checks)
            and set(checks) == set(range(len(spec.constraints)))
            and all(v == "supported" for v in checks.values())
        )


class NeedSourceRecord(ResearchRecord):
    id: str
    need_id: str
    evidence: EvidenceRef
    candidate_pages: list[int]
    source_context: str = Field(default="", max_length=12000)
    context_limited: bool = False
    match: SourceMatch
    accepted: bool


class ObservationBinding(ResearchRecord):
    observation_index: int = Field(ge=0)
    verdicts: list[Literal["supported", "mismatch", "unknown"]] = Field(
        min_length=1,
        max_length=12,
        description="One verdict per need constraint, in its original order, for THIS observation",
    )


class NeedExtractionRecord(ResearchRecord):
    need_id: str
    selection_id: str
    extraction_index: int = Field(ge=0)
    relevant_indexes: list[int]
    bindings: list[ObservationBinding] = Field(default_factory=list)
    checks: list[ConstraintCheck]
    coverage: Literal["complete", "partial", "unresolved"]
    fact_ids: list[str] = Field(default_factory=list)


class PresentedValue(ResearchRecord):
    fact_id: str
    value: str
    computation_id: str | None = None
    support_ids: list[str]


class NeedPresentationRecord(ResearchRecord):
    need_id: str
    requested: NumericPresentation
    values: list[PresentedValue]
    rounding: Literal["decimal_half_even"] = "decimal_half_even"


class ResearchState(BaseModel):
    """Constructed and mutated by application code, not used as model output_type."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task: TaskSpec
    revision: int = 0
    evidence_needs: dict[str, EvidenceNeed] = Field(default_factory=dict)
    need_planning: Literal["pending", "ready", "failed"] = "pending"
    source_selections: list[NeedSourceRecord] = Field(default_factory=list)
    need_extractions: list[NeedExtractionRecord] = Field(default_factory=list)
    presentations: dict[str, NeedPresentationRecord] = Field(default_factory=dict)
    facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    extractions: list[ExtractionRecord] = Field(default_factory=list)
    computations: dict[str, ComputationResult] = Field(default_factory=dict)
    pending_calculations: list[ComputationPlan] = Field(default_factory=list)
    events: list[ResearchEvent] = Field(default_factory=list)
    read_coverage: dict[str, ReadCoverage] = Field(default_factory=dict)
    read_recovery: ReadRecovery | None = None
    search_evidence: list[SearchEvidence] = Field(default_factory=list)
    initial_support_ids: list[str] = Field(default_factory=list)
    text_computations: dict[str, TextCalculationResult] = Field(default_factory=dict)
    quantities: dict[str, QuantityRecord] = Field(default_factory=dict)
    quantity_source_inspections: list[QuantitySourceInspection] = Field(default_factory=list)
    quantity_page_catalog: list[QuantityCatalogPage] = Field(default_factory=list, max_length=72)
    quantity_repairs: int = 0
    quantity_scope_diagnostics: list[ScopeDiagnostic] = Field(default_factory=list)
    answer_repairs: list[AnswerRepair] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    research_stop: str | None = None
    finalization: Literal["pending", "running", "answered", "abstained", "failed"] = "pending"

    def add_need(self, spec: EvidenceNeedSpec) -> EvidenceNeed:
        # The model proposes a specification, never state, an expected answer,
        # a gold value, or a satisfaction status. IDs/statuses belong to code.
        if any(c.question_quote not in self.task.question for c in spec.constraints) or (
            spec.presentation is not None
            and spec.presentation.question_quote not in self.task.question
        ):
            raise ValueError("NEED_NOT_GROUNDED_IN_QUESTION")
        key = "N" + signature("need", spec.model_dump(), 0)[:24]
        if key not in self.evidence_needs:
            self.evidence_needs[key] = EvidenceNeed(id=key, spec=spec)
            self.revision += 1
        return self.evidence_needs[key]

    def add_facts(
        self,
        extraction: DataExtraction,
        ref: EvidenceRef,
        method: Literal["text_witness", "image_checked"],
    ) -> list[ExtractedFact]:
        added = []
        for observation in extraction.values:
            if observation.status != "readable":
                continue
            key = hashlib.sha256(
                (ref.model_dump_json() + observation.model_dump_json()).encode()
            ).hexdigest()[:24]
            fact_id = f"F{key}"
            if fact_id not in self.facts:
                fact = ExtractedFact(
                    id=fact_id, observation=observation, evidence=ref, method=method
                )
                self.facts[fact_id] = fact
                added.append(fact)
        if added:
            self.revision += 1
        return added

    def calculate(self, plan: ComputationPlan) -> ComputationResult:
        """Execute a prepared plan without asking a model to invoke a tool."""
        key = signature("calculate", plan.model_dump(), 0)
        if key in self.computations:
            return self.computations[key]
        if len({item.name for item in plan.inputs}) != len(plan.inputs):
            raise ValueError("Duplicate operand names")
        facts = {item.name: self.facts[item.fact_id] for item in plan.inputs}
        tree = ast.parse(plan.expression, mode="eval")
        if len(list(ast.walk(tree))) > 100:
            raise ValueError("Calculation too complex")
        with localcontext() as context:
            context.prec = 128
            context.rounding = ROUND_HALF_EVEN
            if plan.mode == "display":
                if (
                    len(plan.inputs) != 1
                    or not isinstance(tree.body, ast.Name)
                    or tree.body.id != plan.inputs[0].name
                ):
                    raise ValueError("Display formatting accepts one sourced operand only")
                fact = facts[plan.inputs[0].name]
                if plan.output_unit != fact.observation.unit:
                    raise ValueError("Display formatting cannot change units")
                # Decimal precision changes the printed number, not its unit or
                # magnitude scale. Unknown scale labels are never interpreted.
                value = decimal_value(fact.observation.value)
                expanded = str(value)
                output_factor = Decimal(1)
            else:
                quantities = {
                    name: (_scaled(fact.observation), fact.observation.unit)
                    for name, fact in facts.items()
                }
                value, dimension, expanded = _evaluate(tree.body, quantities)
                output_dim, output_factor = _unit(plan.output_unit)
                if dimension != output_dim:
                    raise ValueError("Output unit has a different dimension")
                value /= output_factor
            if not value.is_finite() or abs(value) > Decimal("1e30"):
                raise ValueError("Non-finite or unbounded result")
            value_text = f"{value:.{plan.decimals}f}"
        if output_factor != 1:
            expanded = f"({expanded}) / {output_factor}"
        result = ComputationResult(
            id=key,
            plan=plan,
            value=value_text,
            expanded_expression=expanded,
            support_ids=list(dict.fromkeys(f.evidence.support_id for f in facts.values())),
        )
        self.computations[key] = result
        self.revision += 1
        return result


def signature(operation: str, arguments: dict[str, object], revision: int) -> str:
    return hashlib.sha256(
        json.dumps([operation, arguments, revision], sort_keys=True).encode()
    ).hexdigest()


def decimal_value(value: str | None) -> Decimal:
    # Deliberately no guessing of locale/thousands separators.
    if value is None or len(value) > 100 or "," in value:
        raise ValueError("A canonical decimal value is required")
    number = Decimal(value)
    if not number.is_finite() or abs(number) > Decimal("1e30"):
        raise ValueError("Invalid numeric value")
    return number


def text_observation_supported(value: ObservedValue, source: str) -> bool:
    """A necessary lexical check, not a semantic proof of a table relationship."""
    if value.status != "readable" or not value.witness or value.witness not in source:
        return False
    if any(
        label and label not in value.witness
        for label in (
            value.category,
            value.series,
            value.period,
            value.unit,
            value.scale,
            *value.qualifiers,
        )
    ):
        return False
    assert value.value is not None
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value.value):
        # No ambiguous decimal/thousands normalization, detached digits or lost signs.
        numbers = re.findall(r"(?<![\w.,])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?![\w.,])", value.witness)
        return any(decimal_value(n) == decimal_value(value.value) for n in numbers)
    return value.value in value.witness


def _scaled(value: ObservedValue) -> Decimal:
    scales = {
        "": 1,
        "thousand": 1000,
        "million": 1000000,
        "billion": 1000000000,
        "lakh": 100000,
        "crore": 10000000,
    }
    if value.scale not in scales:
        raise ValueError("Unsupported scale; never guess a multiplier")
    return decimal_value(value.value) * scales[value.scale]


_UNITS = {
    "": ("scalar", "1"),
    "%": ("scalar", "0.01"),
    "m": ("length", "1"),
    "cm": ("length", "0.01"),
    "mm": ("length", "0.001"),
    "km": ("length", "1000"),
    "s": ("time", "1"),
    "min": ("time", "60"),
    "h": ("time", "3600"),
    "g": ("mass", "1"),
    "kg": ("mass", "1000"),
}


def _unit(unit: str) -> tuple[str, Decimal]:
    if unit in _UNITS:
        dimension, factor = _UNITS[unit]
        return dimension, Decimal(factor)
    # Currency and domain units only support identity; no implicit exchange rates.
    return f"opaque:{unit}", Decimal(1)


def _evaluate(
    node: ast.AST,
    values: dict[str, tuple[Decimal, str]],
) -> tuple[Decimal, str, str]:
    if isinstance(node, ast.Name) and node.id in values:
        value, unit = values[node.id]
        dimension, factor = _unit(unit)
        text = str(value) if factor == 1 else f"({value} * {factor})"
        return value * factor, dimension, text
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value, dimension, text = _evaluate(node.operand, values)
        return (
            (-value, dimension, f"(-{text})")
            if isinstance(node.op, ast.USub)
            else (value, dimension, text)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in {"mean", "min", "max"} or node.keywords or not node.args:
            raise ValueError("Unsupported aggregate")
        args = [_evaluate(arg, values) for arg in node.args]
        if len({dimension for _, dimension, _ in args}) != 1:
            raise ValueError("Aggregate requires the same dimensions")
        numbers = [n for n, _, _ in args]
        if node.func.id == "mean":
            return (
                sum(numbers, Decimal(0)) / len(numbers),
                args[0][1],
                "(" + " + ".join(t for _, _, t in args) + f") / {len(args)}",
            )
        chosen = min(numbers) if node.func.id == "min" else max(numbers)
        return chosen, args[0][1], next(t for n, _, t in args if n == chosen)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
        left, ld, lt = _evaluate(node.left, values)
        right, rd, rt = _evaluate(node.right, values)
        operations = {
            ast.Add: (operator.add, "+"),
            ast.Sub: (operator.sub, "-"),
            ast.Mult: (operator.mul, "*"),
            ast.Div: (operator.truediv, "/"),
        }
        operation, symbol = operations[type(node.op)]
        if isinstance(node.op, ast.Add | ast.Sub):
            if ld != rd:
                raise ValueError("Cannot add different dimensions")
            dimension = ld
        elif isinstance(node.op, ast.Mult):
            if ld != "scalar" and rd != "scalar":
                raise ValueError("Compound dimensions are not supported")
            dimension = rd if ld == "scalar" else ld
        else:
            if ld == rd:
                dimension = "scalar"
            elif rd == "scalar":
                dimension = ld
            else:
                raise ValueError("Compound dimensions are not supported")
        return operation(left, right), dimension, f"({lt} {symbol} {rt})"
    raise ValueError("Only named, sourced operands and arithmetic are allowed")
