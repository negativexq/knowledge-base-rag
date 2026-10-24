"""Typed inputs and receipts for application-executed quantitative work."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm.research_dispositions import ReviewedDisposition
from app.llm.scope_diagnostics import ScopeDiagnostic

QuantityMode = Literal["read", "arithmetic", "count", "select", "lookup", "list"]
NumberFormat = Literal["canonical", "decimal_point", "decimal_comma", "space_grouped"]
NumberScale = Literal["1", "1000", "100000", "1000000", "10000000", "1000000000"]
SourceNumber = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[0-9+\-−.,() \u00a0\u202f]+$")
]


class QuantityData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuantitySource(QuantityData):
    inventory_scope: Literal["document", "bounded_object", "unknown"] = "unknown"
    operation_kind: QuantityMode = "arithmetic"
    support_ids: list[str] = Field(default_factory=list, max_length=3)
    context_support_ids: list[str] = Field(default_factory=list, max_length=3)
    pages: list[int] = Field(
        default_factory=list,
        max_length=3,
        description="Physical pages for numeric inputs in support_ids; context pages are separate",
    )
    modality: Literal["text", "image"] = "text"
    available: bool = False


class SourceRange(QuantityData):
    support_id: str = Field(min_length=1, max_length=100)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class QuantityItem(QuantityData):
    position: int = Field(
        ge=1, le=1000, description="Item ordinal in this category on its source page"
    )
    text: str = Field(min_length=1, max_length=500)
    source_object: str = Field(
        default="",
        max_length=500,
        description="Source heading/column/region owning this item, not a nearby object",
    )
    witness: str = Field(default="", max_length=1500)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class QuantityGroup(QuantityData):
    label: str = Field(min_length=1, max_length=200)
    items: list[QuantityItem] = Field(max_length=200)
    object_anchor: str = Field(default="", max_length=500)
    closure_basis: Literal["bounded_object", "declared_inventory", "unresolved"] = "unresolved"
    closure_anchor: str = Field(default="", max_length=500)
    # Describes source boundaries, not a model's assertion of a total.
    boundary_witness: str = Field(default="", max_length=1500)
    boundary_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    complete: bool = False


class QuantityOperand(QuantityData):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    label: str = Field(min_length=1, max_length=200)
    value: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="", max_length=100)
    witness: str = Field(default="", max_length=1500)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class NumericReading(QuantityData):
    value_origin: Literal["source_printed", "counted_items"] = "source_printed"
    value: SourceNumber | None
    value_status: Literal["readable", "not_found", "unreadable", "ambiguous"] = "readable"
    number_format: NumberFormat = "canonical"
    source_scale: NumberScale = Field(
        default="1", description="Printed unit multiplier to base units"
    )

    @model_validator(mode="after")
    def status_matches_value(self) -> NumericReading:
        if self.value_status == "readable" and self.value is None:
            raise ValueError("A readable numeric input requires a source value")
        if self.value_status in {"not_found", "unreadable"} and self.value is not None:
            raise ValueError("An unavailable numeric input cannot carry a source value")
        return self


class QuantityNumericOperand(QuantityOperand, NumericReading):
    population: str = Field(default="", max_length=300)
    denominator_population: str = Field(default="", max_length=300)
    period: str = Field(default="", max_length=200)


class QuantityReadOperand(QuantityNumericOperand):
    output_unit: str = Field(default="", max_length=100)
    output_scale: NumberScale = Field(
        default="1", description="Requested unit multiplier to base units"
    )
    sign_convention: Literal["signed", "magnitude"] = "signed"


class QuantityLookupOperand(QuantityNumericOperand):
    binding_status: Literal["supported", "unknown"] = "supported"
    population: str = Field(default="", max_length=300)
    series: str = Field(default="", max_length=200)
    period: str = Field(default="", max_length=200)


class QuantityOperation(QuantityData):
    mode: QuantityMode
    result_unit: str = Field(default="", max_length=100)
    interpretation: str = Field(default="", max_length=800)
    result_kind: Literal["exact", "approximate"] = "exact"
    count_mode: Literal["per_group", "total", "distinct"] = "per_group"
    select_mode: Literal["minimum", "maximum"] = "minimum"
    list_order: Literal["source", "ascending", "descending"] = "source"
    list_unique: bool = False
    output_decimals: int | None = Field(default=None, ge=0, le=10)
    output_order: Literal["source", "ascending", "descending"] = "source"
    count_output: Literal["count", "pages", "count_and_pages"] = "count"


class QuantityLookupChoice(QuantityData):
    """Source identity joins a comparison expression to a different requested metric."""

    label: str = Field(min_length=1, max_length=200)
    score_expression: str = Field(min_length=1, max_length=500)
    value_operand: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")


class QuantityAbsence(QuantityData):
    """An inspected source region with no items satisfying the requested condition."""

    source_object: str = Field(min_length=1, max_length=500)
    witness: str = Field(default="", max_length=1500)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class QuantityDraft(QuantityOperation):
    operands: list[
        QuantityOperand | QuantityNumericOperand | QuantityLookupOperand | QuantityReadOperand
    ] = Field(default_factory=list, max_length=20)
    # A named-input formula, never a model-written result.
    expression: str = Field(default="", max_length=500)
    decimals: int = Field(default=3, ge=0, le=10)
    groups: list[QuantityGroup] = Field(default_factory=list, max_length=10)
    items: list[QuantityItem] = Field(default_factory=list, max_length=200)
    choices: list[QuantityLookupChoice] = Field(default_factory=list, max_length=10)
    absence: QuantityAbsence | None = None
    complete: bool = False

    @model_validator(mode="after")
    def coherent(self) -> QuantityDraft:
        if self.result_kind == "approximate" and self.mode != "arithmetic":
            raise ValueError("Approximate derivations require an arithmetic operation")
        if self.mode in {"read", "arithmetic", "select", "lookup"}:
            if not self.operands or self.groups or self.items or self.count_mode != "per_group":
                raise ValueError("Numeric operations require named inputs, no item groups")
            if self.mode == "arithmetic" and not self.expression:
                raise ValueError("Arithmetic requires a formula")
            if self.mode == "select" and (self.expression or len(self.operands) < 2):
                raise ValueError("Selection requires at least two inputs, no formula")
            if self.mode == "read" and self.expression:
                raise ValueError("Reading returns source values, not formulas")
            if self.mode == "lookup" and (self.expression or len(self.choices) < 2):
                raise ValueError("Conditional lookup requires comparison choices, no final formula")
            if len({o.name for o in self.operands}) != len(self.operands):
                raise ValueError("Duplicate operand names")
        elif self.mode == "count":
            if not self.groups or self.operands or self.expression or self.items:
                raise ValueError("Counting requires item groups, no arithmetic")
        elif (
            bool(self.items) == (self.absence is not None)
            or self.operands
            or self.expression
            or self.groups
        ):
            raise ValueError("Listing requires source items, no arithmetic or count groups")
        if self.mode != "lookup" and self.choices:
            raise ValueError("Comparison choices only apply to conditional lookup")
        if self.mode != "list" and self.absence is not None:
            raise ValueError("Absence evidence only applies to listing")
        if self.mode != "list" and (self.list_order != "source" or self.list_unique):
            raise ValueError("List formatting only applies to listing")
        if self.mode not in {"select", "lookup"} and self.select_mode != "minimum":
            raise ValueError("Selection operation only applies to selection")
        if self.mode not in {"read", "lookup"} and self.output_decimals is not None:
            raise ValueError("Output precision only applies to numeric read/lookup")
        if self.mode != "read" and self.output_order != "source":
            raise ValueError("Numeric output ordering only applies to read")
        if self.mode != "count" and self.count_output != "count":
            raise ValueError("Page inventory output only applies to count")
        return self


class QuantityCheck(QuantityData):
    accepted: bool
    complete: bool
    # No replacement numbers, answer or repair plan can be supplied here.
    reason: Literal["supported", "wrong_scope", "wrong_binding", "incomplete", "unreadable"]


class QuantityIssue(QuantityData):
    kind: Literal["wrong_binding", "missing_item", "boundary", "operation", "unreadable"]
    target: Literal["operand", "group", "item", "absence", "operation"]
    index: int | None = Field(default=None, ge=0, le=199)
    description: str = Field(min_length=1, max_length=600)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    witness: str = Field(default="", max_length=1000)
    question_start: int = Field(default=1, ge=1)
    question_end: int = Field(default=1, ge=1)
    needed_evidence: str = Field(default="", max_length=300)
    evidence_kind: Literal["unspecified", "printed_values", "entity_inventory"] = "unspecified"


class QuantityNotationCorrection(QuantityData):
    index: int = Field(ge=0, le=19)
    number_format: NumberFormat


class QuantityAssessment(QuantityData):
    inputs: Literal["supported", "mismatch", "unknown"]
    coverage: Literal["complete", "incomplete", "unknown"]
    operation: Literal["supported", "mismatch", "ambiguous", "unknown"]
    entity_identity: Literal["supported", "unknown"] = "unknown"
    list_unique: bool | None = Field(
        default=None,
        description="Question's name-set versus occurrence policy; null for other modes",
    )
    issues: list[QuantityIssue] = Field(default_factory=list, max_length=10)
    alternatives: list[Literal["per_group", "total", "distinct"]] = Field(
        default_factory=list, max_length=3
    )
    notation_corrections: list[QuantityNotationCorrection] = Field(
        default_factory=list, max_length=20
    )
    supported_operand_indexes: list[int] = Field(
        default_factory=list,
        max_length=20,
        description="Independently supported operands, even when other inputs are missing",
    )
    source_disposition: ReviewedDisposition | None = None


class QuantityCatalogPage(QuantityData):
    source_id: str
    document_version: str
    physical_page: int = Field(ge=1, le=2000)
    pdf_page_label: str = ""
    native_lines: list[str] = Field(default_factory=list, max_length=6)
    support_ids: list[str] = Field(min_length=1, max_length=3)
    numbered_items: list[str] = Field(default_factory=list, max_length=40)
    location_hints_only: Literal[True] = True


class QuantityImageBinding(QuantityData):
    image_id: str
    source_id: str
    document_version: str | None
    physical_page: int
    support_ids: list[str] = Field(default_factory=list, max_length=9)
    evidence_role: Literal["input", "context"] = "input"


class QuantityGapSearch(QuantityData):
    """Application-owned link from an unresolved receipt to candidate evidence and inspection."""

    parent_id: str
    source_id: str = ""
    document_version: str = ""
    offset: int = 0
    next_offset: int | None = None
    has_more: bool = False
    scan_limited: bool = False
    requirements: list[QuantityIssue] = Field(max_length=10)
    query: str = Field(max_length=500)
    candidate_support_ids: list[str] = Field(default_factory=list, max_length=6)
    inspected_support_ids: list[str] = Field(default_factory=list)
    inspected_pages: list[int] = Field(default_factory=list, max_length=3)
    status: Literal["located", "inspected", "resolved", "unresolved"] = "located"


class QuantityNumberReceipt(QuantityData):
    name: str
    source_value: str | None
    canonical_value: str | None = None
    source_scale: str = "1"
    output_scale: str = "1"
    sign_convention: Literal["signed", "magnitude"] = "signed"
    output_value: str | None = None
    output_unit: str = ""
    value_status: Literal["readable", "not_found", "unreadable", "ambiguous", "invalid"]
    errors: list[str] = Field(default_factory=list)


class QuantityArithmeticConversion(QuantityData):
    source_formula: str
    source_factors: dict[str, str]
    source_units: dict[str, str]
    output_unit: str
    output_scale: str
    result_dimension: str
    expression: str


class QuantityRecord(QuantityData):
    id: str
    need_id: str
    support_ids: list[str]
    context_support_ids: list[str] = Field(default_factory=list)
    source_id: str
    document_version: str | None
    pages: list[int]
    modality: Literal["text", "image"]
    draft: QuantityDraft
    check: QuantityCheck | None = None
    values: list[str] = Field(default_factory=list)
    expression: str = ""
    proof_support_ids: list[str] = Field(default_factory=list)
    assessments: list[QuantityAssessment] = Field(default_factory=list)
    review_status: Literal["pending", "accepted", "rejected", "indeterminate"] = "pending"
    diagnostic_errors: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    provisional_values: list[str] = Field(default_factory=list)
    ambiguity_results: dict[str, list[str]] = Field(default_factory=dict)
    execution_status: Literal["pending", "completed", "failed"] = "pending"
    image_bindings: list[QuantityImageBinding] = Field(default_factory=list)
    scope_diagnostic: ScopeDiagnostic | None = None
    inventory_replacement: bool = False
    numeric_inputs: list[QuantityNumberReceipt] = Field(default_factory=list)
    arithmetic_conversion: QuantityArithmeticConversion | None = None
    absence_confirmed: bool = False
    absence_scope: Literal["none", "inspected_material", "bounded_object"] = "none"
    supported_operand_indexes: list[int] = Field(default_factory=list)
    inventory_context: dict[str, Any] = Field(default_factory=dict)
    inventory_errors: list[str] = Field(default_factory=list)
    inventory_scope: Literal["document", "bounded_object", "unknown"] = "unknown"
    document_inventory_id: str | None = None


    @property
    def has_result(self) -> bool:
        return (
            bool(self.values)
            or (self.absence_confirmed and self.execution_status == "completed")
            or bool(
                self.draft.mode == "list"
                and self.draft.absence
                and self.execution_status == "completed"
            )
        )


class InventoryItemRef(QuantityData):
    """A checked source occurrence, never a model-authored running summary."""

    occurrence_id: str
    quantity_id: str
    group_index: int = Field(ge=0)
    item_index: int = Field(ge=0)


class InventoryWindow(QuantityData):
    quantity_id: str
    pages: list[int]
    input_status: Literal["pending", "supported", "rejected"]
    coverage: Literal["complete", "incomplete", "unknown"]


class InventoryProgress(QuantityData):
    id: str
    need_id: str
    source_id: str
    document_version: str
    windows: list[InventoryWindow] = Field(default_factory=list)
    items: list[InventoryItemRef] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    # This record accumulates observations. It cannot certify global completeness.
    complete: Literal[False] = False



class TextQuantityOperand(QuantityOperand):
    # Text mode exposes references, not a free-form quotation field.
    witness: Literal[""] = ""
    source_ranges: list[SourceRange] = Field(min_length=1, max_length=4)


class TextQuantityItem(QuantityItem):
    witness: Literal[""] = ""
    source_ranges: list[SourceRange] = Field(min_length=1, max_length=4)


class TextQuantityGroup(QuantityData):
    object_anchor: str = ""
    closure_basis: Literal["bounded_object", "declared_inventory", "unresolved"] = "unresolved"
    closure_anchor: str = ""
    label: str = Field(min_length=1, max_length=200)
    items: list[TextQuantityItem] = Field(min_length=1, max_length=200)
    boundary_witness: Literal[""] = ""
    boundary_ranges: list[SourceRange] = Field(min_length=1, max_length=4)
    complete: bool = False


class TextQuantityDraft(QuantityOperation):
    operands: list[TextQuantityOperand] = Field(default_factory=list, max_length=20)
    expression: str = Field(default="", max_length=500)
    decimals: int = Field(default=3, ge=0, le=10)
    groups: list[TextQuantityGroup] = Field(default_factory=list, max_length=10)
    items: list[TextQuantityItem] = Field(default_factory=list, max_length=200)
    choices: list[QuantityLookupChoice] = Field(default_factory=list, max_length=10)
    absence: QuantityAbsence | None = None
    complete: bool = False


class QuantityRepairRequirement(QuantityData):
    evidence_kind: Literal[
        "source_correction",
        "entity_inventory",
        "coverage_completion",
        "scope_research",
        "existing_scope",
    ]
    previous_support_ids: list[str] = Field(default_factory=list)


class EntityInventoryDraft(QuantityDraft):
    @model_validator(mode="after")
    def inventory_required(self) -> EntityInventoryDraft:
        if self.mode != "count":
            raise ValueError("REPAIR_REQUIRES_ENTITY_INVENTORY")
        return self


class TextEntityInventoryDraft(TextQuantityDraft):
    @model_validator(mode="after")
    def inventory_required(self) -> TextEntityInventoryDraft:
        if self.mode != "count":
            raise ValueError("REPAIR_REQUIRES_ENTITY_INVENTORY")
        return self


class ImageQuantityOperand(QuantityOperand):
    page: int = Field(ge=1, le=2000)
    witness: str = Field(min_length=1, max_length=1500)


class ImageQuantityItem(QuantityItem):
    page: int = Field(ge=1, le=2000)
    witness: str = Field(min_length=1, max_length=1500)


class ImageQuantityGroup(QuantityData):
    object_anchor: str = ""
    closure_basis: Literal["bounded_object", "declared_inventory", "unresolved"] = "unresolved"
    closure_anchor: str = ""
    label: str = Field(min_length=1, max_length=200)
    items: list[ImageQuantityItem] = Field(min_length=1, max_length=200)
    boundary_witness: str = Field(min_length=1, max_length=1500)
    boundary_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    complete: bool


class ImageQuantityDraft(QuantityOperation):
    operands: list[ImageQuantityOperand] = Field(default_factory=list, max_length=20)
    expression: str = Field(default="", max_length=500)
    decimals: int = Field(default=3, ge=0, le=10)
    groups: list[ImageQuantityGroup] = Field(default_factory=list, max_length=10)
    items: list[ImageQuantityItem] = Field(default_factory=list, max_length=200)
    choices: list[QuantityLookupChoice] = Field(default_factory=list, max_length=10)
    absence: QuantityAbsence | None = None
    complete: bool

    @model_validator(mode="after")
    def coherent(self) -> ImageQuantityDraft:
        QuantityDraft.model_validate(self.model_dump())
        return self


class ImageEntityInventoryDraft(ImageQuantityDraft):
    @model_validator(mode="after")
    def inventory_required(self) -> ImageEntityInventoryDraft:
        if self.mode != "count":
            raise ValueError("REPAIR_REQUIRES_ENTITY_INVENTORY")
        return self


class InventoryPageDecision(QuantityData):
    page: int = Field(ge=1, le=2000)
    action: Literal["inspect", "exclude", "uncertain"]
    reason: str = Field(min_length=1, max_length=300)


class DocumentInventoryPlan(QuantityData):
    counting_unit: str = Field(min_length=1, max_length=300)
    output: Literal["count", "pages", "count_and_pages"]
    pages: list[InventoryPageDecision] = Field(min_length=1, max_length=36)


class InventoryRepeat(QuantityData):
    item_index: int = Field(ge=0, description="item_index of the repeated mention in this window")
    repeats_window: int = Field(ge=0, le=12, description="window_index of the first transcription")
    repeats_item: int = Field(ge=0, description="item_index of the first transcription")


class InventoryWindowReview(QuantityData):
    window_index: int = Field(ge=0, le=12)
    inputs: Literal["supported", "mismatch", "unknown"]
    local_coverage: Literal["complete", "incomplete", "unknown"]
    repeats: list[InventoryRepeat] = Field(default_factory=list, max_length=200)


class DocumentInventoryReview(QuantityData):
    windows: list[InventoryWindowReview] = Field(min_length=1, max_length=13)
    document_coverage: Literal["complete", "incomplete", "unknown"]
    operation: Literal["supported", "mismatch", "ambiguous", "unknown"]
    issues: list[str] = Field(default_factory=list, max_length=12)
    missing_detail_pages: list[int] = Field(
        default_factory=list, max_length=3,
        description="Original physical pages needing detail images to resolve incomplete or "
        "unknown document coverage; empty when no missing-page inspection can resolve it",
    )


class DocumentInventoryRun(QuantityData):
    id: str
    need_id: str
    source_id: str
    document_version: str
    seed_support_id: str
    page_count: int
    plan: DocumentInventoryPlan
    window_ids: list[str] = Field(default_factory=list)
    reviewed: bool = False
    review: DocumentInventoryReview | None = None
    previous_reviews: list[DocumentInventoryReview] = Field(default_factory=list, max_length=1)
    additional_pages: list[int] = Field(default_factory=list, max_length=3)
    window_size: int | None = Field(default=None, ge=1)
    complete: bool = False
    aggregate_id: str | None = None


class QuantitySelection(QuantitySource):
    # The selector must explicitly choose context or state that none is needed.
    context_support_ids: list[str] = Field(max_length=3)
    document_plan: DocumentInventoryPlan | None = None


class PopulationQuantitySelection(QuantitySelection):
    """Aggregates are reported numbers or arithmetic, not respondent inventories."""

    operation_kind: Literal["read", "arithmetic"] = "arithmetic"
    inventory_scope: Literal["bounded_object", "unknown"] = "unknown"
    document_plan: None = None


class QuantityPageQuality(QuantityData):
    page: int
    native_text_chars: int
    image_area_fraction: float
    requires_image: bool


class QuantitySourceInspection(QuantityData):
    support_ids: list[str]
    source_id: str
    document_version: str
    pages: list[QuantityPageQuality]
