"""Operation-local model contracts; the application owns page identity and defaults."""

from __future__ import annotations

from types import GenericAlias
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, create_model

from app.evidence.support_units import SupportUnit
from app.llm.quantity_state import (
    ImageQuantityDraft,
    NumberScale,
    NumericReading,
    QuantityAssessment,
    QuantityData,
    QuantityDraft,
    QuantityImageBinding,
    QuantityIssue,
    QuantityLookupChoice,
    QuantityMode,
    SourceNumber,
    TextQuantityDraft,
)


def collection_contract(
    kind: QuantityMode,
    bindings: list[QuantityImageBinding],
    support_ids: list[str],
) -> type[BaseModel]:
    """Expose exactly one executable operation, with bounded source handles."""
    image = bool(bindings)
    locator: dict[str, Any]
    if image:
        image_id = Literal[tuple(b.image_id for b in bindings)]  # type: ignore[valid-type]
        locator = {
            "image_ids": (GenericAlias(list, image_id), Field(min_length=1, max_length=3)),
            "witness": (str, Field(min_length=1, max_length=1500)),
        }
    else:
        support_id = Literal[tuple(support_ids)]  # type: ignore[valid-type]
        ref = create_model(
            "CollectionSourceRange",
            __base__=QuantityData,
            support_id=(support_id, ...),
            start_line=(int, Field(ge=1)),
            end_line=(int, Field(ge=1)),
        )
        locator = {"source_ranges": (GenericAlias(list, ref), Field(min_length=1, max_length=4))}
    bindings_fields: dict[str, Any] = (
        {
            "population": (str, Field(max_length=300)),
            "series": (str, Field(max_length=200)),
            "period": (str, Field(max_length=200)),
        }
        if kind == "lookup"
        else {}
    )
    if kind == "read":
        bindings_fields.update(
            output_unit=(str, Field(default="", max_length=100)),
            output_scale=(NumberScale, "1"),
            sign_convention=(Literal["signed", "magnitude"], "signed"),
        )
    operand = create_model(
        "CollectionOperand",
        __base__=NumericReading,
        name=(str, Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")),
        label=(str, Field(min_length=1, max_length=200)),
        value=(SourceNumber | None, ...),
        unit=(str, Field(max_length=100)),
        **bindings_fields,
        **locator,
    )
    item = create_model(
        "CollectionItem",
        __base__=QuantityData,
        position=(int, Field(ge=1, le=1000)),
        text=(str, Field(min_length=1, max_length=500)),
        source_object=(str, Field(default="", max_length=500)),
        **locator,
    )
    fields: dict[str, Any] = {"mode": (Literal[kind], kind), "complete": (bool, ...)}
    if kind in {"read", "arithmetic", "select", "lookup"}:
        fields["operands"] = (
            GenericAlias(list, operand),
            Field(min_length=2 if kind == "select" else 1, max_length=20),
        )
    if kind == "arithmetic":
        fields.update(
            expression=(str, Field(min_length=1, max_length=500)),
            decimals=(int, Field(ge=0, le=10)),
            result_unit=(str, Field(max_length=100)),
            interpretation=(str, Field(max_length=300)),
        )
    elif kind in {"select", "lookup"}:
        fields["select_mode"] = (Literal["minimum", "maximum"], ...)
        if kind == "lookup":
            fields["choices"] = (list[QuantityLookupChoice], Field(min_length=2, max_length=10))
    elif kind == "list":
        absence = create_model(
            "CollectionAbsence",
            __base__=QuantityData,
            source_object=(str, Field(min_length=1, max_length=500)),
            **locator,
        )
        fields.update(
            items=(GenericAlias(list, item), Field(max_length=200)),
            absence=(absence | None, None),
            list_order=(Literal["source", "ascending", "descending"], ...),
            list_unique=(bool, ...),
        )
    elif kind == "count":
        boundaries: dict[str, Any] = (
            {"boundary_witness": (str, Field(min_length=1, max_length=1500))}
            if image
            else {"boundary_ranges": locator["source_ranges"]}
        )
        group = create_model(
            "CollectionGroup",
            __base__=QuantityData,
            label=(str, Field(min_length=1, max_length=200)),
            items=(GenericAlias(list, item), Field(min_length=1, max_length=200)),
            complete=(bool, ...),
            **boundaries,
        )
        fields.update(
            groups=(GenericAlias(list, group), Field(min_length=1, max_length=10)),
            count_mode=(Literal["per_group", "total", "distinct"], ...),
        )
    return create_model(
        f'Collect{kind.title()}{"Image" if image else "Text"}', __base__=QuantityData, **fields
    )


def bind_collection(
    output: BaseModel,
    bindings: list[QuantityImageBinding],
    units: dict[str, SupportUnit],
) -> QuantityDraft:
    """Map supplied handles to source pages; never infer a page from visible print."""
    data = output.model_dump(mode="json")
    if isinstance(output, QuantityDraft | ImageQuantityDraft | TextQuantityDraft):
        # Legacy serialized/application fixtures are distinct from native wire contracts.
        return QuantityDraft.model_validate(data)
    images = {b.image_id: b for b in bindings}
    entries = [*data.get("operands", []), *data.get("items", [])]
    if data.get("absence") is not None:
        entries.append(data["absence"])
    entries.extend(item for group in data.get("groups", []) for item in group["items"])
    for entry in entries:
        if images:
            ids = entry.get("image_ids", [])
            if not ids or any(key not in images for key in ids):
                raise ValueError("COLLECTION_IMAGE_ID_INVALID")
            entry["page"] = images[ids[0]].physical_page
        else:
            refs = entry.get("source_ranges", [])
            if not refs or any(ref["support_id"] not in units for ref in refs):
                raise ValueError("COLLECTION_SOURCE_ID_INVALID")
            unit = units[refs[0]["support_id"]]
            entry["page"] = (
                unit.page_number
                if unit.page_number == (unit.page_end or unit.page_number)
                else None
            )
    return QuantityDraft.model_validate(data)


def review_contract(draft: QuantityDraft) -> type[QuantityAssessment]:
    """A reviewer can object only to slots present in this operation."""
    target = {"list": "item", "count": "group"}.get(draft.mode, "operand")
    count = (
        len(draft.items)
        if target == "item"
        else (len(draft.groups) if target == "group" else len(draft.operands))
    )
    issue = create_model(
        f"{draft.mode.title()}InputIssue",
        __base__=QuantityIssue,
        target=(Literal[target], ...),
        index=(int, Field(ge=0, le=max(0, count - 1))),
    )
    if draft.absence is not None:
        issue = create_model(
            "AbsenceIssue",
            __base__=QuantityIssue,
            target=(Literal["absence"], "absence"),
            index=(Literal[None], None),
        )
    operation_issue = create_model(
        "OperationIssue",
        __base__=QuantityIssue,
        target=(Literal["operation"], "operation"),
        index=(Literal[None], None),
    )
    fields: dict[str, Any] = {
        "issues": (
            GenericAlias(list, issue | operation_issue),
            Field(default_factory=cast(Any, list), max_length=10),
        )
    }
    return create_model(f"Review{draft.mode.title()}", __base__=QuantityAssessment, **fields)
