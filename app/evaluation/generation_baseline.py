"""Deterministic scoring helpers for the Phase 7 generation smoke.

These helpers intentionally do not call a judge model. They score only facts,
sources, citations, and output-policy results that the repository can verify
without importing outside knowledge. Anything requiring semantic claim
entailment is explicitly left for manual review.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from app.llm.grounding import check_grounding
from app.retrieval.hybrid_search import SearchResult

SMOKE_CATEGORY_PLAN: tuple[tuple[str, int, str | None], ...] = (
    ("multi_document", 3, None),
    ("cross_lingual", 3, "tr->en"),
    ("cross_lingual", 3, "en->tr"),
    ("version_conflict", 2, None),
    ("injection_bearing", 2, None),
    ("standard_answerable", 6, None),
    ("hard_answerable", 6, None),
    ("unanswerable", 4, None),
    ("acl_negative", 3, None),
    ("ambiguous", 4, None),
)

_TOKEN_RE = re.compile(r"[\w%:.-]+", re.UNICODE)
_GENERIC_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "do",
    "for",
    "from",
    "how",
    "is",
    "it",
    "must",
    "of",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "which",
    "with",
    "within",
    "ve",
    "bir",
    "birlikte",
    "için",
    "ile",
    "mı",
    "mi",
    "nedir",
    "ne",
    "olan",
    "veya",
}

_SMOKE_PREFERRED_IDS: dict[str, tuple[str, ...]] = {
    # These are the canonical complete multi-document development records
    # used by the Phase 6 analysis; keeping them here makes the Phase 7
    # stress slice about generation synthesis, not a different retrieval mix.
    "multi_document": ("multi-00-1", "multi-00-3", "multi-03-0"),
    "injection_bearing": ("injection-03-0", "injection-03-1"),
}


def select_generation_smoke_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select the same 36 development questions deterministically every run."""
    selected: list[dict[str, Any]] = []
    for category, count, language_pair in SMOKE_CATEGORY_PLAN:
        matches = [
            question
            for question in questions
            if question["category"] == category
            and (language_pair is None or question["language_pair"] == language_pair)
        ]
        if len(matches) < count:
            raise ValueError(
                f"generation smoke needs {count} {category} records "
                f"for {language_pair or 'all pairs'}, found {len(matches)}"
            )
        preferred = [
            question
            for preferred_id in _SMOKE_PREFERRED_IDS.get(category, ())
            for question in matches
            if question["id"] == preferred_id
        ]
        remaining = [question for question in matches if question not in preferred]
        selected.extend((preferred + sorted(remaining, key=lambda item: item["id"]))[:count])
    selected.sort(key=lambda item: item["id"])
    if len({question["id"] for question in selected}) != len(selected):
        raise ValueError("generation smoke selection contains duplicate question IDs")
    return selected


def behavioral_bucket(question: dict[str, Any], all_required_present: bool) -> str:
    if question["answerability"] == "ambiguous":
        return "SHOULD_CLARIFY"
    if question["answerability"] == "unanswerable":
        return "SHOULD_ABSTAIN"
    if not all_required_present:
        return "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL"
    return "SHOULD_ANSWER"


def safe_chunk_payload(chunk: SearchResult) -> dict[str, Any]:
    payload = chunk.payload
    return {
        "chunk_id": chunk.id or payload.get("chunk_id", ""),
        "source_id": payload.get("source_id"),
        "content": payload.get("text", ""),
        "metadata": {
            key: payload.get(key)
            for key in (
                "source_type",
                "title",
                "source_name",
                "heading_path",
                "heading_occurrence",
                "page_number",
                "paragraph_index",
                "authority_role",
                "authority_scope",
                "document_version",
                "effective_date",
                "version",
                "canonical",
            )
            if payload.get(key) is not None
        },
    }


def build_cache_record(
    question: dict[str, Any],
    chunks: list[SearchResult],
    *,
    pre_acl_candidate_count: int | None,
    authorized_candidate_count: int | None,
    retrieval_ms: float,
    deterministic_reason: str | None,
) -> dict[str, Any]:
    source_ids = [chunk.payload.get("source_id") for chunk in chunks]
    required_sources = set(question.get("required_evidence", []))
    expected_sources = set(question.get("expected_source_ids", []))
    all_required_present = bool(required_sources) and required_sources <= set(source_ids)
    gold_present = bool(expected_sources & set(source_ids))
    if not expected_sources:
        all_required_present = False
        gold_present = False
    return {
        "query_id": question["id"],
        "case_family": question["case_family"],
        "category": question["category"],
        "split": question["split"],
        "answerability": question["answerability"],
        "query_language": question["query_language"],
        "evidence_language": question["evidence_language"],
        "language_pair": question["language_pair"],
        "query": question["question"],
        "authorized_top5": [safe_chunk_payload(chunk) for chunk in chunks],
        "gold_present": gold_present,
        "all_required_present": all_required_present,
        "behavioral_bucket": behavioral_bucket(question, all_required_present),
        "retrieval": {
            "pre_acl_candidate_count": pre_acl_candidate_count,
            "authorized_candidate_count": authorized_candidate_count,
            "returned_authorized_top5": len(chunks),
            "retrieval_ms": round(retrieval_ms, 3),
            "deterministic_reason": deterministic_reason,
        },
    }


def chunks_from_cache(record: dict[str, Any]) -> list[SearchResult]:
    """Reconstruct only authorized chunks for the real generation function."""
    return [
        SearchResult(
            score=0.0,
            id=item["chunk_id"],
            payload={
                **item["metadata"],
                "source_id": item["source_id"],
                "text": item["content"],
                "chunk_id": item["chunk_id"],
            },
        )
        for item in record["authorized_top5"]
    ]


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize(text))


def expected_components(expected_answer: str | None) -> list[str]:
    if not expected_answer:
        return []
    return [component.strip() for component in expected_answer.split(";") if component.strip()]


def _component_match(component: str, answer: str) -> bool:
    normalized_answer = _normalize(answer)
    normalized_component = _normalize(component).strip()
    if normalized_component in normalized_answer:
        return True
    tokens = [
        token
        for token in _tokens(component)
        if token not in _GENERIC_WORDS
        and (len(token) >= 4 or any(char.isdigit() for char in token))
    ]
    return bool(tokens) and all(token in _tokens(answer) for token in tokens)


def deterministic_correctness(question: dict[str, Any], answer: str) -> dict[str, Any]:
    components = expected_components(question.get("expected_answer"))
    if not components:
        return {"status": "NOT_APPLICABLE", "covered": 0, "total": 0, "components": []}
    covered = [_component_match(component, answer) for component in components]
    return {
        "status": "PASS" if all(covered) else "FAIL",
        "covered": sum(covered),
        "total": len(covered),
        "components": covered,
        "method": "normalized_expected_answer_components",
    }


def _cited_source_ids(citations: list[tuple[str, str, str]]) -> set[str]:
    return {source_id for _, source_id, _ in citations}


def score_generation(
    question: dict[str, Any],
    record: dict[str, Any],
    answer: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    chunks = chunks_from_cache(record)
    grounding = check_grounding(answer, chunks)
    grounding_event = next((event for event in events if event.get("type") == "grounding"), None)
    # In strict v3 mode an invalid raw answer is withheld, so the released
    # answer may be empty even though the grounding event still contains the
    # exact citations the model emitted. Score those citations from the
    # runtime event rather than silently turning a malformed answer into a
    # citation pass.
    emitted_citations = (
        grounding_event.get("citations_found", grounding.citations_found)
        if grounding_event
        else grounding.citations_found
    )
    emitted_ungrounded = (
        grounding_event.get("ungrounded_citations", grounding.ungrounded_citations)
        if grounding_event
        else grounding.ungrounded_citations
    )
    emitted_citations_valid = (
        grounding_event.get("citations_valid") if grounding_event else None
    )
    # ``stream_answer`` deliberately keeps the grounding event compact and
    # does not include ``citations_valid``.  The event's ungrounded list is
    # authoritative for the citations emitted by the raw model response,
    # including responses withheld by strict output validation.
    if emitted_citations_valid is None:
        emitted_citations_valid = not emitted_ungrounded
    security_event = next(
        (event for event in events if event.get("type") == "security_validation"),
        None,
    )
    error_event = next((event for event in events if event.get("type") == "error"), None)
    expected_sources = set(question.get("expected_source_ids", []))
    supporting_sources = set(question.get("supporting_source_ids", []))
    cited_sources = _cited_source_ids(emitted_citations)
    allowed_support_sources = expected_sources | supporting_sources
    required_sources = set(question.get("required_evidence", []))
    components = deterministic_correctness(question, answer)
    validation_passed = security_event.get("passed") if security_event else None
    if not chunks:
        validation_passed = security_event.get("passed") if security_event else None
    if error_event:
        failure_type = "OUTPUT_VALIDATION_FAILURE"
    elif not answer and question["answerability"] == "answerable":
        failure_type = "GENERATION_PROVIDER_FAILURE"
    elif not emitted_citations_valid:
        failure_type = "CITATION_INVALID"
    elif components["status"] == "FAIL":
        failure_type = "ANSWER_INCORRECT"
    elif components["covered"] < components["total"]:
        failure_type = "ANSWER_INCOMPLETE"
    else:
        failure_type = None
    required_sources_cited = len(required_sources & cited_sources)
    citation_completeness = (
        required_sources_cited / len(required_sources) if required_sources else None
    )
    return {
        "query_id": question["id"],
        "case_family": question["case_family"],
        "category": question["category"],
        "language_pair": question["language_pair"],
        "query": question["question"],
        "answerability": question["answerability"],
        "gold_present": record["gold_present"],
        "all_required_present": record["all_required_present"],
        "expected_source_ids": sorted(expected_sources),
        "answer": answer,
        "events": events,
        "correctness": components,
        "required_fact_completeness": {
            "covered": components["covered"],
            "total": components["total"],
            "method": "authored_expected_answer_semicolon_components",
        },
        "citations": {
            "found": emitted_citations,
            "unknown_or_unauthorized": emitted_ungrounded,
            "valid": emitted_citations_valid,
            "support_correct": (
                bool(cited_sources) and cited_sources <= allowed_support_sources
                if expected_sources or supporting_sources
                else None
            ),
            "required_sources_cited": required_sources_cited,
            "required_sources_total": len(required_sources),
            "completeness": citation_completeness,
        },
        "output_validation": {
            "passed": validation_passed,
            "violations": security_event.get("violations", []) if security_event else [],
            "error": error_event,
        },
        "unsupported_claims": {"status": "REQUIRES_REVIEW", "count": None},
        "authority_selection": {"status": "REQUIRES_REVIEW"},
        "language_appropriateness": {"status": "REQUIRES_REVIEW"},
        "failure": failure_type,
        "manual_review_required": question["answerability"] == "answerable",
    }


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    generated = [result for result in results if result.get("answer") or result.get("events")]
    gold_present = [
        result
        for result in results
        if result["answerability"] == "answerable" and result["all_required_present"]
    ]
    correct = [result for result in gold_present if result["correctness"]["status"] == "PASS"]
    complete = [
        result
        for result in gold_present
        if result["required_fact_completeness"]["covered"]
        == result["required_fact_completeness"]["total"]
    ]
    validation = [
        result for result in generated if result["output_validation"]["passed"] is not None
    ]
    valid_citations = [result for result in generated if result["citations"]["valid"]]
    support_checked = [
        result for result in generated if result["citations"]["support_correct"] is not None
    ]
    unsupported_review = [
        result
        for result in gold_present
        if result["unsupported_claims"]["status"] == "REQUIRES_REVIEW"
    ]

    def rate(count: int, denominator: int) -> float | None:
        return round(count / denominator, 6) if denominator else None

    return {
        "record_count": len(results),
        "generated_record_count": len(generated),
        "answerable_count": sum(result["answerability"] == "answerable" for result in results),
        "gold_present_answerable_count": len(gold_present),
        "correct_answer": {
            "count": len(correct),
            "denominator": len(gold_present),
            "rate": rate(len(correct), len(gold_present)),
        },
        "fully_complete_answer": {
            "count": len(complete),
            "denominator": len(gold_present),
            "rate": rate(len(complete), len(gold_present)),
        },
        "gold_present_answer_success": {
            "count": None,
            "denominator": len(gold_present),
            "rate": None,
            "status": "REQUIRES_REVIEW_FOR_CLAIM_SUPPORT",
        },
        "unsupported_claims": {
            "answer_count": None,
            "denominator": len(gold_present),
            "rate": None,
            "manual_review_count": len(unsupported_review),
            "status": "REQUIRES_REVIEW",
        },
        "citation_validity": {
            "count": len(valid_citations),
            "denominator": len(generated),
            "rate": rate(len(valid_citations), len(generated)),
        },
        "citation_support_correctness": {
            "count": sum(
                result["citations"]["support_correct"] is True for result in support_checked
            ),
            "denominator": len(support_checked),
            "rate": rate(
                sum(result["citations"]["support_correct"] is True for result in support_checked),
                len(support_checked),
            ),
        },
        "citation_completeness": {
            "measured": [
                result["citations"]["completeness"]
                for result in generated
                if result["citations"]["completeness"] is not None
            ]
        },
        "output_validation": {
            "count": sum(result["output_validation"]["passed"] is True for result in validation),
            "denominator": len(validation),
            "rate": rate(
                sum(result["output_validation"]["passed"] is True for result in validation),
                len(validation),
            ),
        },
        "failure_counts": dict(
            sorted(Counter(result["failure"] for result in results if result["failure"]).items())
        ),
        "manual_review_count": len(unsupported_review),
    }


def summarize_latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(values)
    return {
        "count": len(values),
        "p50_ms": round(ordered[round(0.50 * (len(ordered) - 1))], 3),
        "p95_ms": round(ordered[round(0.95 * (len(ordered) - 1))], 3),
        "max_ms": round(max(values), 3),
    }
