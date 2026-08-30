"""Conservative critical-value extraction for evidence-backed claims."""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

CriticalValidatorVersion = Literal["baseline", "v3"]
VALID_CRITICAL_VALIDATOR_VERSIONS = ("baseline", "v3")


def validate_critical_validator_version(value: str) -> CriticalValidatorVersion:
    """Validate the server-owned critical-value validator selector."""
    if value not in VALID_CRITICAL_VALIDATOR_VERSIONS:
        raise ValueError(
            "critical validator version must be one of "
            f"{VALID_CRITICAL_VALIDATOR_VERSIONS}, got {value!r}"
        )
    return cast(CriticalValidatorVersion, value)


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


def _baseline_claim_local_critical_value_audit(
    claim: str, support_texts: Sequence[str]
) -> dict[str, Any]:
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


# The following helpers are the production-compatible port of the frozen V3
# contract.  They intentionally remain local and deterministic: the offline
# calibration scripts are never imported by serving code.
_V3_VERSION = re.compile(r"(?<![\w-])v?(\d+(?:\.\d+){0,2})(?:\.x)?(?![\w])", re.IGNORECASE)
_V3_GROUPED_INTEGER = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_V3_SIGNED = re.compile(r"(?<![\w])([+-])(\d+(?:[.,]\d+)?)(?![\w])")
_V3_SQLCODE = re.compile(r"\bSQLCODE\s*=?\s*([+-]?\d+)\b", re.IGNORECASE)


def _v3_version_values(text: str) -> list[tuple[int, ...]]:
    values: list[tuple[int, ...]] = []
    for match in _V3_VERSION.finditer(text or ""):
        # ISO dates are dates, not versions. The frozen candidate only
        # applies its version guard when the critical value is a version.
        if re.match(r"\d{4}-\d{1,2}-\d{1,2}", text[match.start() :]):
            continue
        try:
            values.append(tuple(int(part) for part in match.group(1).split(".")))
        except ValueError:
            continue
    return values


def _v3_version_signal(text: str) -> bool:
    """Distinguish version notation from dotted/grouped numeric values."""
    if re.search(r"\b(?:version|release|family|series)\b|\bv\d", text, re.IGNORECASE):
        return bool(_v3_version_values(text))
    return any(len(value) >= 3 for value in _v3_version_values(text))


def _v3_claim_version_specificity(claim: str) -> str:
    lower = claim.lower()
    if re.search(
        r"\b(?:family|series|major version|major release)\b|\.x\b|\bor\s+later\b",
        lower,
    ):
        if re.search(r"\b\d+\.\d+\.x\b|\bminor series\b", lower):
            return "FAMILY_MINOR"
        return "FAMILY_MAJOR"
    if re.search(r"\b(?:exact(?:ly)?|full version)\b", lower):
        return "EXACT"
    values = _v3_version_values(claim)
    if values and len(values[0]) >= 3:
        return "EXACT"
    return "AMBIGUOUS"


def _v3_version_guard_status(claim: str, support: str) -> str | None:
    claim_versions = _v3_version_values(claim)
    support_versions = _v3_version_values(support)
    if not claim_versions or not support_versions:
        return None
    specificity = _v3_claim_version_specificity(claim)
    claim_value = claim_versions[0]
    if specificity == "EXACT":
        if re.search(
            r"\b(?:not|no|never|does\s+not|doesn't|cannot|can't)\b",
            claim,
            re.IGNORECASE,
        ) and re.search(r"\b(?:supports?|exposes?|returns?)\b", support, re.IGNORECASE):
            if any(value == claim_value for value in support_versions):
                return "DIRECT_CONFLICT"
        return (
            "DIRECT_SUPPORT"
            if any(value == claim_value for value in support_versions)
            else "DIRECT_CONFLICT"
        )
    if specificity == "FAMILY_MAJOR":
        if "or later" in claim.lower():
            return (
                "DIRECT_SUPPORT"
                if any(value >= claim_value for value in support_versions)
                else "DIRECT_CONFLICT"
            )
        return (
            "DIRECT_SUPPORT"
            if any(value[0] == claim_value[0] for value in support_versions)
            else "DIRECT_CONFLICT"
        )
    if specificity == "FAMILY_MINOR":
        return (
            "DIRECT_SUPPORT"
            if any(len(value) >= 2 and value[:2] == claim_value[:2] for value in support_versions)
            else "DIRECT_CONFLICT"
        )
    return "INDETERMINATE"


def _v3_number_equivalent(left: str, right: str) -> bool:
    def grouped(value: str) -> str | None:
        if _V3_GROUPED_INTEGER.fullmatch(value):
            return value.replace(",", "").replace(".", "")
        return None

    if left.replace(",", ".") == right.replace(",", "."):
        return True
    return grouped(left) == right or grouped(right) == left


def _v3_decimal_equivalent(left: str, right: str, claim: str, support: str) -> bool:
    if "." not in left or "." not in right:
        return False
    if not re.fullmatch(r"\d+\.\d+", left) or not re.fullmatch(r"\d+\.\d+", right):
        return False
    if not re.search(
        r"\b(?:seconds?|secs?|percent|rate|ratio|latency|probability)\b|%",
        f"{claim} {support}",
        re.IGNORECASE,
    ):
        return False
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return False


def _v3_explicit_grouping_context(claim: str, support: str) -> bool:
    return bool(
        re.search(
            r"\b(?:bytes?|records?|entries|rows?|packets?|blocks?|kb|mb|gb)\b",
            f"{claim} {support}",
            re.IGNORECASE,
        )
    )


def _v3_ambiguous_locale_pair(claim: str, support: str) -> bool:
    def numeric(text: str) -> list[str]:
        return re.findall(r"(?<![\w])\d+(?:[.,]\d+)*(?![\w])", text)

    grouped = [value for value in numeric(claim) if _V3_GROUPED_INTEGER.fullmatch(value)]
    if not grouped:
        return False
    normalized = {value.replace(",", "").replace(".", "") for value in grouped}
    support_values = set()
    for value in numeric(support):
        if _V3_GROUPED_INTEGER.fullmatch(value):
            support_values.add(value.replace(",", "").replace(".", ""))
        elif value.isdigit() and len(value) > 3:
            support_values.add(value)
    return bool(normalized & support_values) and not _v3_explicit_grouping_context(claim, support)


def _v3_signed_numeric(text: str) -> str | None:
    match = _V3_SIGNED.search(text or "")
    return match.group(1) + match.group(2).replace(",", ".") if match else None


def _v3_tokenized(text: str) -> list[dict[str, Any]]:
    tokens = _local_tokens(text)
    for token in tokens:
        context = token.get("local_context", "")
        if (
            token.get("kind") == "VERSION"
            and re.fullmatch(r"\d{1,3}[.,]\d{3}", str(token.get("value")))
            and not re.search(r"\b(?:version|release|v)\b", context, re.IGNORECASE)
        ):
            token["kind"] = "NUMBER"
    version_number = re.compile(r"\bversion\s+(\d+)\b", re.IGNORECASE)
    for match in version_number.finditer(text):
        for token in tokens:
            if token.get("kind") == "NUMBER" and token.get("start") == match.start(1):
                token["kind"] = "VERSION"
    return tokens


def _v3_relation_audit(claim: str, support: Sequence[str]) -> list[str]:
    """Return frozen V3 relation statuses for non-version critical values."""
    support_text = " ".join(support)
    claim_cve = re.search(r"CVE[- ](\d{4})[- ](\d+)", claim, re.IGNORECASE)
    claim_sql = _V3_SQLCODE.search(claim)
    if claim_cve or claim_sql:
        identifier = (
            f"CVE-{claim_cve.group(1)}-{claim_cve.group(2)}"
            if claim_cve
            else f"SQLCODE {claim_sql.group(1)}"
        )
        compact = re.sub(r"[^a-z0-9]+", "", identifier.casefold())
        compact_support = re.sub(r"[^a-z0-9]+", "", support_text.casefold())
        if compact in compact_support:
            return ["DIRECT_SUPPORT"]
        if re.search(r"\b(?:CVE-|SQLCODE)\b", support_text, re.IGNORECASE):
            return ["DIRECT_CONFLICT"]
        return ["INDETERMINATE"]

    claim_tokens = _v3_tokenized(claim)
    support_tokens = [_v3_tokenized(text) for text in support]
    statuses: list[str] = []
    for index, token in enumerate(claim_tokens):
        claim_context = token.get("local_context", "")
        claim_words = set(re.findall(r"[A-Za-z0-9_]+", claim_context.lower()))
        has_support = False
        has_conflict = False
        signed_claim = _v3_signed_numeric(claim_context)
        for other_tokens in support_tokens:
            for other in other_tokens:
                same_kind = other.get("kind") == token.get("kind") and other.get(
                    "unit"
                ) == token.get("unit")
                same_value = str(other.get("value")) == str(token.get("value"))
                equivalent = token.get("kind") in {
                    "NUMBER",
                    "PERCENTAGE",
                    "DURATION",
                    "CURRENCY",
                } and _v3_number_equivalent(str(token.get("value")), str(other.get("value")))
                other_context = other.get("local_context", "")
                context_related = bool(
                    claim_words & set(re.findall(r"[A-Za-z0-9_]+", other_context.lower()))
                )
                if same_kind and (same_value or equivalent) and context_related:
                    has_support = True
                elif same_kind and context_related:
                    has_conflict = True
        if signed_claim:
            support_signed = _v3_signed_numeric(support_text)
            if support_signed == signed_claim:
                has_support = True
            elif re.search(
                rf"(?<![\w])(?:[+-])?{re.escape(signed_claim.lstrip('+-'))}(?![\w])",
                support_text,
            ):
                has_conflict = True
        if _v3_decimal_equivalent(
            "".join(re.findall(r"\d+\.\d+", claim)[:1]),
            "".join(re.findall(r"\d+\.\d+", support_text)[:1]),
            claim,
            support_text,
        ):
            has_support = True
        statuses.append(
            "DIRECT_SUPPORT"
            if has_support
            else "DIRECT_CONFLICT"
            if has_conflict
            else "INDETERMINATE"
        )
    return statuses


def _v3_status(claim: str, support_texts: Sequence[str]) -> str:
    support = " ".join(support_texts)
    version_status = _v3_version_guard_status(claim, support) if _v3_version_signal(claim) else None
    if version_status:
        return version_status
    claim_values = _local_tokens(claim)
    if _V3_SQLCODE.search(claim):
        claim_code = _V3_SQLCODE.search(claim).group(1)  # type: ignore[union-attr]
        support_codes = _V3_SQLCODE.findall(support)
        return (
            "DIRECT_SUPPORT"
            if claim_code in support_codes
            else "DIRECT_CONFLICT"
            if support_codes
            else "INDETERMINATE"
        )
    if _v3_signed_numeric(claim):
        signed = _v3_signed_numeric(claim)
        support_signed = _v3_signed_numeric(support)
        if support_signed == signed:
            return "DIRECT_SUPPORT"
        if signed and re.search(
            rf"(?<![\w])(?:[+-])?{re.escape(signed.lstrip('+-'))}(?![\w])", support
        ):
            return "DIRECT_CONFLICT"
    if _v3_ambiguous_locale_pair(claim, support):
        return "INDETERMINATE"
    statuses = _v3_relation_audit(claim, support_texts)
    if "DIRECT_CONFLICT" in statuses:
        return "DIRECT_CONFLICT"
    if "INDETERMINATE" in statuses:
        return "INDETERMINATE"
    return "DIRECT_SUPPORT" if claim_values else "DIRECT_SUPPORT"


def _v3_critical_type(claim: str) -> str | None:
    if _V3_SQLCODE.search(claim) or re.search(r"\bCVE[- ]\d{4}[- ]\d+", claim, re.IGNORECASE):
        return "IDENTIFIER"
    if _v3_version_signal(claim):
        return "VERSION"
    tokens = _v3_tokenized(claim)
    return tokens[0].get("kind") if tokens else None


def _validator_disagreement(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    left = baseline.get("validator_outcome")
    right = candidate.get("validator_outcome")
    if left == right:
        return "SAME"
    return {
        ("REJECT", "PASS"): "BASELINE_REJECT_V3_PASS",
        ("PASS", "REJECT"): "BASELINE_PASS_V3_REJECT",
        ("INDETERMINATE", "PASS"): "BASELINE_IND_V3_PASS",
        ("PASS", "INDETERMINATE"): "BASELINE_PASS_V3_IND",
        ("REJECT", "INDETERMINATE"): "BASELINE_REJECT_V3_IND",
        ("INDETERMINATE", "REJECT"): "BASELINE_IND_V3_REJECT",
    }.get((left, right), "SAME")


def _audit_outcome(result: dict[str, Any]) -> str:
    if result.get("pass"):
        return "PASS"
    if any("INDETERMINATE" in code for code in result.get("failure_codes", [])):
        return "INDETERMINATE"
    return "REJECT"


def claim_local_critical_value_audit(
    claim: str,
    support_texts: Sequence[str],
    *,
    validator_version: CriticalValidatorVersion = "baseline",
    shadow_enabled: bool = False,
) -> dict[str, Any]:
    """Audit a claim with the server-selected validator, optionally in shadow.

    Shadow evaluation is diagnostic only: the baseline result is always
    returned while shadow mode is active with the baseline selector.
    """
    version = validate_critical_validator_version(validator_version)
    started = time.perf_counter()
    baseline_started = time.perf_counter()
    baseline = _baseline_claim_local_critical_value_audit(claim, support_texts)
    baseline_duration_ms = round((time.perf_counter() - baseline_started) * 1000, 3)
    result = baseline
    if version == "v3":
        status = _v3_status(claim, support_texts)
        outcome = (
            "REJECT"
            if status == "DIRECT_CONFLICT"
            else "INDETERMINATE"
            if status == "INDETERMINATE"
            else "PASS"
        )
        result = {
            **baseline,
            "failure_codes": (
                ["CRITICAL_VALUE_DIRECT_CONFLICT"]
                if outcome == "REJECT"
                else ["CRITICAL_VALUE_INDETERMINATE"]
                if outcome == "INDETERMINATE"
                else []
            ),
            "status": (
                "CRITICAL_VALUE_DIRECT_CONFLICT"
                if outcome == "REJECT"
                else "CRITICAL_VALUE_INDETERMINATE"
                if outcome == "INDETERMINATE"
                else "CRITICAL_VALUE_SUPPORTED"
            ),
            "pass": outcome == "PASS",
        }
    shadow = None
    shadow_v3_duration_ms = 0.0
    shadow_error = False
    shadow_error_class: str | None = None
    if shadow_enabled and version == "baseline":
        shadow_started = time.perf_counter()
        try:
            candidate = claim_local_critical_value_audit(
                claim, support_texts, validator_version="v3", shadow_enabled=False
            )
            shadow = _validator_disagreement(
                {"validator_outcome": _audit_outcome(result)},
                {"validator_outcome": _audit_outcome(candidate)},
            )
        except Exception:
            # Shadow is diagnostic only. A candidate failure must never alter
            # the baseline answer path or turn into a user-visible failure.
            shadow_error = True
            shadow_error_class = "SHADOW_EVALUATION_FAILURE"
            shadow = "SHADOW_ERROR"
        finally:
            shadow_v3_duration_ms = round((time.perf_counter() - shadow_started) * 1000, 3)
    outcome = _audit_outcome(result)
    reason = result.get("status") or "NO_CRITICAL_VALUE"
    result.update(
        {
            "validator_version": version,
            "validator_outcome": outcome,
            "validator_reason_class": reason,
            "critical_value_type": _v3_critical_type(claim),
            "critical_value_count": len(result.get("answer_critical_tokens", [])),
            "forced_abstain": outcome != "PASS",
            "indeterminate": outcome == "INDETERMINATE",
            "locale_ambiguity": outcome == "INDETERMINATE"
            and _v3_ambiguous_locale_pair(claim, " ".join(support_texts)),
            "version_ambiguity": outcome == "INDETERMINATE"
            and _v3_claim_version_specificity(claim) == "AMBIGUOUS",
            "version_specificity_reject": outcome == "REJECT"
            and _v3_critical_type(claim) == "VERSION",
            "identifier_reject": outcome == "REJECT" and _v3_critical_type(claim) == "IDENTIFIER",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "baseline_duration_ms": baseline_duration_ms,
            "shadow_v3_duration_ms": shadow_v3_duration_ms,
            "shadow_enabled": bool(shadow_enabled),
            "shadow_disagreement": shadow,
            "shadow_error": shadow_error,
            "shadow_error_class": shadow_error_class,
        }
    )
    return result
