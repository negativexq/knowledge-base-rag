"""Verified counts behind answers that count listed things.

"13 geographic market names are listed" states a number no unit prints: the
units list the names. The model copies each counted item from the cited
units; this module checks, without a model, that every item is printed there
and none is counted twice. The count is the number of items, so a verified
count is evidence for that number (and a calculation may use it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EDGE_PUNCTUATION = " \t\n\"'“”‘’.,;:!?-–—*"


@dataclass(frozen=True)
class Count:
    items: tuple[str, ...]

    @property
    def result(self) -> int:
        return len(self.items)

    def fact(self) -> str:
        """The verified count as a line of evidence."""
        return f"count of listed items = {self.result}"


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _item_key(item: str) -> str:
    return _normalized(item).strip(_EDGE_PUNCTUATION)


def verify_count(count: Count, support_texts: list[str]) -> list[str]:
    """Failure codes for a count; empty when it is verified."""
    keys = [_item_key(item) for item in count.items]
    if not keys or not all(re.search(r"\w", key) for key in keys):
        return ["COUNT_EMPTY"]
    if len(set(keys)) != len(keys):
        return ["COUNT_ITEM_DUPLICATE"]
    support = _normalized(" ".join(support_texts))
    if any(key not in support for key in keys):
        return ["COUNT_ITEM_NOT_IN_SUPPORT"]
    return []


def unit_count_facts(count: Count, unit_texts: list[str]) -> list[str]:
    """The verified count split by cited unit ("4 in one list, 3 in the
    other"), as lines of evidence; none unless each item is printed in exactly
    one of the units, so the split is the units' own."""
    keys = [_item_key(item) for item in count.items]
    units = [_normalized(text) for text in unit_texts]
    homes = [[index for index, unit in enumerate(units) if key in unit] for key in keys]
    if len(units) < 2 or any(len(home) != 1 for home in homes):
        return []
    per_unit = [sum(home[0] == index for home in homes) for index in range(len(units))]
    return [f"count of listed items in one cited unit = {n}" for n in per_unit if n]
