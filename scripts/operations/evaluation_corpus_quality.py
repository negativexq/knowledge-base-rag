"""Fast static quality checks shared by the corpus builder and validator."""

from __future__ import annotations

import re
from collections import Counter

EN_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "when", "what", "which",
    "must", "should", "within", "after", "before", "only", "not", "are", "is", "of",
}
TR_STOPWORDS = {
    "ve", "bir", "için", "ile", "bu", "şu", "olan", "olarak", "göre", "hangi", "kadar",
    "de", "da", "ile", "olan", "süre", "iade", "belge", "kaydı", "kapsamında",
}
LEAKAGE_PATTERNS = (
    r"does the available evidence", r"can an operator cite", r"check the tenant boundary",
    r"without naming a plan or region", r"using the (?:turkish|english) (?:source|policy|document)",
    r"the (?:turkish|english) source is relevant", r"according to the english document",
    r"answer for tenant-[ab] only", r"is this fact available to a tenant-[ab] caller",
    r"keep the required evidence", r"give both source identities", r"state the safe handling",
)


def substantive_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result: list[str] = []
    for paragraph in paragraphs:
        if paragraph.startswith("#") or paragraph.startswith("|"):
            continue
        if re.fullmatch(r"[-*_ ]+", paragraph):
            continue
        if re.match(
            r"^(document owner|policy owner|contract owner|owner|effective date|effective|"
            r"published|"
            r"last reviewed|audience|scope|applies to|authority|version|page|belge sahibi|yürürlük|"
            r"son gözden geçirme|kapsam|belge sahibi)\s*:",
            paragraph,
            re.IGNORECASE,
        ):
            continue
        result.append(paragraph)
    return result


def _normalise_paragraph(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\bpage\s+\d+\b", "", value)
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^\w\sçğıöşü]", "", value).strip()


def quality_metrics(text: str) -> dict[str, float | int]:
    paragraphs = substantive_paragraphs(text)
    # Generated PDFs repeat a short running title on every page.  It is page
    # furniture, not substantive content, and must not hide paragraph quality.
    short_repeated = {
        paragraph for paragraph, count in Counter(paragraphs).items()
        if count >= 3 and len(paragraph.split()) <= 8
    }
    paragraphs = [paragraph for paragraph in paragraphs if paragraph not in short_repeated]
    exact = Counter(paragraphs)
    normalised = Counter(_normalise_paragraph(paragraph) for paragraph in paragraphs)
    grams: Counter[str] = Counter()
    for paragraph in paragraphs:
        words = re.findall(r"[\wçğıöşü]+", paragraph.lower())
        grams.update(" ".join(words[index:index + 10]) for index in range(max(0, len(words) - 9)))
    repeated_grams = sum(count - 1 for count in grams.values() if count > 1)
    total_grams = sum(grams.values())
    total = len(paragraphs) or 1
    return {
        "substantive_paragraph_count": len(paragraphs),
        "exact_duplicate_ratio": round(
            sum(count - 1 for count in exact.values() if count > 1) / total, 6
        ),
        "normalized_duplicate_ratio": round(
            sum(count - 1 for count in normalised.values() if count > 1) / total, 6
        ),
        "unique_substantive_paragraph_ratio": round(len(normalised) / total, 6),
        "repeated_long_ngram_count": repeated_grams,
        "repeated_long_ngram_ratio": round(repeated_grams / max(1, total_grams), 6),
    }


def language_scores(text: str) -> dict[str, float]:
    words = re.findall(r"[\wçğıöşü]+", text.lower())
    if not words:
        return {"en": 0.0, "tr": 0.0}
    en = sum(word in EN_STOPWORDS for word in words) / len(words)
    tr = (
        sum(word in TR_STOPWORDS for word in words)
        + len(re.findall(r"[çğıöşü]", text.lower())) / 3
    ) / len(words)
    return {"en": round(en, 6), "tr": round(tr, 6)}


def language_matches(text: str, expected: str) -> bool:
    scores = language_scores(text)
    # Turkish orthography is a strong signal; for short English fixtures the
    # stopword score is more reliable than character counts.
    if expected == "tr":
        return scores["tr"] >= max(0.015, scores["en"] * 0.8)
    return scores["en"] >= max(0.015, scores["tr"] * 0.8)


def query_has_label_leakage(query: str) -> bool:
    lowered = query.lower()
    return any(re.search(pattern, lowered) for pattern in LEAKAGE_PATTERNS)
