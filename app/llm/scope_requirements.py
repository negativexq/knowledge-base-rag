"""Positive coverage of question-quoted restrictions, separate from transcription."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.scope_diagnostics import DiagnosticScopeJudgment
from app.llm.scope_validation import LineScopeJudgment, LineWitness, resolve_line_judgment


class RequirementBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_index: int = Field(ge=0, description="Zero-based index in question_requirements")
    verdict: Literal["supported", "mismatch", "unknown"]
    binding_basis: Literal[
        "explicit", "linguistic_equivalence", "source_relationship", "unestablished"
    ]
    claim_indexes: list[int] = Field(min_length=1, max_length=50)
    witnesses: list[LineWitness] = Field(default_factory=list, max_length=12)


class RequiredScopeJudgment(DiagnosticScopeJudgment):
    requirement_bindings: list[RequirementBinding] = Field(max_length=72)


INSTRUCTIONS = """question_requirements contain verbatim restrictions from the question,
not inferred planning values. Return one requirement_bindings entry for every index.
Evaluate them against the answer as a whole, pointing to the applicable claim_indexes.
Supported needs source witnesses for that specific restriction, not merely a nearby
number or title. Distinguish literal support, linguistic equivalents, and a relationship
established by source evidence. Geographic containment, category membership and an
object's position are relationships, not linguistic equivalents. Outside knowledge or
an application proof's generated label cannot establish a source relationship.
If a port/range, object location, category or inventory scope conflicts, do not approve
the answer because a different part of the question was satisfied. Missing evidence
is unknown, not mismatch or verified absence. This adds no answer-writing stage.
"""


def range_conflicts(question: str, claims: list[dict[str, Any]]) -> bool:
    """Check explicit named target ranges against leading answer identities."""
    ranges = re.findall(r"\b([A-Za-z]{2,})\s+(\d+)\s*[-–]\s*(\d+)\b", question)
    for unit, lower, upper in ranges:
        singular = unit.casefold().removesuffix("s")
        for claim in claims:
            match = re.match(
                r"(?:the\s+)?" + re.escape(singular) + r"s?\s+(\d+)\b", claim["claim"]["text"], re.I
            )
            if match and not int(lower) <= int(match[1]) <= int(upper):
                return True
    return False


def validate_requirements(
    payload: dict[str, Any],
    requirements: list[dict[str, str]],
    judgment: RequiredScopeJudgment,
    generated_ids: set[str],
) -> list[str]:
    bindings = {b.requirement_index: b for b in judgment.requirement_bindings}
    if len(bindings) != len(judgment.requirement_bindings) or set(bindings) != set(
        range(len(requirements))
    ):
        return ["SCOPE_REQUIREMENT_COVERAGE_INVALID"]
    errors = []
    for index, requirement in enumerate(requirements):
        binding = bindings[index]
        if binding.verdict != "supported" or binding.binding_basis == "unestablished":
            errors.append("SCOPE_REQUIREMENT_UNRESOLVED")
            continue
        if not binding.witnesses or not set(binding.claim_indexes) <= set(
            range(len(payload["claims"]))
        ):
            errors.append("SCOPE_REQUIREMENT_WITNESS_INVALID")
            continue
        evidence: list[str] = []
        for witness in binding.witnesses:
            claim = next(
                (
                    c
                    for c in payload["claims"]
                    if c["claim_index"] in binding.claim_indexes
                    and witness.support_id in {u["support_unit_id"] for u in c["cited_evidence"]}
                ),
                None,
            )
            if claim is None:
                errors.append("SCOPE_REQUIREMENT_WITNESS_INVALID")
                continue
            try:
                resolved = resolve_line_judgment(
                    payload,
                    LineScopeJudgment.model_validate(
                        dict(
                            checks=[
                                dict(
                                    claim_index=claim["claim_index"],
                                    verdict="supported",
                                    reason="NONE",
                                    witnesses=[witness.model_dump()],
                                )
                            ]
                        )
                    ),
                )
                if witness.support_id not in generated_ids:
                    evidence.extend(w.quote for w in resolved.checks[0].witnesses)
            except ValueError:
                errors.append("SCOPE_REQUIREMENT_WITNESS_INVALID")
        if (
            requirement["dimension"] in {"entity", "population"}
            and binding.binding_basis != "linguistic_equivalence"
        ):
            names = set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b", requirement["question_quote"]))
            names -= {"The", "Which", "What", "How", "Please", "According", "For", "All"}
            source = " ".join(evidence).casefold()
            if any(name.casefold() not in source for name in names):
                errors.append("SCOPE_NAMED_ENTITY_RELATION_UNGROUNDED")
    return list(dict.fromkeys(errors))
