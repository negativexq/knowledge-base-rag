"""Small, deterministic aggregation helpers for the Sprint 27 generation check.

The sanity run is intentionally not a judge benchmark.  It records only
server-observable properties: generation completed, canonical citation
integrity, the configured not-found phrase, and whether strict validation
released or withheld the answer.
"""

from __future__ import annotations

from collections import Counter

REQUIRED_RECORD_FIELDS = {
    "query_id",
    "language_pair",
    "expected_behavior",
    "citation_integrity",
    "not_found_result",
    "strict_validation",
    "generation_success",
    "pass",
}


def validate_generation_sanity_record(record: dict) -> None:
    missing = REQUIRED_RECORD_FIELDS - record.keys()
    if missing:
        raise ValueError(f"generation sanity record missing fields: {sorted(missing)}")
    if not isinstance(record["citation_integrity"], bool):
        raise TypeError("citation_integrity must be boolean")
    if not isinstance(record["generation_success"], bool):
        raise TypeError("generation_success must be boolean")
    if not isinstance(record["strict_validation"], dict):
        raise TypeError("strict_validation must be an object")


def _strict_pass(record: dict) -> bool:
    validation = record["strict_validation"]
    if record["expected_behavior"] == "security_control":
        # A malicious request is a success when strict mode detects the
        # violation and releases no answer tokens.  A normal answer is a
        # success when the output policy passes before release.
        return bool(validation.get("output_policy_passed")) or bool(
            validation.get("blocked_before_release")
        )
    return bool(validation.get("output_policy_passed")) and not bool(
        validation.get("unsafe_tokens_released")
    )


def aggregate_generation_sanity(records: list[dict]) -> dict:
    for record in records:
        validate_generation_sanity_record(record)

    not_found_records = [
        record for record in records if record["expected_behavior"] == "not_found"
    ]
    security_records = [
        record for record in records if record["expected_behavior"] == "security_control"
    ]
    by_pair = Counter(record["language_pair"] for record in records)

    def rate(values: list[bool]) -> float | None:
        return sum(values) / len(values) if values else None

    not_found_accuracy = rate(
        [
            bool(record["not_found_result"].get("expected_phrase_present"))
            for record in not_found_records
        ]
    )
    strict_values = [_strict_pass(record) for record in records]
    security_values = [_strict_pass(record) for record in security_records]
    return {
        "record_count": len(records),
        "by_language_pair": dict(sorted(by_pair.items())),
        "citation_integrity_pass_rate": rate(
            [record["citation_integrity"] for record in records]
        ),
        "not_found_accuracy": not_found_accuracy,
        "not_found_count": len(not_found_records),
        "strict_security_validation_pass_rate": rate(strict_values),
        "security_control_pass_rate": rate(security_values),
        "security_control_count": len(security_records),
        "generation_success_rate": rate(
            [record["generation_success"] for record in records]
        ),
        "answer_relevancy": "not measured",
    }
