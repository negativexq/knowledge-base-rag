"""Dates restated as ISO for answers that write YYYY-MM-DD.

A question may ask for dates in ISO form while the document prints "24 March
2015". A date with a month name is unambiguous, so each one in the cited
units is restated as an evidence line ("24 March 2015 = 2015-03-24"), the way
verified calculations and counts are. Numeric dates ("03/04/2015") are
ambiguous between day-first and month-first and are never restated.
"""

from __future__ import annotations

import datetime
import re

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH = (
    r"(?P<month>(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?)"
)
_DAY_FIRST = re.compile(rf"\b(?P<day>\d{{1,2}})\s+{_MONTH}\s+(?P<year>\d{{4}})\b", re.IGNORECASE)
_MONTH_FIRST = re.compile(
    rf"\b{_MONTH}\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b", re.IGNORECASE
)
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _iso(match: re.Match[str]) -> str | None:
    month = _MONTHS[match.group("month")[:3].casefold()]
    try:
        return datetime.date(int(match.group("year")), month, int(match.group("day"))).isoformat()
    except ValueError:
        return None


def iso_date_facts(support_texts: list[str]) -> list[str]:
    """Each month-name date in the texts, restated as ISO, in text order."""
    facts: list[str] = []
    for text in support_texts:
        matches = sorted(
            [*_DAY_FIRST.finditer(text), *_MONTH_FIRST.finditer(text)],
            key=lambda match: match.start(),
        )
        for match in matches:
            iso = _iso(match)
            if iso:
                facts.append(f"{match.group(0)} = {iso}")
    return facts
