"""Opt-in generation observability for evaluation artifacts.

The application deliberately does not persist raw model output by default.
Callers that explicitly create a :class:`GenerationObservation` (for example,
an offline benchmark) can receive the raw candidate and the distinct
validator/user-visible outcomes without changing the strict release gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.grounding import GroundingResult
from app.llm.output_policy import OutputPolicyResult
from app.shared.config import SecurityValidationMode


def normalize_validator_failure_codes(violations: list[str]) -> list[str]:
    """Map internal policy violation names to stable evaluation codes."""
    mapping = {
        "unauthorized_citation": "UNAUTHORIZED_CITATION_ID",
        "citation_suppression": "CITATION_SUPPRESSION",
        "hidden_policy_disclosure": "OTHER_VALIDATION_FAILURE",
        "output_schema_failure": "OUTPUT_SCHEMA_FAILURE",
    }
    codes: list[str] = []
    for violation in violations:
        code = mapping.get(violation, "OTHER_VALIDATION_FAILURE")
        if code not in codes:
            codes.append(code)
    return codes


@dataclass
class GenerationObservation:
    """In-memory capture that is inert unless a caller opts into it."""

    raw_candidate_available: bool = False
    raw_candidate_output: str | None = None
    validator_input_available: bool = False
    validator_pass: bool | None = None
    validator_failure_codes: list[str] = field(default_factory=list)
    validated_output_available: bool = False
    user_visible_output_available: bool = False
    citations_extracted_from_raw: list[tuple[str, str, str]] = field(default_factory=list)
    citations_extracted_from_validated: list[tuple[str, str, str]] = field(default_factory=list)
    structured_candidate: dict[str, Any] | None = None
    validated_output: str | None = None
    pipeline_version: str = "pipeline_v1"
    output_contract_version: str = "legacy"
    validated_answer_parts: list[dict[str, Any]] = field(default_factory=list)
    rejected_answer_parts: list[dict[str, Any]] = field(default_factory=list)
    model_abstention: bool | None = None
    application_forced_abstention: bool = False

    def record(
        self,
        answer: str,
        grounding: GroundingResult,
        output_policy: OutputPolicyResult | None,
        *,
        prompt_version: str,
        validation_mode: SecurityValidationMode,
    ) -> None:
        """Record candidate/validator boundaries without relaxing delivery."""
        self.raw_candidate_available = True
        self.raw_candidate_output = answer
        self.citations_extracted_from_raw = list(grounding.citations_found)
        if output_policy is None:
            self.validator_input_available = False
            self.validator_pass = None
            self.validated_output_available = True
            self.user_visible_output_available = True
            self.citations_extracted_from_validated = list(grounding.citations_found)
            return

        self.validator_input_available = True
        self.validator_pass = output_policy.passed
        self.validator_failure_codes = normalize_validator_failure_codes(output_policy.violations)
        self.validated_output_available = output_policy.passed
        self.user_visible_output_available = (
            prompt_version != "v3"
            or validation_mode == "fast"
            or output_policy.passed
        )
        if self.validated_output_available:
            self.citations_extracted_from_validated = list(grounding.citations_found)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_candidate_available": self.raw_candidate_available,
            "raw_candidate_output": self.raw_candidate_output,
            "validator_input_available": self.validator_input_available,
            "validator_pass": self.validator_pass,
            "validator_failure_codes": list(self.validator_failure_codes),
            "validated_output_available": self.validated_output_available,
            "user_visible_output_available": self.user_visible_output_available,
            "citations_extracted_from_raw": list(self.citations_extracted_from_raw),
            "citations_extracted_from_validated": list(self.citations_extracted_from_validated),
            "structured_candidate": self.structured_candidate,
            "validated_output": self.validated_output,
            "pipeline_version": self.pipeline_version,
            "output_contract_version": self.output_contract_version,
            "validated_answer_parts": list(self.validated_answer_parts),
            "rejected_answer_parts": list(self.rejected_answer_parts),
            "model_abstention": self.model_abstention,
            "application_forced_abstention": self.application_forced_abstention,
        }
