"""Explicit numeric notation, source scale and reviewed output conventions."""

from __future__ import annotations

import re
from decimal import Decimal, DecimalException, localcontext
from typing import Literal, get_args

from app.llm.quantity_state import (
    NumberFormat,
    QuantityAssessment,
    QuantityDraft,
    QuantityNumberReceipt,
    QuantityNumericOperand,
    QuantityReadOperand,
)
from app.llm.quantity_units import normalize_arithmetic, unit_scale
from app.llm.research_state import decimal_value


def read_order(draft: QuantityDraft, inputs: list[QuantityNumberReceipt]) -> list[int]:
    """Stable numeric ordering over checked converted values, before rounding."""
    indexes = list(range(len(inputs)))
    if draft.output_order == "source":
        return indexes
    if any(n.value_status != "readable" or n.errors or n.output_value is None for n in inputs):
        raise ValueError("QUANTITY_NUMERIC_INPUT_UNRESOLVED")
    if len({(n.output_unit.strip().casefold(), decimal_value(n.output_scale)) for n in inputs}) > 1:
        raise ValueError("NUMERIC_ORDER_INCOMPATIBLE_UNITS")
    return sorted(
        indexes,
        key=lambda i: decimal_value(inputs[i].output_value),
        reverse=draft.output_order == "descending",
    )


def source_decimal(value: str, notation: NumberFormat) -> Decimal:
    """No locale inference, missing-as-zero coercion, or implicit absolute value."""
    text = value.strip().replace("−", "-")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if "(" in text or ")" in text or (negative and text.startswith(("+", "-"))):
        raise ValueError("NUMERIC_SIGN_INVALID")
    if notation == "canonical":
        pattern = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
        normalized = text
    elif notation == "decimal_point":
        pattern = r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
        normalized = text.replace(",", "")
    elif notation == "decimal_comma":
        pattern = r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?"
        normalized = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace("\u00a0", " ").replace("\u202f", " ")
        pattern = r"[+-]?(?:\d+|\d{1,3}(?: \d{3})+)(?:\.\d+)?"
        normalized = text.replace(" ", "")
    if len(value) > 100 or not re.fullmatch(pattern, text):
        raise ValueError("NUMERIC_NOTATION_INVALID")
    return decimal_value(("-" if negative else "") + normalized)


def normalize_inputs(draft: QuantityDraft) -> list[QuantityNumberReceipt]:
    receipts = []
    for operand in draft.operands:
        typed = operand if isinstance(operand, QuantityNumericOperand) else None
        status = typed.value_status if typed else "readable"
        source_scale = typed.source_scale if typed else "1"
        read = (
            operand if isinstance(operand, QuantityReadOperand) and draft.mode == "read" else None
        )
        output_scale = read.output_scale if read and read.output_unit else source_scale
        output_unit = (read.output_unit or operand.unit) if read else operand.unit
        sign: Literal["signed", "magnitude"] = read.sign_convention if read else "signed"
        # Retaining the exact same displayed unit needs no scale conversion.
        # Resolve default multipliers from its explicit unit label in this case;
        # contradictory or cross-unit declarations must still fail below.
        if read and source_scale == output_scale == "1" and output_unit == operand.unit:
            try:
                source_scale = output_scale = unit_scale(operand.unit)
            except ValueError:
                pass  # Persist an invalid receipt in the checked path below.
        base = QuantityNumberReceipt(
            name=operand.name,
            source_value=operand.value,
            source_scale=source_scale,
            output_scale=output_scale,
            output_unit=output_unit,
            sign_convention=sign,
            value_status=status,
        )
        if status != "readable":
            receipts.append(base)
            continue
        try:
            if operand.value is None:
                raise ValueError("NUMERIC_VALUE_MISSING")
            value = source_decimal(operand.value, typed.number_format if typed else "canonical")
            # Scale/sign presentation is only applied to scalar reads. Arithmetic
            # keeps numbers in their checked source units and has its own formula.
            if read:
                if unit_scale(operand.unit) != source_scale:
                    raise ValueError("NUMERIC_SOURCE_SCALE_MISMATCH")
                if unit_scale(output_unit) != output_scale:
                    raise ValueError("NUMERIC_OUTPUT_SCALE_MISMATCH")
                with localcontext() as context:
                    context.prec = 128
                    output = value * Decimal(source_scale) / Decimal(output_scale)
                    if sign == "magnitude":
                        output = abs(output)
                    output_text = format(output, "f")
                decimal_value(output_text)
            else:
                output_text = format(value, "f")
            receipts.append(
                base.model_copy(
                    update={"canonical_value": format(value, "f"), "output_value": output_text}
                )
            )
        except (ValueError, DecimalException) as exc:
            receipts.append(
                base.model_copy(update={"value_status": "invalid", "errors": [str(exc)]})
            )
    return normalize_arithmetic(draft, receipts)


def apply_notation_corrections(draft: QuantityDraft, review: QuantityAssessment) -> QuantityDraft:
    """A source reviewer may correct notation metadata, never the printed value."""
    operands = list(draft.operands)
    seen: set[int] = set()
    for correction in review.notation_corrections:
        if correction.index in seen or correction.index >= len(operands):
            raise ValueError("NUMERIC_NOTATION_CORRECTION_INVALID")
        seen.add(correction.index)
        old = operands[correction.index]
        if not isinstance(old, QuantityNumericOperand) or old.value is None:
            raise ValueError("NUMERIC_NOTATION_CORRECTION_INVALID")
        # It is not permissible to reinterpret an already valid number (e.g.
        # 1,234 between decimal-comma and decimal-point conventions).
        try:
            original = source_decimal(old.value, old.number_format)
        except ValueError:
            original = None
        try:
            proposed = source_decimal(old.value, correction.number_format)
        except ValueError:
            if original is not None:
                # An unusable metadata suggestion must not destroy a valid
                # transcription or prevent independent source-context repair.
                continue
            raise
        if original is not None and original != proposed:
            raise ValueError("NUMERIC_NOTATION_ALREADY_VALID")
        operands[correction.index] = old.model_copy(
            update={"number_format": correction.number_format}
        )
    return draft.model_copy(update={"operands": operands})


def notation_options(draft: QuantityDraft) -> dict[int, list[NumberFormat]]:
    """Syntax options, never a locale guess or permission to change a valid value."""
    options = {}
    for index, operand in enumerate(draft.operands):
        if not isinstance(operand, QuantityNumericOperand) or operand.value_status != "readable":
            continue
        if operand.value is None:
            continue
        try:
            original = source_decimal(operand.value, operand.number_format)
        except ValueError:
            original = None
        formats = []
        for notation in get_args(NumberFormat):
            try:
                proposed = source_decimal(operand.value, notation)
            except ValueError:
                continue
            if original is None or proposed == original:
                formats.append(notation)
        if formats:
            options[index] = formats
    return options
