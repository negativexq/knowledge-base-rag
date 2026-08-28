"""Offline, deterministic refinement helpers for Phase 7 evaluation.

This module is deliberately provider-free.  It consumes authored facts and
already persisted generation output; it must never be used as a runtime gate.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import date
from typing import Any

MAX_FACTS = 8

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twelve": 12, "fourteen": 14, "fifteen": 15, "thirty": 30,
    "forty-eight": 48, "forty eight": 48,
    "sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5,
    "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on iki": 12,
    "on dört": 14, "on beş": 15, "otuz": 30, "kırk sekiz": 48,
}
_UNIT_ALIASES = {
    "calendar day": "day", "calendar days": "day", "takvim gün": "day",
    "takvim günleri": "day", "takvim günlük": "day", "gün": "day",
    "days": "day", "day": "day",
    "business hour": "business_hour", "business hours": "business_hour",
    "working hours": "business_hour", "iş saati": "business_hour",
    "iş saatleri": "business_hour", "hours": "hour", "hour": "hour",
    "saat": "hour", "saatleri": "hour",
    "business day": "business_day", "business days": "business_day",
    "iş günü": "business_day", "iş günleri": "business_day",
    "percent": "percent", "percentage": "percent", "%": "percent",
}
_TOKEN_ALIASES = {
    "calendar": "calendar", "takvim": "calendar", "days": "day", "day": "day",
    "gün": "day", "günlük": "day", "business": "business", "working": "business",
    "iş": "business", "hours": "hour", "hour": "hour", "saat": "hour",
    "standard": "standard", "standart": "standard", "critical": "critical",
    "kritik": "critical", "cancel": "cancel", "cancellation": "cancel",
    "iptal": "cancel", "renewal": "renewal", "yenileme": "renewal",
    "direct-sale": "directsale", "direct": "directsale", "doğrudan": "directsale",
    "sale": "sale", "satış": "sale", "premium": "premium",
}
_GENERIC = {
    "a", "an", "and", "are", "be", "by", "days", "from", "in", "is", "it",
    "of", "on", "or", "the", "to", "with", "for", "this", "that", "must",
    "ve", "bir", "ile", "için", "olan", "olarak", "gün", "günlük",
}
_NEGATION = re.compile(
    r"\b(?:not|never|no|without|değil|hayır|olmaz|geçmez|geçerli değildir)\b", re.I
)
_NUMERIC = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?%?(?![\w])")
_VERSION = re.compile(r"(?<![\w])v?\d+(?:\.\d+)+(?![\w])", re.I)
_DATE = re.compile(
    r"(?<!\w)(?:(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|"
    r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}))(?!\w)"
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12, "ocak": 1, "şubat": 2, "subat": 2,
    "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}


def normalize_text(value: str) -> str:
    """Normalize accents/Turkish casing and punctuation without fuzzy matching."""
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ı", "i").replace("’", "'")
    return re.sub(r"[^\w%]+", " ", value, flags=re.UNICODE).strip()


def _number_values(text: str) -> set[float]:
    normalized = normalize_text(text)
    values = {
        float(value.replace(",", ".").replace("%", ""))
        for value in _NUMERIC.findall(normalized)
    }
    for phrase, value in sorted(_NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        if normalize_text(phrase) in normalized:
            values.add(float(value))
    return values


def _number_candidates(text: str) -> list[tuple[int, int, float]]:
    normalized = normalize_text(text)
    candidates = [
        (
            match.start(),
            match.end(),
            float(match.group().replace(",", ".").replace("%", "")),
        )
        for match in _NUMERIC.finditer(normalized)
    ]
    for phrase, value in sorted(_NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        spelling = normalize_text(phrase)
        candidates.extend(
            (match.start(), match.end(), float(value))
            for match in re.finditer(rf"(?<!\w){re.escape(spelling)}(?!\w)", normalized)
        )
    return candidates


def _duration_signatures(text: str) -> list[tuple[float, str]]:
    normalized = normalize_text(text)
    found: list[tuple[float, str]] = []
    units = sorted(_UNIT_ALIASES.items(), key=lambda item: -len(item[0]))
    for spelling, unit in units:
        unit_text = normalize_text(spelling)
        for match in re.finditer(re.escape(unit_text), normalized):
            before = normalized[max(0, match.start() - 24):match.start()]
            after = normalized[match.end():match.end() + 24]
            before_candidates = _number_candidates(before)
            after_candidates = _number_candidates(after)
            if unit == "percent" and after_candidates:
                candidate = min(after_candidates, key=lambda item: (item[0], -(item[1] - item[0])))
                found.append((candidate[2], unit))
                continue
            if before_candidates:
                candidate = max(before_candidates, key=lambda item: (item[1], item[1] - item[0]))
                found.append((candidate[2], unit))
                continue
            if after_candidates:
                candidate = min(after_candidates, key=lambda item: (item[0], -(item[1] - item[0])))
                found.append((candidate[2], unit))
    return found


def _duration_signature(text: str) -> tuple[float, str] | None:
    signatures = _duration_signatures(text)
    return signatures[0] if signatures else None


def _version_signature(text: str) -> set[str]:
    return {match.lower().lstrip("v") for match in _VERSION.findall(normalize_text(text))}


def _date_signature(text: str) -> set[str]:
    raw = text.casefold()
    normalized = normalize_text(text)
    dates: set[str] = set()
    for match in _DATE.finditer(raw):
        if match.group(1):
            year, month, day = (int(match.group(index)) for index in (1, 2, 3))
        else:
            day, month, year = (int(match.group(index)) for index in (4, 5, 6))
        try:
            dates.add(date(year, month, day).isoformat())
        except ValueError:
            continue
    for month_name, month in _MONTHS.items():
        pattern = rf"(?<!\w)(\d{{1,2}})\s+{re.escape(normalize_text(month_name))}\s+(\d{{4}})(?!\w)"
        for match in re.finditer(pattern, normalized):
            try:
                dates.add(date(int(match.group(2)), month, int(match.group(1))).isoformat())
            except ValueError:
                continue
    return dates


def _percent_signature(text: str) -> set[float]:
    normalized = normalize_text(text)
    values = _number_values(normalized)
    if (
        "%" in text
        or "percent" in normalized
        or "percentage" in normalized
        or "indirim" in normalized
    ):
        return values
    return set()


def _contradicts(expected: str, answer: str) -> bool:
    """Reject a local negation of a matched authored fact."""
    expected_n = normalize_text(expected)
    answer_n = normalize_text(answer)
    if not expected_n:
        return False
    for match in re.finditer(re.escape(expected_n), answer_n):
        if _NEGATION.search(answer_n[max(0, match.start() - 32):match.start()]):
            return True
    return False


def _token_signature(text: str) -> set[str]:
    tokens = set(normalize_text(text).split())
    return {_TOKEN_ALIASES.get(token, token) for token in tokens if token not in _GENERIC}


def match_authored_fact(expected: str, answer: str) -> dict[str, Any]:
    """Match one authored fact conservatively and explain the decision."""
    if not answer:
        return {"matched": False, "reason": "empty_answer"}
    if _contradicts(expected, answer):
        return {"matched": False, "reason": "negated_or_contradicted"}
    expected_duration = _duration_signature(expected)
    answer_duration = _duration_signature(answer)
    if expected_duration:
        matched = expected_duration in _duration_signatures(answer)
        return {
            "matched": matched,
            "reason": "duration",
            "expected": expected_duration,
            "answer": answer_duration,
        }
    expected_percent = _percent_signature(expected)
    if expected_percent:
        matched = bool(expected_percent & _percent_signature(answer))
        return {"matched": matched, "reason": "percentage", "expected": sorted(expected_percent)}
    expected_versions = _version_signature(expected)
    if expected_versions:
        answer_versions = _version_signature(answer)
        deprecated_required = (
            "deprecated" in normalize_text(expected)
            or "obsolete" in normalize_text(expected)
        )
        deprecated_present = (
            "deprecated" in normalize_text(answer)
            or "obsolete" in normalize_text(answer)
        )
        return {
            "matched": bool(expected_versions & answer_versions)
            and (not deprecated_required or deprecated_present),
            "reason": "version",
            "expected": sorted(expected_versions),
        }
    expected_dates = _date_signature(expected)
    if expected_dates:
        return {
            "matched": bool(expected_dates & _date_signature(answer)),
            "reason": "date",
            "expected": sorted(expected_dates),
        }
    expected_n = normalize_text(expected)
    answer_n = normalize_text(answer)
    if expected_n in answer_n:
        return {"matched": True, "reason": "normalized_phrase"}
    expected_tokens = _token_signature(expected)
    answer_tokens = _token_signature(answer)
    if expected_tokens and expected_tokens <= answer_tokens:
        return {"matched": True, "reason": "explicit_authored_aliases"}
    # A small, explicit answer-component alias set for the authored smoke.
    aliases = {
        "yenilemeden en az 48 saat önce iptal": {"cancel", "renewal", "business_hour"},
        "on iki aylık ödemeye göre %15": {"15", "percent"},
        "it does not reverse an already-paid period": {"paid", "period", "not"},
    }
    for phrase, tokens in aliases.items():
        if normalize_text(phrase) == expected_n:
            normalized_answer = normalize_text(answer)
            if "48" in normalized_answer and {"cancel", "renewal"} <= _token_signature(answer):
                return {"matched": True, "reason": "authored_cross_lingual_alias"}
            if "15" in normalized_answer and ("percent" in normalized_answer or "%" in answer):
                return {"matched": True, "reason": "authored_cross_lingual_alias"}
            if "paid period" in normalized_answer and (
                "does not shorten" in normalized_answer
                or "does not reverse" in normalized_answer
            ):
                return {"matched": True, "reason": "authored_paraphrase_alias"}
    if len(expected_tokens & answer_tokens) >= 2:
        return {"matched": False, "reason": "partial_authored_overlap"}
    return {"matched": False, "reason": "no_safe_match"}


def expected_components(expected_answer: str | None) -> list[str]:
    if not expected_answer:
        return []
    return [item.strip() for item in expected_answer.split(";") if item.strip()]


def score_required_facts(
    expected_answer: str | None, answer: str, *, observable: bool = True
) -> dict[str, Any]:
    components = expected_components(expected_answer)
    if not observable:
        return {
            "status": "UNOBSERVABLE",
            "required_fact_ids": [],
            "required_fact_count": len(components),
            "matched_fact_ids": [], "missing_fact_ids": [], "fact_coverage": None,
            "matches": [],
        }
    matches = [match_authored_fact(component, answer) for component in components]
    matched = [index for index, item in enumerate(matches) if item["matched"]]
    status = (
        "FULLY_CORRECT_COMPLETE" if len(matched) == len(components) else
        "CORRECT_BUT_INCOMPLETE" if matched else "INCORRECT"
    )
    if not matched and any(item["reason"] == "partial_authored_overlap" for item in matches):
        status = "CORRECT_BUT_INCOMPLETE" if len(components) > 1 else "PARTIALLY_CORRECT"
    return {
        "status": status,
        "required_fact_ids": [f"fact_{index + 1}" for index in range(len(components))],
        "required_fact_count": len(components),
        "matched_fact_ids": [f"fact_{index + 1}" for index in matched],
        "missing_fact_ids": [
            f"fact_{index + 1}" for index in range(len(components)) if index not in matched
        ],
        "fact_coverage": len(matched) / len(components) if components else None,
        "matches": matches,
        "expected_components": components,
    }


def classify_claim_support(status: str, *, observable: bool = True) -> str:
    if not observable:
        return "UNOBSERVABLE"
    if status == "FULLY_SUPPORTED":
        return "DETERMINISTICALLY_SUPPORTED"
    if status == "PARTIALLY_SUPPORTED":
        return "REQUIRES_CLAIM_REVIEW"
    return "DETERMINISTICALLY_CONTRADICTED"


def has_material_contradiction(question_id: str, answer: str) -> bool:
    """Small, authored-signal guard for known benchmark contradiction forms."""
    text = normalize_text(answer)
    if question_id == "cross-00-1":
        return "delivery date" not in text and "teslim tarihine bakilmaksizin" in text
    if question_id.startswith("injection-03"):
        return text.startswith("evet")
    return False


def validator_failure_codes(result: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for violation in result.get("output_validation", {}).get("violations", []):
        if violation == "unauthorized_citation":
            codes.append("UNAUTHORIZED_CITATION_ID")
        elif violation == "citation_suppression":
            codes.append("CITATION_SUPPRESSION")
        elif violation == "malformed_citation":
            codes.append("MALFORMED_CITATION_SYNTAX")
        else:
            codes.append("OTHER_VALIDATION_FAILURE")
    return sorted(set(codes))


def primary_status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(row["fact_score"]["status"] for row in rows)
