"""Conservative critical-value extraction for evidence-backed claims."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CriticalValue:
    kind: str
    value: str
    unit: str | None = None


_DURATION = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(calendar\s+days?|days?|gün(?:lük)?|hours?|hours?|saat|business\s+hours?)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_VERSION = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d{4}[.]\d+)\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_CURRENCY = re.compile(
    r"(?:(USD|EUR|GBP|TRY|TL)\s*)?([€$£₺]?\s*\d+(?:[.,]\d+)?)\s*(USD|EUR|GBP|TRY|TL)?",
    re.IGNORECASE,
)
_BOOLEAN = re.compile(r"\b(true|false|yes|no|evet|hayır|hayir)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _number(value: str) -> str:
    return value.replace(",", ".")


def extract_critical_values(text: str) -> list[CriticalValue]:
    values: list[CriticalValue] = []
    for match in _DURATION.finditer(text or ""):
        unit = match.group(2).lower().replace(" ", "_")
        unit = {
            "day": "day",
            "days": "day",
            "calendar_days": "day",
            "gün": "day",
            "günlük": "day",
            "hour": "hour",
            "hours": "hour",
            "saat": "hour",
            "business_hours": "business_hour",
        }.get(unit, unit)
        values.append(CriticalValue("DURATION", _number(match.group(1)), unit))
    for match in _PERCENT.finditer(text or ""):
        values.append(CriticalValue("PERCENTAGE", _number(match.group(1)), "%"))
    for match in _VERSION.finditer(text or ""):
        values.append(CriticalValue("VERSION", match.group(1), None))
    for match in _DATE.finditer(text or ""):
        values.append(CriticalValue("DATE", match.group(1), None))
    for match in _CURRENCY.finditer(text or ""):
        prefix, amount, suffix = match.groups()
        currency = (prefix or suffix or "").upper()
        if currency:
            values.append(CriticalValue("CURRENCY", _number(amount.replace(" ", "")), currency))
    for match in _BOOLEAN.finditer(text or ""):
        value = match.group(1).lower()
        values.append(
            CriticalValue(
                "BOOLEAN",
                "true" if value in {"true", "yes", "evet"} else "false",
                None,
            )
        )
    if not values:
        values.extend(
            CriticalValue("NUMBER", _number(match.group(0)), None)
            for match in _NUMBER.finditer(text or "")
        )
    return values


def critical_value_status(claim: str, support_text: str) -> str | None:
    claim_values = extract_critical_values(claim)
    if not claim_values:
        return None
    support_values = extract_critical_values(support_text)
    if not support_values:
        return "CRITICAL_VALUE_ABSENT"
    if any(value in support_values for value in claim_values):
        return "CRITICAL_VALUE_SUPPORTED"
    return "CRITICAL_VALUE_CONFLICT"
