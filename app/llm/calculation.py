"""Verified calculations behind derived answer numbers.

A derived answer states a number the evidence does not print, computed from
numbers it does print ("41% do not go online" from "59% go online"). The
model writes the arithmetic; this module checks it without a model: the
expression is parsed with a whitelist (numbers, + - * /, parentheses), every
number in it must appear in the cited support units, the result is
recomputed and compared, and the answer text must state the result.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

# Numbers an expression may use without a citation: the whole of a
# percentage, for remainders such as 100 - 59.
ALLOWED_CONSTANTS = frozenset({100.0})
# A stated result matches when it equals the recomputed value rounded to the
# stated precision, or is within this relative tolerance.
RESULT_TOLERANCE = 0.005
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")
_SIGNED_NUMBER = re.compile(r"(-\s*)?(\d[\d,]*(?:\.\d+)?|\.\d+)")
# A negative result may be stated as its magnitude in an answer that says it
# is a decrease ("lower by 155.98" for 1767.80 - 1923.78 = -155.98).
_DECREASE = re.compile(
    r"\b(?:lower|less|fewer|smaller|decreas\w*|declin\w*|fell|fall\w*|dropp?\w*|down|"
    r"reduc\w*|below|short)\b",
    re.IGNORECASE,
)
# A number followed by "%" or one word (a unit such as "percent" or "crore").
_NUMBER_WITH_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s*%|\s+[^\W\d_]+)?")
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


@dataclass(frozen=True)
class Calculation:
    expression: str
    result: str

    def fact(self, text: str | None = None) -> str:
        """The verified calculation as a line of evidence. With the answer
        text, the result is written as the answer states it, unit included
        ("41%"), so a typed value check compares like with like."""
        stated = _signed_numbers(self.result)
        if text and stated:
            decimals = _decimals(self.result)
            for match in _NUMBER_WITH_UNIT.finditer(text):
                if _matches(float(match.group(1).replace(",", "")), stated[0], decimals):
                    return f"{self.expression} = {match.group(0).strip()}"
        return f"{self.expression} = {self.result}"


def numbers_in(text: str) -> list[float]:
    """Numbers printed in text; thousands separators are ignored."""
    return [float(match.replace(",", "")) for match in _NUMBER.findall(text)]


def _signed_numbers(text: str) -> list[float]:
    """Numbers with their minus sign, for a calculation's result."""
    return [
        (-1 if sign else 1) * float(digits.replace(",", ""))
        for sign, digits in _SIGNED_NUMBER.findall(text)
    ]


def _literals(node: ast.AST) -> list[float]:
    if isinstance(node, ast.Expression):
        return _literals(node.body)
    if isinstance(node, ast.BinOp):
        return _literals(node.left) + _literals(node.right)
    if isinstance(node, ast.UnaryOp):
        return _literals(node.operand)
    if isinstance(node, ast.Constant):
        return [float(node.value)]
    return []


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        value = _evaluate(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("division by zero")
        return float(_OPERATORS[type(node.op)](left, right))
    raise ValueError("only numbers, + - * / and parentheses are allowed")


def _parse(expression: str) -> ast.Expression:
    if not expression.strip():
        raise ValueError("empty expression")
    try:
        return ast.parse(expression.replace(",", ""), mode="eval")
    except SyntaxError as exc:
        raise ValueError("unparseable expression") from exc


def evaluate_expression(expression: str) -> float:
    return _evaluate(_parse(expression))


def _decimals(text: str) -> int:
    match = _NUMBER.search(text)
    if match is None or "." not in match.group():
        return 0
    return len(match.group().split(".")[1])


def _matches(value: float, stated: float, decimals: int) -> bool:
    if round(value, decimals) == round(stated, decimals):
        return True
    return abs(value - stated) <= RESULT_TOLERANCE * max(abs(stated), 1e-9)


def verify_calculation(calculation: Calculation, support_texts: list[str], text: str) -> list[str]:
    """Failure codes for a calculation; empty when it is verified."""
    try:
        tree = _parse(calculation.expression)
        value = _evaluate(tree)
    except ValueError:
        return ["CALCULATION_UNPARSEABLE"]
    cited = {number for support in support_texts for number in numbers_in(support)}
    if any(
        operand not in cited and operand not in ALLOWED_CONSTANTS for operand in _literals(tree)
    ):
        return ["CALCULATION_OPERAND_UNSUPPORTED"]
    stated = _signed_numbers(calculation.result)
    if not stated:
        return ["CALCULATION_UNPARSEABLE"]
    decimals = _decimals(calculation.result)
    if not _matches(value, stated[0], decimals):
        return ["CALCULATION_RESULT_MISMATCH"]
    written = numbers_in(text)
    if stated[0] < 0 and _DECREASE.search(text):
        written += [-number for number in written]
    if not any(_matches(stated[0], number, decimals) for number in written):
        return ["CALCULATION_RESULT_NOT_IN_ANSWER"]
    return []
