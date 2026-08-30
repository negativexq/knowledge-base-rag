"""Conservative critical-value extraction for evidence-backed claims."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


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
_LOCAL_DURATION = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(calendar\s+days?|days?|day|hours?|hour|minutes?|minute|mins?|min|seconds?|second|secs?|sec|h|m|s|gün(?:lük)?|saat)\b",
    re.IGNORECASE,
)
_LOCAL_VERSION = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d+(?:\.\d+)+)\b", re.IGNORECASE)
_CITATION = re.compile(r"\s*\[s\.filesystem:[^\]]+\]", re.IGNORECASE)
_LOCAL_WORD = re.compile(r"[\w]+", re.UNICODE)
_LOCAL_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "for",
    "from",
    "go",
    "how",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "use",
    "with",
    "yes",
    "no",
    "you",
    "your",
    "tv",
}


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
    """Legacy union-scope reference used only for historical comparisons."""
    claim_values = extract_critical_values(claim)
    if not claim_values:
        return None
    support_values = extract_critical_values(support_text)
    if not support_values:
        return "CRITICAL_VALUE_ABSENT"
    if any(value in support_values for value in claim_values):
        return "CRITICAL_VALUE_SUPPORTED"
    return "CRITICAL_VALUE_CONFLICT"


def _local_unit(unit: str) -> str:
    unit = unit.lower().replace(" ", "_")
    return {
        "s": "second",
        "sec": "second",
        "secs": "second",
        "second": "second",
        "seconds": "second",
        "m": "minute",
        "min": "minute",
        "mins": "minute",
        "minute": "minute",
        "minutes": "minute",
        "h": "hour",
        "hour": "hour",
        "hours": "hour",
        "saat": "hour",
        "day": "day",
        "days": "day",
        "calendar_days": "day",
        "gün": "day",
        "günlük": "day",
    }.get(unit, unit)


def _local_words(text: str) -> set[str]:
    return {
        word.lower()
        for word in _LOCAL_WORD.findall(text or "")
        if word.lower() not in _LOCAL_STOP and len(word) > 2
    }


def _local_token(
    kind: str, value: str, unit: str | None, start: int, end: int, text: str
) -> dict[str, Any]:
    return {
        "kind": kind,
        "value": unicodedata.normalize("NFKC", value).replace(",", "."),
        "unit": _local_unit(unit) if unit else None,
        "start": start,
        "end": end,
        "local_context": text[max(0, start - 64) : min(len(text), end + 64)],
    }


def _local_tokens(text: str) -> list[dict[str, Any]]:
    text = _CITATION.sub("", unicodedata.normalize("NFKC", text or ""))
    values: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in _LOCAL_DURATION.finditer(text):
        values.append(
            _local_token(
                "DURATION", match.group(1), match.group(2), match.start(), match.end(), text
            )
        )
        occupied.append(match.span())
    for pattern, kind in ((_PERCENT, "PERCENTAGE"), (_LOCAL_VERSION, "VERSION"), (_DATE, "DATE")):
        for match in pattern.finditer(text):
            if any(start < match.end() and match.start() < end for start, end in occupied):
                continue
            values.append(
                _local_token(
                    kind,
                    match.group(1),
                    "%" if kind == "PERCENTAGE" else None,
                    match.start(),
                    match.end(),
                    text,
                )
            )
            occupied.append(match.span())
    for match in _BOOLEAN.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in occupied):
            continue
        normalized = "true" if match.group(1).lower() in {"true", "yes", "evet"} else "false"
        values.append(_local_token("BOOLEAN", normalized, None, match.start(), match.end(), text))
        occupied.append(match.span())
    if not values:
        values.extend(
            _local_token("NUMBER", match.group(0), None, match.start(), match.end(), text)
            for match in _NUMBER.finditer(text)
        )
    return values


def _local_key(value: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return value.get("kind"), value.get("value"), value.get("unit")


def claim_local_critical_value_audit(claim: str, support_texts: Sequence[str]) -> dict[str, Any]:
    """Check critical values against claim-local selected support units.

    This is a deterministic consistency guard, not a semantic entailment check.
    Unrelated values in another support unit do not conflict.  Unresolved
    relationships remain conservative and fail validation.
    """
    answer_tokens = _local_tokens(claim)
    citation_only_claim = bool(_CITATION.search(claim)) and not answer_tokens
    support_tokens = [_local_tokens(text) for text in support_texts]
    if citation_only_claim:
        if any(support_tokens):
            return {
                "answer_critical_tokens": [],
                "token_traces": [],
                "failure_codes": [],
                "status": "CRITICAL_VALUE_SUPPORTED",
                "pass": True,
            }
        return {
            "answer_critical_tokens": [],
            "token_traces": [],
            "failure_codes": ["CRITICAL_VALUE_UNSUPPORTED"],
            "status": "CRITICAL_VALUE_UNSUPPORTED",
            "pass": False,
        }
    traces: list[dict[str, Any]] = []
    failures: list[str] = []
    for answer_token in answer_tokens:
        per_support: list[dict[str, Any]] = []
        relations: list[str] = []
        for support_index, support_text in enumerate(support_texts):
            support_tokens = _local_tokens(support_text)
            answer_words = _local_words(answer_token["local_context"])
            support_rows = []
            for support_token in support_tokens:
                same_value = _local_key(answer_token) == _local_key(support_token)
                same_kind = answer_token["kind"] == support_token["kind"]
                same_unit = answer_token["unit"] == support_token["unit"]
                context_related = bool(answer_words & _local_words(support_token["local_context"]))
                if same_value and context_related:
                    relation = "DIRECT_SUPPORT"
                elif same_kind and same_unit and context_related:
                    relation = "DIRECT_CONFLICT"
                else:
                    relation = "UNRELATED"
                support_rows.append({**support_token, "relation": relation})
            support_relation = (
                "DIRECT_SUPPORT"
                if any(item["relation"] == "DIRECT_SUPPORT" for item in support_rows)
                else "DIRECT_CONFLICT"
                if any(item["relation"] == "DIRECT_CONFLICT" for item in support_rows)
                else "UNRELATED"
                if support_rows
                else "INDETERMINATE"
            )
            relations.append(support_relation)
            per_support.append(
                {
                    "support_index": support_index,
                    "support_critical_tokens": support_rows,
                    "relation": support_relation,
                    "matching_local_context": [
                        item["local_context"]
                        for item in support_rows
                        if item["relation"] == "DIRECT_SUPPORT"
                    ],
                }
            )
        if "DIRECT_SUPPORT" in relations:
            status = "DIRECT_SUPPORT"
        elif "DIRECT_CONFLICT" in relations:
            status = "DIRECT_CONFLICT"
            failures.append("CRITICAL_VALUE_DIRECT_CONFLICT")
        else:
            status = "INDETERMINATE"
            failures.append("CRITICAL_VALUE_INDETERMINATE")
        traces.append(
            {
                "answer_critical_token": answer_token,
                "answer_local_context": answer_token["local_context"],
                "per_support": per_support,
                "status": status,
            }
        )
    return {
        "answer_critical_tokens": answer_tokens,
        "token_traces": traces,
        "failure_codes": sorted(set(failures)),
        "status": (
            "CRITICAL_VALUE_DIRECT_CONFLICT"
            if "CRITICAL_VALUE_DIRECT_CONFLICT" in failures
            else "CRITICAL_VALUE_INDETERMINATE"
            if failures
            else "CRITICAL_VALUE_SUPPORTED"
            if answer_tokens
            else None
        ),
        "pass": not failures,
    }
