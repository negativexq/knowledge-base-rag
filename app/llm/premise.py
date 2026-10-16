"""Deterministic question-premise checks.

A question can carry a constraint that the documents contradict ("the plan
revised in May 2018" when every source says 2016). A model answering from
nearby content then states a wrong fact with a valid citation, which the
support-ID validator cannot see because the cited unit does support the
answer text. The check here looks only at the question's explicit years:
they are unambiguous, language independent, and on the Evaluation Corpus v2
golden set every answerable question's years appear in its evidence.
"""

import re

_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def missing_question_years(question: str, evidence_texts: list[str]) -> list[str]:
    """Years named in the question that appear in none of the evidence
    texts, in question order and without duplicates."""
    evidence = "\n".join(evidence_texts)
    missing: list[str] = []
    for year in _YEAR.findall(question):
        if year not in missing and not re.search(rf"(?<!\d){year}(?!\d)", evidence):
            missing.append(year)
    return missing


# Month names by number, English (full and short) and Turkish.
_MONTHS = {
    1: ("january", "jan", "ocak"),
    2: ("february", "feb", "şubat", "subat"),
    3: ("march", "mar", "mart"),
    4: ("april", "apr", "nisan"),
    5: ("may", "mayıs", "mayis"),
    6: ("june", "jun", "haziran"),
    7: ("july", "jul", "temmuz"),
    8: ("august", "aug", "ağustos", "agustos"),
    9: ("september", "sep", "sept", "eylül", "eylul"),
    10: ("october", "oct", "ekim"),
    11: ("november", "nov", "kasım", "kasim"),
    12: ("december", "dec", "aralık", "aralik"),
}
_MONTH_NUMBER = {name: number for number, names in _MONTHS.items() for name in names}
_MONTH_NAME = "|".join(sorted(_MONTH_NUMBER, key=len, reverse=True))
_QUESTION_DATE = re.compile(
    rf"(?<!\w)({_MONTH_NAME})\.?,?\s+((?:19|20)\d{{2}})(?!\d)", re.IGNORECASE
)


def _date_in(evidence: str, month: int, year: str) -> bool:
    names = "|".join(_MONTHS[month])
    patterns = (
        # "May 2018", "May, 2018", "May 2, 2018", "2 May 2018"
        rf"(?<!\w)(?:{names})\.?,?\s+(?:\d{{1,2}}(?:st|nd|rd|th)?,?\s+)?{year}(?!\d)",
        rf"(?<!\d){year}[-/.]0?{month}(?!\d)",
        rf"(?<!\d)0?{month}[-/.]{year}(?!\d)",
    )
    return any(re.search(pattern, evidence, re.IGNORECASE) for pattern in patterns)


def missing_question_dates(question: str, evidence_texts: list[str]) -> list[str]:
    """Month-and-year dates named in the question ("May 2018") that no
    evidence text states as a date, in question order. A year that appears
    only elsewhere in the evidence does not confirm "May 2018"."""
    evidence = "\n".join(evidence_texts)
    missing: list[str] = []
    for match in _QUESTION_DATE.finditer(question):
        month_text, year = match.group(1), match.group(2)
        label = f"{month_text} {year}"
        if label in missing:
            continue
        if not _date_in(evidence, _MONTH_NUMBER[month_text.lower()], year):
            missing.append(label)
    return missing
