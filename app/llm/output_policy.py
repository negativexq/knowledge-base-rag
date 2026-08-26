"""Deterministic, lightweight post-generation policy checks.

This is a release gate for strict mode, not an injection classifier and not
a claim-level grounding system. It checks properties the server can know
without asking another model: prompt disclosure, citation integrity, and
citation suppression when authorized evidence was supplied.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm.grounding import GroundingResult, check_grounding
from app.llm.prompt import NOT_FOUND_PHRASE
from app.retrieval.hybrid_search import SearchResult


@dataclass(frozen=True)
class OutputPolicyResult:
    passed: bool
    violations: list[str]
    hidden_prompt_leaked: bool
    citations_valid: bool
    citation_suppressed: bool
    grounding: GroundingResult

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": self.violations,
            "hidden_prompt_leaked": self.hidden_prompt_leaked,
            "citations_valid": self.citations_valid,
            "citation_suppressed": self.citation_suppressed,
        }


_DISCLOSURE_MARKERS = (
    "system prompt:",
    "hidden policy:",
    "developer message:",
    "system message:",
    "gizli sistem mesajı:",
    "sistem mesajı:",
    "gizli politika:",
)


def check_output_policy(
    answer: str,
    chunks: list[SearchResult],
    system_prompt: str,
) -> OutputPolicyResult:
    grounding = check_grounding(answer, chunks)
    normalized = answer.casefold()
    normalized_prompt = system_prompt.strip().casefold()
    hidden_prompt_leaked = bool(normalized_prompt and normalized_prompt in normalized)
    disclosure_marker = any(marker in normalized for marker in _DISCLOSURE_MARKERS)
    citation_suppressed = bool(chunks) and (
        not grounding.has_citations and NOT_FOUND_PHRASE.casefold() not in normalized
    )

    violations: list[str] = []
    if hidden_prompt_leaked or disclosure_marker:
        violations.append("hidden_policy_disclosure")
    if not grounding.citations_valid:
        violations.append("unauthorized_citation")
    if citation_suppressed:
        violations.append("citation_suppression")

    return OutputPolicyResult(
        passed=not violations,
        violations=violations,
        hidden_prompt_leaked=hidden_prompt_leaked or disclosure_marker,
        citations_valid=grounding.citations_valid,
        citation_suppressed=citation_suppressed,
        grounding=grounding,
    )
