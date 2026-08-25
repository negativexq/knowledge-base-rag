import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationReport:
    """Sprint 20: a machine-checkable quality gate for a golden set, not
    just eyeballed — a 220-question set is too large to manually spot
    every dangling location or accidental duplicate the way Sprint 9/17.5
    could with 12.
    """

    exact_duplicate_queries: list[list[str]]  # groups of question ids sharing an exact query
    normalized_duplicate_queries: list[list[str]]  # groups sharing a normalized query
    dangling_locations: list[tuple[str, tuple[str, str, str]]]  # (question_id, location)
    language_pair_counts: dict[tuple[str, str], int]
    not_found_count: int
    not_found_ratio: float
    total_questions: int

    @property
    def is_clean(self) -> bool:
        return not self.exact_duplicate_queries and not self.dangling_locations

    def meets_distribution(self, minimums: dict[tuple[str, str], int]) -> bool:
        return all(
            self.language_pair_counts.get(cell, 0) >= minimum
            for cell, minimum in minimums.items()
        )


def normalize_query(query: str) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed — catches a
    near-duplicate that differs only in casing/punctuation/spacing (e.g.
    "What is X?" vs "what is x"), which an exact-string check misses.
    Deliberately NOT a semantic/embedding-based check — that would need a
    model call and introduce its own nondeterminism into what should be
    a fast, offline quality gate.
    """
    lowered = query.lower().strip()
    no_punct = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", "", lowered)
    return re.sub(r"\s+", " ", no_punct).strip()


def find_exact_duplicates(questions: list[dict]) -> list[list[str]]:
    by_query: dict[str, list[str]] = {}
    for q in questions:
        by_query.setdefault(q["query"].strip(), []).append(q["id"])
    return [ids for ids in by_query.values() if len(ids) > 1]


def find_normalized_duplicates(questions: list[dict]) -> list[list[str]]:
    by_normalized: dict[str, list[str]] = {}
    for q in questions:
        by_normalized.setdefault(normalize_query(q["query"]), []).append(q["id"])
    return [ids for ids in by_normalized.values() if len(ids) > 1]


def find_dangling_locations(
    questions: list[dict], real_locations: set[tuple[str, str, str]]
) -> list[tuple[str, tuple[str, str, str]]]:
    """A question's expected_location that doesn't correspond to any
    REAL, currently-ingested Qdrant point — "dangling" ground truth that
    would silently make recall unmeasurable for that question (it could
    never be found, correctly or not). real_locations must come from an
    actual scroll of a real collection, never assumed.
    """
    dangling = []
    for q in questions:
        for loc in q.get("expected_locations", []):
            key = (loc[0], loc[1], loc[2])
            if key not in real_locations:
                dangling.append((q["id"], key))
    return dangling


def language_pair_counts(questions: list[dict]) -> dict[tuple[str, str], int]:
    counter = Counter(
        (q["query_lang"], q["content_lang"]) for q in questions if q.get("content_lang")
    )
    return dict(counter)


def validate_golden_set(
    questions: list[dict], real_locations: set[tuple[str, str, str]]
) -> ValidationReport:
    not_found = [q for q in questions if q.get("expect_not_found")]
    total = len(questions)
    return ValidationReport(
        exact_duplicate_queries=find_exact_duplicates(questions),
        normalized_duplicate_queries=find_normalized_duplicates(questions),
        dangling_locations=find_dangling_locations(questions, real_locations),
        language_pair_counts=language_pair_counts(questions),
        not_found_count=len(not_found),
        not_found_ratio=len(not_found) / total if total else 0.0,
        total_questions=total,
    )
