"""Typed inputs and receipts for application-executed quantitative work."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm.scope_diagnostics import ScopeDiagnostic

QuantityMode = Literal["read", "arithmetic", "count", "select", "list"]


class QuantityData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuantitySource(QuantityData):
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
    items: list[QuantityItem] = Field(min_length=1, max_length=200)
    # Describes source boundaries, not a model's assertion of a total.
    boundary_witness: str = Field(default="", max_length=1500)
    boundary_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    complete: bool = False


class QuantityOperand(QuantityData):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="", max_length=100)
    witness: str = Field(default="", max_length=1500)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class QuantityOperation(QuantityData):
    mode: QuantityMode
    result_unit: str = Field(default="", max_length=100)
    interpretation: str = Field(default="", max_length=300)
    count_mode: Literal["per_group", "total", "distinct"] = "per_group"
    select_mode: Literal["minimum", "maximum"] = "minimum"
    list_order: Literal["source", "ascending", "descending"] = "source"
    list_unique: bool = False


class QuantityDraft(QuantityOperation):
    operands: list[QuantityOperand] = Field(default_factory=list, max_length=20)
    # A named-input formula, never a model-written result.
    expression: str = Field(default="", max_length=500)
    decimals: int = Field(default=3, ge=0, le=10)
    groups: list[QuantityGroup] = Field(default_factory=list, max_length=10)
    items: list[QuantityItem] = Field(default_factory=list, max_length=200)
    complete: bool = False

    @model_validator(mode="after")
    def coherent(self) -> QuantityDraft:
        if self.mode in {"read", "arithmetic", "select"}:
            if not self.operands or self.groups or self.items or self.count_mode != "per_group":
                raise ValueError("Numeric operations require named inputs, no item groups")
            if self.mode == "arithmetic" and not self.expression:
                raise ValueError("Arithmetic requires a formula")
            if self.mode == "select" and (self.expression or len(self.operands) < 2):
                raise ValueError("Selection requires at least two inputs, no formula")
            if self.mode == "read" and self.expression:
                raise ValueError("Reading returns source values, not formulas")
            if len({o.name for o in self.operands}) != len(self.operands):
                raise ValueError("Duplicate operand names")
        elif self.mode == "count":
            if not self.groups or self.operands or self.expression or self.items:
                raise ValueError("Counting requires item groups, no arithmetic")
        elif not self.items or self.operands or self.expression or self.groups:
            raise ValueError("Listing requires source items, no arithmetic or count groups")
        if self.mode != "list" and (self.list_order != "source" or self.list_unique):
            raise ValueError("List formatting only applies to listing")
        if self.mode != "select" and self.select_mode != "minimum":
            raise ValueError("Selection operation only applies to selection")
        return self


class QuantityCheck(QuantityData):
    accepted: bool
    complete: bool
    # No replacement numbers, answer or repair plan can be supplied here.
    reason: Literal["supported", "wrong_scope", "wrong_binding", "incomplete", "unreadable"]


class QuantityIssue(QuantityData):
    kind: Literal["wrong_binding", "missing_item", "boundary", "operation", "unreadable"]
    target: Literal["operand", "group", "item", "operation"]
    index: int | None = Field(default=None, ge=0, le=199)
    description: str = Field(min_length=1, max_length=600)
    source_ranges: list[SourceRange] = Field(default_factory=list, max_length=4)
    page: int | None = Field(default=None, ge=1, le=2000)
    witness: str = Field(default="", max_length=1000)
    question_start: int = Field(default=1, ge=1)
    question_end: int = Field(default=1, ge=1)
    needed_evidence: str = Field(default="", max_length=300)
    evidence_kind: Literal["unspecified", "printed_values", "entity_inventory"] = "unspecified"


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


class QuantityCatalogPage(QuantityData):
    source_id: str
    document_version: str
    physical_page: int = Field(ge=1, le=2000)
    pdf_page_label: str = ""
    native_lines: list[str] = Field(default_factory=list, max_length=6)
    support_ids: list[str] = Field(min_length=1, max_length=3)
    location_hints_only: Literal[True] = True


class QuantityImageBinding(QuantityData):
    image_id: str
    source_id: str
    document_version: str | None
    physical_page: int


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


class TextQuantityOperand(QuantityOperand):
    # Text mode exposes references, not a free-form quotation field.
    witness: Literal[""] = ""
    source_ranges: list[SourceRange] = Field(min_length=1, max_length=4)


class TextQuantityItem(QuantityItem):
    witness: Literal[""] = ""
    source_ranges: list[SourceRange] = Field(min_length=1, max_length=4)


class TextQuantityGroup(QuantityData):
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
    complete: bool = False


class QuantityRepairRequirement(QuantityData):
    evidence_kind: Literal[
        "source_correction", "entity_inventory", "coverage_completion", "scope_research"
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


class QuantitySelection(QuantitySource):
    # The selector must explicitly choose context or state that none is needed.
    context_support_ids: list[str] = Field(max_length=3)


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
