"""Rule-based content screening for POST /chat, run in shadow mode.

Two detectors, both deterministic and dependency-free:

- Direct prompt injection in the user's question (English and Turkish
  phrasings): instruction override, system-prompt extraction, jailbreak
  personas, and prompt-delimiter injection. This complements, not replaces,
  the structural defenses: the question is already JSON-encoded with angle
  brackets escaped (app/llm/trust_boundary.py) and the answer is checked by
  app/llm/output_policy.py.
- PII in questions and in the answer shown to the user: email, phone (Turkish
  and E.164), IBAN (mod-97 checked), Turkish national ID (TCKN checksum), and
  payment card numbers (Luhn checked). Checksums keep order numbers and other
  long digit strings from being reported.

Results carry rule IDs and per-type counts only — never the matched text — so
they can go on spans and into the audit log. Shadow mode means nothing is
blocked; see docs/security.md for how the counts are meant to inform a later
enforcement decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FLAGS = re.IGNORECASE | re.UNICODE

_INJECTION_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "instruction_override": (
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}?"
            r"\b(?:previous|prior|above|earlier|all|your|any|the)\b[^.\n]{0,20}?"
            r"\b(?:instructions?|rules|prompts?|guidelines|directives)\b",
            _FLAGS,
        ),
        re.compile(
            r"(?:önceki|yukarıdaki|tüm|bütün|şimdiye kadarki|verilen)\s+"
            r"(?:talimat|kural|komut|yönerge)\w*\s+(?:\w+\s+){0,2}?"
            r"(?:yok\s*say|görmezden\s+gel|unut|ihmal\s+et|geçersiz\s+say)",
            _FLAGS,
        ),
    ),
    "system_prompt_extraction": (
        re.compile(
            r"\b(?:show|reveal|print|repeat|display|output|leak|tell\s+me|what\s+(?:are|were|is))\b"
            r"[^.\n]{0,30}?\b(?:your|the)\s+(?:system\s+prompt|initial\s+instructions|"
            r"hidden\s+instructions|original\s+instructions|instructions\s+above|system\s+message)",
            _FLAGS,
        ),
        re.compile(
            r"sistem\s*(?:prompt|istem|talimat|mesaj)\w*\s+(?:\w+\s+){0,2}?"
            r"(?:göster|yaz|söyle|ver|paylaş|açıkla|nedir)",
            _FLAGS,
        ),
    ),
    "jailbreak_persona": (
        re.compile(
            r"\b(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|from\s+now\s+on\s+you\s+are)\b"
            r"[^.\n]{0,40}?\b(?:dan|jailbroken|unrestricted|unfiltered|"
            r"without\s+(?:any\s+)?(?:restrictions|rules|filters|limits))\b",
            _FLAGS,
        ),
        re.compile(r"\b(?:developer\s+mode|do\s+anything\s+now|jailbreak)\b", _FLAGS),
        re.compile(
            r"(?:kısıtlama|filtre|kural|sınır)(?:sız|siz)\s+(?:bir\s+)?(?:yapay\s+zeka|asistan|model)",
            _FLAGS,
        ),
    ),
    "delimiter_injection": (
        re.compile(
            r"</?\s*(?:retrieved_context|untrusted_context|system|assistant|instructions?)\b[^>]{0,40}>",
            _FLAGS,
        ),
        re.compile(r"<\|im_(?:start|end)\|>|\[/?INST\]|```\s*system\b", _FLAGS),
        re.compile(r"^\s*(?:system|assistant)\s*:", _FLAGS | re.MULTILINE),
    ),
}

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
# Country code + 2 check digits + 11–30 alphanumerics, optionally grouped in 4s.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
# Maximal runs of digits joined by at most one space or dash, so a long
# number is classified as a whole and never matched in pieces.
_DIGIT_RUN = re.compile(r"(\+)?(?<![\d])\d(?:[ -]?\d)+(?![\d])")


@dataclass(frozen=True)
class ScreeningResult:
    injection_rules: tuple[str, ...] = ()
    pii_counts: dict[str, int] = field(default_factory=dict)

    @property
    def flagged(self) -> bool:
        return bool(self.injection_rules or self.pii_counts)

    def span_attributes(self, prefix: str) -> dict[str, object]:
        attributes: dict[str, object] = {f"{prefix}.flagged": self.flagged}
        if self.injection_rules:
            attributes[f"{prefix}.injection_rules"] = tuple(sorted(self.injection_rules))
        if self.pii_counts:
            attributes[f"{prefix}.pii_types"] = tuple(sorted(self.pii_counts))
            attributes[f"{prefix}.pii_count"] = sum(self.pii_counts.values())
        return attributes

    def audit_fields(self) -> dict[str, object]:
        return {
            "injection_rules": sorted(self.injection_rules),
            "pii_counts": dict(sorted(self.pii_counts.items())),
        }


def screen_input(text: str) -> ScreeningResult:
    """Screen a user question: prompt-injection rules and PII."""
    return ScreeningResult(injection_rules=_injection_rules(text), pii_counts=_pii_counts(text))


def screen_output(text: str) -> ScreeningResult:
    """Screen the answer shown to the user: PII only. Policy disclosure in
    answers is app/llm/output_policy.py's job."""
    return ScreeningResult(pii_counts=_pii_counts(text))


def _injection_rules(text: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            rule
            for rule, patterns in _INJECTION_RULES.items()
            if any(pattern.search(text) for pattern in patterns)
        )
    )


def _pii_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    def add(kind: str) -> None:
        counts[kind] = counts.get(kind, 0) + 1

    # Each detector blanks what it matched so later, looser detectors (digit
    # runs) never re-count the digits inside an email or IBAN.
    for match in _EMAIL.finditer(text):
        add("email")
    text = _EMAIL.sub(" ", text)

    def iban(match: re.Match[str]) -> str:
        if _iban_checksum_ok(match.group(0)):
            add("iban")
            return " "
        return match.group(0)

    text = _IBAN.sub(iban, text)

    for match in _DIGIT_RUN.finditer(text):
        kind = _classify_digit_run(match.group(1) is not None, re.sub(r"\D", "", match.group(0)))
        if kind is not None:
            add(kind)
    return counts


def _classify_digit_run(has_plus: bool, digits: str) -> str | None:
    if has_plus:
        return "phone" if 8 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits.startswith("0"):
        return "phone"  # Turkish national format, e.g. 0532 123 45 67
    if len(digits) == 11 and _tckn_checksum_ok(digits):
        return "tckn"
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return "credit_card"
    return None


def _iban_checksum_ok(raw: str) -> bool:
    iban = raw.replace(" ", "").upper()
    if not 15 <= len(iban) <= 34:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def _tckn_checksum_ok(digits: str) -> bool:
    if len(digits) != 11 or digits[0] == "0":
        return False
    d = [int(c) for c in digits]
    d10 = (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10
    d11 = sum(d[:10]) % 10
    return d[9] == d10 and d[10] == d11


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
