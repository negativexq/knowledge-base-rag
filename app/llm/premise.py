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
