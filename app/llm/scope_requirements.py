"""Positive coverage of question-quoted restrictions, separate from transcription."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.scope_diagnostics import DiagnosticScopeJudgment
from app.llm.scope_validation import LineScopeJudgment, LineWitness, resolve_line_judgment


class ImageRequirementWitness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_id: str = Field(min_length=1, max_length=100)
    observation: str = Field(min_length=1, max_length=600)


class RequirementBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_index: int = Field(ge=0, description="Zero-based index in question_requirements")
    verdict: Literal["supported", "mismatch", "unknown"]
    binding_basis: Literal[
        "explicit", "linguistic_equivalence", "source_relationship", "unestablished"
    ]
    claim_indexes: list[int] = Field(min_length=1, max_length=50)
    witnesses: list[LineWitness] = Field(default_factory=list, max_length=12)
    image_witnesses: list[ImageRequirementWitness] = Field(default_factory=list, max_length=6)


class RequiredScopeJudgment(DiagnosticScopeJudgment):
    requirement_bindings: list[RequirementBinding] = Field(max_length=72)


INSTRUCTIONS = """question_requirements contain verbatim restrictions from the question,
not inferred planning values. Return one requirement_bindings entry for every index.
For a source_limitation claim, bind the cited source scope and the stated limitation
to the requested entity/metric/period, not a nonexistent positive value. A supported
limitation can describe a known mismatch: return mismatch with original witnesses
for that restriction while supporting the truthful limitation claim itself. Unknown
identity or incomplete inspection still cannot establish a contradiction or absence.
The application never uses such a mismatch to approve a positive requested value. A supported
limitation must have original-source evidence for the actual missing/incompatible
input; incomplete searching alone does not establish absence. An ordinary paraphrase
does not invent a finer measurement than the question or source actually distinguishes.
Evaluate them against the answer as a whole, pointing to the applicable claim_indexes.
Supported needs source witnesses for that specific restriction, not merely a nearby
number or title. Distinguish literal support, linguistic equivalents, and a relationship
established by source evidence. Geographic containment, category membership and an
object's position are relationships, not linguistic equivalents. Outside knowledge or
an application proof's generated label cannot establish a source relationship.
For a requirement established visually, use image_witnesses with a supplied
source_images image_id and a short direct observation of the relevant object and
condition. Inspect the original image; do not repeat the collector's description
as proof. A text witness may establish a textual condition, but generated proof
text alone cannot establish a condition. Do not equate readable labels with a
matching color, location or range. Image witnesses must apply to the listed claims.
If a port/range, object location, category or inventory scope conflicts, do not approve
the answer because a different part of the question was satisfied. Missing evidence
is unknown, not mismatch or verified absence. This adds no answer-writing stage.
For a source-backed explanation rather than a positive requested value, you may
return source_disposition with independently checked object identity, question
binding, witnesses and complete boundaries. Do not require an absent target to
appear in the source first; verify the requested table/legend/section instead.
An unknown positive requirement stays unknown. Only a separate, established
source finding can explain it. A partial view or wrong object cannot close the
question's source scope; report remaining candidates and incomplete scope.
For disposition witnesses and boundaries, use supplied start_line/end_line locators
when available; the application copies the exact source text without model rewriting.
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
    source_images: list[dict[str, Any]] | None = None,
    *,
    diagnostics: dict[str, int] | None = None,
) -> list[str]:
    images = {image["image_id"]: image for image in source_images or []}
    bindings = {b.requirement_index: b for b in judgment.requirement_bindings}
    if len(bindings) != len(judgment.requirement_bindings) or set(bindings) != set(
        range(len(requirements))
    ):
        return ["SCOPE_REQUIREMENT_COVERAGE_INVALID"]
    errors = []
    for index, requirement in enumerate(requirements):
        binding = bindings[index]
        limited_claims = [
            c for c in payload["claims"] if c["claim_index"] in binding.claim_indexes
        ]
        primary = {c.claim_index: c for c in judgment.checks}
        verified_contrast = (
            binding.verdict == "mismatch"
            and bool(limited_claims)
            and all(
                c["claim"].get("answer_kind") == "source_limitation"
                and c["claim_index"] in primary
                and primary[c["claim_index"]].verdict == "supported"
                and primary[c["claim_index"]].reason == "NONE"
                for c in limited_claims
            )
        )
        if (
            binding.verdict != "supported" and not verified_contrast
        ) or binding.binding_basis == "unestablished":
            errors.append("SCOPE_REQUIREMENT_UNRESOLVED")
            continue
        if not (binding.witnesses or binding.image_witnesses) or not set(
            binding.claim_indexes
        ) <= set(range(len(payload["claims"]))):
            errors.append("SCOPE_REQUIREMENT_WITNESS_INVALID")
            continue
        evidence: list[str] = []
        image_evidence: list[str] = []
        for image_witness in binding.image_witnesses:
            image = images.get(image_witness.image_id)
            if image is None or not set(binding.claim_indexes) & set(
                image.get("claim_indexes", [])
            ):
                errors.append("SCOPE_REQUIREMENT_IMAGE_INVALID")
            else:
                image_evidence.append(image_witness.observation)
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
                # An original-image witness is an independent source authority.
                # A malformed optional OCR line on the same claim must not erase
                # it. Unknown support IDs, wrong image/claim bindings and semantic
                # mismatch remain errors; never repair or invent a source quote.
                if image_evidence:
                    if diagnostics is not None:
                        key = "ignored_optional_text_witnesses"
                        diagnostics[key] = diagnostics.get(key, 0) + 1
                else:
                    errors.append("SCOPE_REQUIREMENT_WITNESS_INVALID")
        if requirement["dimension"] == "condition" and not (evidence or image_evidence):
            errors.append("SCOPE_CONDITION_SOURCE_UNGROUNDED")
        # Relationship meaning belongs to the independently grounded scope
        # judgment, not a capitalization heuristic over the question's wording.
        # Table headers, aliases and ordinary capitalized words need not appear
        # verbatim in every witness. Generated proofs alone still cannot bind
        # the requested entity or population (including linguistic equivalents).
        if requirement["dimension"] in {"entity", "population"} and not (
            evidence or image_evidence
        ):
            errors.append("SCOPE_NAMED_ENTITY_RELATION_UNGROUNDED")
    return list(dict.fromkeys(errors))
