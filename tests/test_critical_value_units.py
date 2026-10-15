"""Critical values with storage units and Turkish-suffixed durations.

Two golden-set questions were answered correctly in Turkish from English PDF
evidence and still rejected (CRITICAL_VALUE_INDETERMINATE), so the user saw
"not found":

- "Ücretsiz hesap 15 GB ..." against "Free accounts include 15GB of storage."
  The glued "15GB" produced no value at all, and "GB" was not a unit.
- "... süresi 30 gündür." against "Link expiration defaults to 30 days."
  Only "gün"/"günlük" were durations; the copula form "gündür" was not.
"""

import pytest

from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_validator_runtime import audit_critical_value


def _outcome(answer: str, support: str) -> str:
    return audit_critical_value(answer, [support], selector="architecture_v2", claim_id="c")[
        "validator_outcome"
    ]


def _values(text: str) -> list[tuple[str, str, str | None]]:
    return [
        (o.lexical_type, o.normalized_value, o.unit) for o in extract_critical_occurrences(text)
    ]


# --- the two golden-set failures ---------------------------------------------


def test_spaced_storage_answer_is_supported_by_glued_english_evidence():
    assert (
        _outcome(
            "Ücretsiz hesap 15 GB depolama alanı içerir.",
            "Free accounts include 15GB of storage.",
        )
        == "PASS"
    )


def test_turkish_copula_duration_is_supported_by_english_days():
    assert (
        _outcome(
            "Paylaşılan bağlantılar için varsayılan son kullanma süresi 30 gündür.",
            "Link expiration defaults to 30 days if not specified.",
        )
        == "PASS"
    )


# --- extraction ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15GB of storage", [("NUMBER", "15", "gb")]),
        ("15 GB depolama", [("NUMBER", "15", "gb")]),
        ("1.5 TB plan", [("NUMBER", "1.5", "tb")]),
        ("500MB limit", [("NUMBER", "500", "mb")]),
    ],
)
def test_storage_sizes_carry_their_unit(text, expected):
    assert _values(text) == expected


@pytest.mark.parametrize(
    "text",
    ["30 gün", "30 gündür", "30 gündür.", "30 günde", "30 güne kadar", "30 günü", "30 günlük"],
)
def test_turkish_day_suffixes_are_durations(text):
    assert _values(text)[0] == ("DURATION", "30", "day")


@pytest.mark.parametrize("text", ["24 saat", "24 saattir", "24 saatte", "24 saatlik"])
def test_turkish_hour_suffixes_are_durations(text):
    assert _values(text)[0] == ("DURATION", "24", "hour")


def test_a_word_that_only_starts_with_gun_is_not_a_duration():
    """The word güncelleme (update) begins with gün but is not a day."""
    assert _values("30 güncelleme yapıldı")[0][0] == "NUMBER"
    assert _values("30 güncelleme yapıldı")[0][2] is None


# --- no false support ----------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "support"),
    [
        ("Ücretsiz hesap 20 GB depolama alanı içerir.", "Free accounts include 15GB of storage."),
        ("Ücretsiz hesap 15 TB depolama alanı içerir.", "Free accounts include 15GB of storage."),
        ("Bağlantı süresi 45 gündür.", "Link expiration defaults to 30 days if not specified."),
        ("Bağlantı süresi 30 saattir.", "Link expiration defaults to 30 days if not specified."),
    ],
)
def test_a_different_value_or_unit_is_never_supported(answer, support):
    assert _outcome(answer, support) != "PASS"
