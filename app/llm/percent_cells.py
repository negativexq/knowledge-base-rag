"""Survey-table cells restated as the percentages they are.

Survey reports print a table of percentages as bare cells under a "% of ..."
header, often with significance letters glued on: "$75,000+ 92 42",
"College graduate (n=537) 87ab". An answer that says "42%" or "87%" then
meets a bare NUMBER, or nothing. In a unit that prints no "%" at all, a cell
from 0 to 100 that stands alone (the line ends, or a "|" or another number
follows) is restated as an evidence line ("table cell 87ab = 87%"). So is a
unit whose header declares percentages ("the % who use Twitter", "% of") even
when some of its cells print "%". A number followed by a word ("42
employees") or ending an age range ("18-29") is not a cell; any other unit
that prints percentages is never restated.
"""

from __future__ import annotations

import re

# A cell: not glued to a word, "$", "=" or a digit group before it; optional
# significance letters (a-e, increasing); then the line end, "|" or a number.
_CELL = re.compile(
    r"(?<![\w$=.,-])(?P<value>\d{1,3}(?:\.\d+)?)(?P<letters>[a-e]{1,5})?(?![\w.,])"
    r"(?=\s*(?:$|\||\d))",
    re.MULTILINE,
)


# A header saying the table's numbers are percentages.
_PERCENT_HEADER = re.compile(r"%\s+(?:who|of)\b|\(%\)|\bpercent(?:age)?s?\b", re.IGNORECASE)


def _significance_letters(letters: str | None) -> bool:
    return not letters or list(letters) == sorted(set(letters))


def percent_cell_facts(support_texts: list[str]) -> list[str]:
    """Each standalone 0-100 cell of the units that print no "%" or declare
    percentages in a header, as a percentage."""
    facts: list[str] = []
    for text in support_texts:
        if "%" in text and not _PERCENT_HEADER.search(text):
            continue
        for match in _CELL.finditer(text):
            value = match.group("value")
            if float(value) <= 100 and _significance_letters(match.group("letters")):
                facts.append(f"table cell {match.group(0)} = {value}%")
    return facts
