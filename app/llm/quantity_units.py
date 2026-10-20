"""Application-owned scale algebra for arithmetic over source-printed operands."""

from __future__ import annotations

import ast
import re
from decimal import Decimal, localcontext

from app.llm.calculation import numeric_function
from app.llm.quantity_state import (
    NumberScale,
    QuantityArithmeticConversion,
    QuantityDraft,
    QuantityNumberReceipt,
    QuantityNumericOperand,
)
from app.llm.research_state import decimal_value

SCALE_PATTERNS: list[tuple[str, NumberScale]] = [
    (r"\b(?:billions?)\b", "1000000000"),
    (r"\b(?:crores?)\b", "10000000"),
    (r"\b(?:millions?)\b", "1000000"),
    (r"\b(?:lacs?|lakhs?)\b", "100000"),
    (r"\b(?:thousands?)\b|\b000(?:['’]?s)?\b", "1000"),
]


def scaled_arithmetic(draft: QuantityDraft) -> bool:
    if draft.mode != "arithmetic":
        return False
    if any(isinstance(o, QuantityNumericOperand) and o.source_scale != "1" for o in draft.operands):
        return True
    try:
        return any(
            isinstance(n, ast.Call) for n in ast.walk(ast.parse(draft.expression, mode="eval"))
        )
    except SyntaxError:
        return False


def unit_scale(unit: str) -> NumberScale:
    found = [scale for pattern, scale in SCALE_PATTERNS if re.search(pattern, unit, re.I)]
    if len(found) > 1:
        raise ValueError("NUMERIC_SCALE_AMBIGUOUS")
    return found[0] if found else "1"


def unit_identity(unit: str) -> tuple[str, Decimal]:
    """Normalize scale wording, not currency exchange or unknown unit identities."""
    scale = unit_scale(unit)
    base = unit.casefold().strip()
    for pattern, _ in SCALE_PATTERNS:
        base = re.sub(pattern, " ", base, flags=re.I)
    base = re.sub(r"\b(?:in|of)\b", " ", base)
    base = " ".join(base.strip(" ()[]").split())
    aliases = {
        "rupees": "rupee",
        "rupee": "rupee",
        "rs.": "rupee",
        "rs": "rupee",
        "u.s. dollars": "usd",
        "us dollars": "usd",
        "us dollar": "usd",
        "u.s. dollar": "usd",
        "percentage": "",
        "percent": "",
        "%": "",
        "percentage points": "",
        "ratio": "",
        "times": "",
    }
    return aliases.get(base, base), Decimal(scale)


def arithmetic_conversion(
    draft: QuantityDraft, numbers: list[QuantityNumberReceipt]
) -> QuantityArithmeticConversion | None:
    """Expand source-to-base factors and verify dimensions before output conversion.

    Formula literals retain their mathematical role (including percent multipliers).
    Only application-added factors represent unit conversion. Original displays and
    the named-input formula remain immutable and independently reviewed.
    """
    if not scaled_arithmetic(draft):
        return None
    if any(n.value_status != "readable" or n.errors for n in numbers):
        return None
    try:
        tree = ast.parse(draft.expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("QUANTITY_EXPRESSION_INVALID") from exc
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("QUANTITY_EXPRESSION_TOO_COMPLEX")
    by_name = {}
    factors = {}
    dimensions = {}
    for operand, number in zip(draft.operands, numbers, strict=True):
        identity, printed_scale = unit_identity(operand.unit)
        source_scale = Decimal(number.source_scale)
        if printed_scale != 1 and printed_scale != source_scale:
            raise ValueError("NUMERIC_SOURCE_SCALE_MISMATCH")
        if number.canonical_value is None:
            raise ValueError("QUANTITY_NUMERIC_INPUT_UNRESOLVED")
        factors[operand.name] = format(source_scale, "f")
        dimensions[operand.name] = identity
        raw = format(decimal_value(number.canonical_value), "f")
        by_name[operand.name] = (
            raw if source_scale == 1 else f"({raw} * {source_scale})",
            identity,
        )
    used = set()

    def render(node: ast.AST) -> tuple[str, str]:
        if isinstance(node, ast.Expression):
            return render(node.body)
        if isinstance(node, ast.Name):
            if node.id not in by_name:
                raise ValueError("QUANTITY_UNKNOWN_OPERAND")
            used.add(node.id)
            return by_name[node.id]
        if isinstance(node, ast.Call):
            name = numeric_function(node)
            arguments = [render(arg) for arg in node.args]
            if len({dimension for _, dimension in arguments}) != 1:
                raise ValueError("ARITHMETIC_INCOMPATIBLE_UNITS")
            return f"{name}({','.join(text for text, _ in arguments)})", arguments[0][1]
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            text = ast.get_source_segment(draft.expression, node) or str(node.value)
            decimal_value(text)
            return text, ""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            text, dimension = render(node.operand)
            return f"({'-' if isinstance(node.op, ast.USub) else '+'}{text})", dimension
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, ast.Add | ast.Sub | ast.Mult | ast.Div
        ):
            left, ld = render(node.left)
            right, rd = render(node.right)
            if isinstance(node.op, ast.Add | ast.Sub):
                if ld != rd:
                    raise ValueError("ARITHMETIC_INCOMPATIBLE_UNITS")
                dimension = ld
                symbol = "+" if isinstance(node.op, ast.Add) else "-"
            elif isinstance(node.op, ast.Mult):
                if ld and rd:
                    raise ValueError("ARITHMETIC_COMPOUND_UNITS_UNSUPPORTED")
                dimension, symbol = ld or rd, "*"
            else:
                if ld == rd:
                    dimension = ""
                elif not rd:
                    dimension = ld
                else:
                    raise ValueError("ARITHMETIC_INCOMPATIBLE_UNITS")
                symbol = "/"
            return f"({left} {symbol} {right})", dimension
        raise ValueError("ARITHMETIC_UNIT_OPERATION_UNSUPPORTED")

    expression, dimension = render(tree)
    if used != set(by_name):
        raise ValueError("QUANTITY_UNUSED_OPERAND")
    target, output_scale = unit_identity(draft.result_unit)
    if not draft.result_unit.strip() and dimension:
        # Unspecified output preserves a common displayed source scale, rather
        # than silently changing a bare-number convention.
        scales = {n.source_scale for n in numbers}
        if len(scales) != 1:
            raise ValueError("ARITHMETIC_OUTPUT_UNIT_REQUIRED")
        target, output_scale = dimension, Decimal(next(iter(scales)))
    elif not target and output_scale != 1:
        target = dimension  # "in millions" with an otherwise established identity
    if target != dimension:
        raise ValueError("ARITHMETIC_OUTPUT_UNIT_MISMATCH")
    if output_scale != 1:
        expression = f"({expression} / {output_scale})"
    return QuantityArithmeticConversion(
        source_formula=draft.expression,
        source_factors=factors,
        source_units=dimensions,
        output_unit=draft.result_unit,
        output_scale=format(output_scale, "f"),
        result_dimension=dimension,
        expression=expression,
    )


def normalize_arithmetic(
    draft: QuantityDraft, numbers: list[QuantityNumberReceipt]
) -> list[QuantityNumberReceipt]:
    if not scaled_arithmetic(draft):
        return numbers
    try:
        plan = arithmetic_conversion(draft, numbers)
        if plan is None:
            return numbers
        result = []
        for operand, number in zip(draft.operands, numbers, strict=True):
            assert number.canonical_value is not None
            with localcontext() as context:
                context.prec = 128
                base = decimal_value(number.canonical_value) * Decimal(number.source_scale)
                decimal_value(format(base, "f"))
            result.append(
                number.model_copy(
                    update={
                        "output_value": format(base, "f"),
                        "output_scale": "1",
                        "output_unit": plan.source_units[operand.name],
                    }
                )
            )
        return result
    except (ValueError, ArithmeticError) as exc:
        return [
            n.model_copy(update={"value_status": "invalid", "errors": [str(exc)]}) for n in numbers
        ]
