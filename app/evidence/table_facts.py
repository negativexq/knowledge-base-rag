"""Facts read from the table rows a support unit prints.

The PDF parser prints a table as a header line ("Table: | 2021 | 2020") and
one line per row that repeats each column header next to its value
("Long-term debt | 2021: 6,692 | 2020: 7,514"). Each value cell of such a
row is a fact: the value, the row's label and the cell's column, read from
the same line, so the three belong together. A row printed without column
headers takes them from the table's header line by position, only when both
have the same number of cells. A value whose row label or column cannot be
read, or a cell that prints more than one number, yields no fact: its
numbers are kept as unresolved, so a caller can refuse rather than guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.calculation import numbers_in

_HEADER = "Table:"
_TEXT = re.compile(r"[^\W\d_]{2,}")
_SCALE = re.compile(r"\bin\s+(thousands|millions|billions)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Fact:
    value: float
    row: str
    column: str
    # "thousands", "millions" or "billions" when the table's header says so.
    scale: str | None


@dataclass(frozen=True)
class UnitFacts:
    facts: tuple[Fact, ...] = ()
    # Numbers printed in table value cells that yielded no fact.
    unresolved: frozenset[float] = frozenset()


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.split("|")]


def header_line(text: str) -> str | None:
    """The first table header line in a text, or None."""
    return next((line for line in text.splitlines() if line.startswith(_HEADER)), None)


def _scale(header: str | None) -> str | None:
    match = _SCALE.search(header or "")
    return match.group(1).casefold() if match else None


def _row(line: str, header: str | None, scale: str | None) -> tuple[list[Fact], set[float]]:
    cells = _cells(line)
    names = _cells(header.removeprefix(_HEADER)) if header else []
    facts: list[Fact] = []
    unresolved: set[float] = set()
    row: str | None = None
    for index, cell in enumerate(cells):
        name, _, value = cell.rpartition(": ")
        numbers = numbers_in(value)
        if _TEXT.search(value):
            # A text cell names the row (a line may print several rows).
            row = cell
            continue
        if not numbers:
            continue
        column = name or (names[index] if len(names) == len(cells) else "")
        if row is None or not column or len(numbers) != 1:
            unresolved.update(numbers)
            continue
        facts.append(Fact(numbers[0], row, column, scale))
    return facts, unresolved


def unit_facts(text: str, header: str | None = None) -> UnitFacts:
    """The facts of the table rows in a unit's text. ``header`` is the table's
    header line when the unit does not print it (a row split from its table);
    a header line in the text replaces it for the lines after it."""
    facts: list[Fact] = []
    unresolved: set[float] = set()
    for line in text.splitlines():
        if line.startswith(_HEADER):
            header = line
            continue
        if "|" not in line:
            continue
        row_facts, row_unresolved = _row(line, header, _scale(header))
        facts.extend(row_facts)
        unresolved.update(row_unresolved)
    return UnitFacts(tuple(facts), frozenset(unresolved))
