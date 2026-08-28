"""Pipeline v2 structured answer contract and claim-level validation."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.evaluation.critical_values import critical_value_status
from app.llm.grounding import (
    GroundingResult,
    check_grounding,
    citation_identity_status,
    extract_citations,
)
from app.llm.observability import GenerationObservation, normalize_validator_failure_codes
from app.llm.output_policy import check_output_policy
from app.llm.prompt import NOT_FOUND_PHRASE, build_messages, load_system_prompt
from app.llm.provider import ChatProvider
from app.llm.support_units import (
    SupportUnit,
    build_support_units,
    serialize_support_units,
    support_unit_map,
)
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import SecurityValidationMode
from app.shared.tracing import get_tracer

STRUCTURED_OUTPUT_CONTRACT_VERSION = "output_contract_v2"
PIPELINE_VERSION = "pipeline_v2_section_claims"
HARDENED_OUTPUT_CONTRACT_VERSION = "output_contract_v2_1"
HARDENED_PIPELINE_VERSION = "pipeline_v2_1_hardened"
EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION = "output_contract_v2_2"
EVIDENCE_BACKED_PIPELINE_VERSION = "pipeline_v2_2_evidence_backed"
SUPPORT_UNIT_OUTPUT_CONTRACT_VERSION = "output_contract_v2_3"
SUPPORT_UNIT_PIPELINE_VERSION = "pipeline_v2_3_support_units"
SUPPORT_UNIT_PATTERN_OUTPUT_CONTRACT_VERSION = "output_contract_v2_3_1"
SUPPORT_UNIT_PATTERN_PIPELINE_VERSION = "pipeline_v2_3_1_support_units_pattern"
SUPPORT_UNIT_BOUNDED_OUTPUT_CONTRACT_VERSION = "output_contract_v2_3_2"
SUPPORT_UNIT_BOUNDED_PIPELINE_VERSION = "pipeline_v2_3_2_support_units_bounded_output"
SUPPORT_UNIT_MAX_OUTPUT_TOKENS = 1024

STRUCTURED_OUTPUT_INSTRUCTIONS = """
Return only a JSON object with this exact shape:
{"answer_parts":[{"text":"...","citations":["[s.filesystem:source/location]"]}],"abstain":false}
Each answer_part must be one independently supportable final factual claim or answer component.
Use only the provided authorized evidence. Attach only citations that directly support
that answer_part. Use an exact value from the server-generated canonical_citations
array in the evidence metadata; do not reconstruct or abbreviate citation locations.
If the evidence is insufficient for a material answer, return {"answer_parts":[],"abstain":true}.
Do not include markdown fences, commentary, planning, or hidden reasoning.
""".strip()

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text", "citations"],
            },
        },
        "abstain": {"type": "boolean"},
    },
    "required": ["answer_parts", "abstain"],
}

HARDENED_OUTPUT_INSTRUCTIONS = """
Return only a JSON object with this exact shape:
{"answer_parts":[{"text":"...","evidence_ids":["E1"]}],"abstain":false}
Use only the provided authorized evidence. Every answer_part must be directly
supported by at least one cited evidence block, and must use exact response-local
evidence IDs from the server-generated metadata (E1, E2, ...). Do not reconstruct
source names or chunk IDs. If the evidence does not directly support a material
answer, return {"answer_parts":[],"abstain":true,"reason_code":"INSUFFICIENT_EVIDENCE"}.
Do not answer from general knowledge, infer missing policy values, fill gaps from
plausibility, include markdown fences, or reveal planning/hidden reasoning.
""".strip()

HARDENED_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer_parts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence_ids"],
            },
        },
        "abstain": {"type": "boolean"},
        "reason_code": {"type": "string", "enum": ["INSUFFICIENT_EVIDENCE"]},
    },
    "required": ["answer_parts", "abstain"],
}

EVIDENCE_BACKED_OUTPUT_INSTRUCTIONS = """
Return only a JSON object with this exact shape:
{"answer_parts":[{"text":"...","evidence":[
  {"evidence_id":"E1","quote":"exact text copied from E1"}
]}],"abstain":false}
Use only the provided authorized evidence. Every answer_part must include at least
one exact supporting quote copied from its cited evidence block. Do not invent or
paraphrase quotes, cite merely related evidence, answer from general knowledge,
infer missing policy values, or fill gaps from plausibility. If no material claim
can be directly supported by an exact evidence quote, return
{"answer_parts":[],"abstain":true,"reason_code":"INSUFFICIENT_EVIDENCE"}.
Do not include markdown fences, commentary, planning, or hidden reasoning.
""".strip()

EVIDENCE_BACKED_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer_parts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "evidence_id": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["evidence_id", "quote"],
                        },
                    },
                },
                "required": ["text", "evidence"],
            },
        },
        "abstain": {"type": "boolean"},
        "reason_code": {"type": "string", "enum": ["INSUFFICIENT_EVIDENCE"]},
    },
    "required": ["answer_parts", "abstain"],
}

SUPPORT_UNIT_OUTPUT_INSTRUCTIONS = """
Return only JSON with this shape:
{"answer_parts":[{"text":"...","support_ids":["E1.U1"]}],"abstain":false}
Use only the provided authorized support units. Every answer_part must include one
or more support_ids from the supplied list. Do not invent IDs or answer from general
knowledge. If a material claim has no directly supporting unit, omit that claim; if
no material claim can be supported, return {"answer_parts":[],"abstain":true}.
Do not include reasoning, planning, or markdown fences.
""".strip()


@dataclass(frozen=True)
class AnswerPart:
    text: str
    citations: list[str]


@dataclass(frozen=True)
class StructuredAnswer:
    answer_parts: list[AnswerPart]
    abstain: bool


@dataclass(frozen=True)
class StructuredValidation:
    parsed: StructuredAnswer | None
    valid_parts: list[AnswerPart]
    rejected_parts: list[dict[str, Any]]
    failure_codes: list[str]
    top_level_valid: bool
    abstain: bool


@dataclass(frozen=True)
class HardenedAnswerPart:
    text: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class HardenedAnswer:
    answer_parts: list[HardenedAnswerPart]
    abstain: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class HardenedValidation:
    parsed: HardenedAnswer | None
    valid_parts: list[HardenedAnswerPart]
    rejected_parts: list[dict[str, Any]]
    failure_codes: list[str]
    top_level_valid: bool
    abstain: bool


@dataclass(frozen=True)
class EvidenceQuote:
    evidence_id: str
    quote: str


@dataclass(frozen=True)
class EvidenceBackedAnswerPart:
    text: str
    evidence: list[EvidenceQuote]


@dataclass(frozen=True)
class EvidenceBackedAnswer:
    answer_parts: list[EvidenceBackedAnswerPart]
    abstain: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class EvidenceBackedValidation:
    parsed: EvidenceBackedAnswer | None
    valid_parts: list[EvidenceBackedAnswerPart]
    rejected_parts: list[dict[str, Any]]
    failure_codes: list[str]
    top_level_valid: bool
    model_abstain: bool
    application_abstain: bool


@dataclass(frozen=True)
class SupportUnitAnswerPart:
    text: str
    support_ids: list[str]


@dataclass(frozen=True)
class SupportUnitAnswer:
    answer_parts: list[SupportUnitAnswerPart]
    abstain: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class SupportUnitValidation:
    parsed: SupportUnitAnswer | None
    valid_parts: list[SupportUnitAnswerPart]
    rejected_parts: list[dict[str, Any]]
    failure_codes: list[str]
    top_level_valid: bool
    model_abstain: bool
    application_abstain: bool


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].strip().lower() in {"```", "```json"}:
            return "\n".join(lines[1:-1]).strip()
    return text


def parse_hardened_answer(raw: str) -> HardenedAnswer:
    value = json.loads(_strip_json_fence(raw))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON must be an object")
    if set(value) - {"answer_parts", "abstain", "reason_code"}:
        raise ValueError("unknown top-level field")
    parts = value.get("answer_parts")
    abstain = value.get("abstain")
    if not isinstance(parts, list) or not isinstance(abstain, bool):
        raise ValueError("answer_parts must be a list and abstain must be boolean")
    reason = value.get("reason_code")
    if reason is not None and reason != "INSUFFICIENT_EVIDENCE":
        raise ValueError("unknown reason_code")
    parsed: list[HardenedAnswerPart] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or set(part) != {"text", "evidence_ids"}:
            raise ValueError(f"answer_parts[{index}] has invalid fields")
        if not isinstance(part["text"], str) or not isinstance(part["evidence_ids"], list):
            raise ValueError(f"answer_parts[{index}] has invalid values")
        if not all(isinstance(item, str) for item in part["evidence_ids"]):
            raise ValueError(f"answer_parts[{index}] has invalid evidence IDs")
        parsed.append(HardenedAnswerPart(part["text"].strip(), list(part["evidence_ids"])))
    if abstain and parsed:
        raise ValueError("abstain=true cannot carry answer parts")
    return HardenedAnswer(parsed, abstain, reason)


def _evidence_map(chunks: list[SearchResult]) -> dict[str, SearchResult]:
    return {
        str(chunk.payload.get("evidence_id", f"E{index}")): chunk
        for index, chunk in enumerate(chunks, 1)
    }


def validate_hardened_answer(
    answer: HardenedAnswer, chunks: list[SearchResult]
) -> HardenedValidation:
    evidence = _evidence_map(chunks)
    if answer.abstain:
        return HardenedValidation(answer, [], [], [], True, True)
    if not answer.answer_parts:
        return HardenedValidation(answer, [], [], ["ABSTAIN_CONTRACT_INVALID"], True, False)
    valid: list[HardenedAnswerPart] = []
    rejected: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, part in enumerate(answer.answer_parts):
        part_codes: list[str] = []
        if not part.text:
            part_codes.append("ANSWER_PART_SCHEMA_INVALID")
        if not part.evidence_ids:
            part_codes.append("EMPTY_EVIDENCE_LIST")
        unknown = [item for item in part.evidence_ids if item not in evidence]
        if unknown:
            part_codes.append("UNKNOWN_EVIDENCE_ID")
        if part_codes:
            unique = sorted(set(part_codes))
            rejected.append(
                {
                    "part_index": index,
                    "text": part.text,
                    "evidence_ids": list(part.evidence_ids),
                    "failure_codes": unique,
                    "survived": False,
                }
            )
            codes.extend(unique)
        else:
            valid.append(part)
    return HardenedValidation(answer, valid, rejected, sorted(set(codes)), True, False)


def normalize_evidence_quote(value: str) -> str:
    """Normalize only representation noise for exact quote containment."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split())


def parse_evidence_backed_answer(raw: str) -> EvidenceBackedAnswer:
    value = json.loads(_strip_json_fence(raw))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON must be an object")
    if set(value) - {"answer_parts", "abstain", "reason_code"}:
        raise ValueError("unknown top-level field")
    parts = value.get("answer_parts")
    abstain = value.get("abstain")
    if not isinstance(parts, list) or not isinstance(abstain, bool):
        raise ValueError("answer_parts must be a list and abstain must be boolean")
    reason = value.get("reason_code")
    if reason is not None and reason != "INSUFFICIENT_EVIDENCE":
        raise ValueError("unknown reason_code")
    parsed: list[EvidenceBackedAnswerPart] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or set(part) != {"text", "evidence"}:
            raise ValueError(f"answer_parts[{index}] has invalid fields")
        if not isinstance(part["text"], str) or not isinstance(part["evidence"], list):
            raise ValueError(f"answer_parts[{index}] has invalid values")
        evidence: list[EvidenceQuote] = []
        for evidence_index, item in enumerate(part["evidence"]):
            if not isinstance(item, dict) or set(item) != {"evidence_id", "quote"}:
                raise ValueError(
                    f"answer_parts[{index}].evidence[{evidence_index}] has invalid fields"
                )
            if not isinstance(item["evidence_id"], str) or not isinstance(item["quote"], str):
                raise ValueError(
                    f"answer_parts[{index}].evidence[{evidence_index}] has invalid values"
                )
            evidence.append(EvidenceQuote(item["evidence_id"].strip(), item["quote"]))
        parsed.append(EvidenceBackedAnswerPart(part["text"].strip(), evidence))
    if abstain and parsed:
        raise ValueError("abstain=true cannot carry answer parts")
    return EvidenceBackedAnswer(parsed, abstain, reason)


def support_unit_output_schema(units: list[SupportUnit]) -> dict[str, Any]:
    """Build a request-scoped schema that constrains IDs, without claiming entailment."""
    support_ids = [unit.support_unit_id for unit in units]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer_parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "support_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": support_ids},
                        },
                    },
                    "required": ["text", "support_ids"],
                },
            },
            "abstain": {"type": "boolean"},
        },
        "required": ["answer_parts", "abstain"],
    }


def support_unit_pattern_output_schema() -> dict[str, Any]:
    """Diagnostic schema with structural IDs; membership stays app-validated.

    This is intentionally not the production V2.3 schema.  It isolates the
    cost of a request-scoped enum from the support-unit contract itself.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer_parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "support_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": r"^E[1-9][0-9]*\.U[1-9][0-9]*$",
                            },
                        },
                    },
                    "required": ["text", "support_ids"],
                },
            },
            "abstain": {"type": "boolean"},
        },
        "required": ["answer_parts", "abstain"],
    }
def parse_support_unit_answer(raw: str) -> SupportUnitAnswer:
    value = json.loads(_strip_json_fence(raw))
    if not isinstance(value, dict) or set(value) - {"answer_parts", "abstain", "reason_code"}:
        raise ValueError("invalid support-unit top-level object")
    parts = value.get("answer_parts")
    abstain = value.get("abstain")
    if not isinstance(parts, list) or not isinstance(abstain, bool):
        raise ValueError("invalid support-unit answer fields")
    reason = value.get("reason_code")
    if reason is not None and reason != "INSUFFICIENT_EVIDENCE":
        raise ValueError("unknown support-unit reason")
    parsed: list[SupportUnitAnswerPart] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or set(part) != {"text", "support_ids"}:
            raise ValueError(f"invalid support-unit part {index}")
        if not isinstance(part["text"], str) or not isinstance(part["support_ids"], list):
            raise ValueError(f"invalid support-unit values {index}")
        if not all(isinstance(item, str) for item in part["support_ids"]):
            raise ValueError(f"invalid support-unit IDs {index}")
        parsed.append(SupportUnitAnswerPart(part["text"].strip(), list(part["support_ids"])))
    if abstain and parsed:
        raise ValueError("abstain=true cannot carry support units")
    return SupportUnitAnswer(parsed, abstain, reason)


def validate_support_unit_answer(
    answer: SupportUnitAnswer, units: list[SupportUnit]
) -> SupportUnitValidation:
    available = support_unit_map(units)
    if answer.abstain:
        return SupportUnitValidation(answer, [], [], [], True, True, False)
    valid: list[SupportUnitAnswerPart] = []
    rejected: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, part in enumerate(answer.answer_parts):
        part_codes: list[str] = []
        if not part.text:
            part_codes.append("ANSWER_PART_SCHEMA_INVALID")
        if not part.support_ids:
            part_codes.append("EMPTY_SUPPORT_LIST")
        selected = [available.get(item) for item in part.support_ids]
        if any(unit is None for unit in selected):
            part_codes.append("UNKNOWN_SUPPORT_ID")
        support_text = "\n".join(unit.text for unit in selected if unit is not None)
        value_status = critical_value_status(part.text, support_text)
        if value_status in {"CRITICAL_VALUE_ABSENT", "CRITICAL_VALUE_CONFLICT"}:
            part_codes.append(value_status)
        if part_codes:
            rejected.append(
                {
                    "part_index": index,
                    "text": part.text,
                    "support_ids": list(part.support_ids),
                    "validation_status": "REJECTED",
                    "failure_codes": sorted(set(part_codes)),
                    "critical_value_status": value_status,
                    "survived": False,
                }
            )
            codes.extend(part_codes)
        else:
            valid.append(part)
    application_abstain = not valid
    if application_abstain:
        codes.append("NO_VALID_SUPPORT_BACKED_CLAIMS")
    return SupportUnitValidation(
        answer, valid, rejected, sorted(set(codes)), True, False, application_abstain
    )


def render_support_unit_answer(parts: list[SupportUnitAnswerPart], *, abstain: bool = False) -> str:
    if abstain or not parts:
        return NOT_FOUND_PHRASE
    return "\n\n".join(
        f"{part.text} {' '.join(f'[{item}]' for item in part.support_ids)}".strip()
        for part in parts
    )


async def stream_support_unit_answer(
    query: str,
    blocks: list[SearchResult],
    provider: ChatProvider,
    *,
    model: str,
    prompt_version: str = "v3",
    context_serializer: Any = serialize_support_units,
    evaluation_observation: Any = None,
    think: bool = False,
    num_ctx: int = 4096,
    seed: int | None = None,
):
    """Pipeline v2.3.2: support IDs with bounded provider output."""
    units = build_support_units(blocks)
    yield {
        "type": "metadata",
        "prompt_version": prompt_version,
        "pipeline_version": SUPPORT_UNIT_BOUNDED_PIPELINE_VERSION,
        "output_contract_version": SUPPORT_UNIT_BOUNDED_OUTPUT_CONTRACT_VERSION,
    }
    messages = build_messages(
        query,
        units,
        version=prompt_version,
        context_serializer=context_serializer,
        system_prompt_suffix=SUPPORT_UNIT_OUTPUT_INSTRUCTIONS,
    )
    generation_kwargs = {
        "model": model,
        "think": think,
        "temperature": 0.0,
        # Keep the original exact enum contract.  The reliability fix bounds
        # runaway JSON generation; application membership validation remains
        # authoritative.
        "schema": support_unit_output_schema(units),
        "num_ctx": num_ctx,
        "num_predict": SUPPORT_UNIT_MAX_OUTPUT_TOKENS,
    }
    if seed is not None:
        generation_kwargs["seed"] = seed
    raw = await provider.chat_json(messages, **generation_kwargs)
    try:
        parsed = parse_support_unit_answer(raw)
        validation = validate_support_unit_answer(parsed, units)
    except (ValueError, json.JSONDecodeError):
        parsed = None
        validation = SupportUnitValidation(
            None, [], [], ["TOP_LEVEL_SCHEMA_INVALID"], False, False, True
        )
    final_abstain = validation.model_abstain or validation.application_abstain
    rendered = render_support_unit_answer(validation.valid_parts, abstain=final_abstain)
    user_visible = validation.top_level_valid and bool(rendered)
    if evaluation_observation is not None:
        evaluation_observation.raw_candidate_available = True
        evaluation_observation.raw_candidate_output = raw
        evaluation_observation.validator_input_available = True
        evaluation_observation.validator_pass = (
            validation.top_level_valid and not validation.failure_codes
        )
        evaluation_observation.validator_failure_codes = list(validation.failure_codes)
        evaluation_observation.validated_output = rendered
        evaluation_observation.validated_output_available = user_visible
        evaluation_observation.user_visible_output_available = user_visible
        evaluation_observation.pipeline_version = SUPPORT_UNIT_BOUNDED_PIPELINE_VERSION
        evaluation_observation.output_contract_version = (
            SUPPORT_UNIT_BOUNDED_OUTPUT_CONTRACT_VERSION
        )
        evaluation_observation.model_abstention = validation.model_abstain
        evaluation_observation.application_forced_abstention = (
            validation.application_abstain and not validation.model_abstain
        )
        evaluation_observation.structured_candidate = (
            {
                "answer_parts": [
                    {"text": part.text, "support_ids": list(part.support_ids)}
                    for part in parsed.answer_parts
                ],
                "abstain": parsed.abstain,
            }
            if parsed
            else None
        )
        evaluation_observation.validated_answer_parts = [
            {"text": part.text, "support_ids": list(part.support_ids), "survived": True}
            for part in validation.valid_parts
        ]
        evaluation_observation.rejected_answer_parts = validation.rejected_parts
    if user_visible:
        yield {"type": "token", "content": rendered}
    yield {
        "type": "security_validation",
        "passed": user_visible,
        "violations": list(validation.failure_codes),
        "validator_failure_codes": list(validation.failure_codes),
        "citation_suppressed": final_abstain,
        "hidden_prompt_leaked": False,
        "abstain": final_abstain,
        "application_forced_abstention": validation.application_abstain
        and not validation.model_abstain,
    }


def _quote_validation(evidence: EvidenceQuote, blocks: dict[str, SearchResult]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "evidence_id": evidence.evidence_id,
        "raw_quote": evidence.quote,
        "normalized_quote": normalize_evidence_quote(evidence.quote),
        "quote_match": False,
    }
    normalized_quote = result["normalized_quote"]
    if not evidence.evidence_id or not normalized_quote:
        result["status"] = "EMPTY_QUOTE" if not normalized_quote else "MALFORMED_EVIDENCE_REFERENCE"
        return result
    block = blocks.get(evidence.evidence_id)
    if block is None:
        result["status"] = "UNKNOWN_EVIDENCE_ID"
        return result
    quote = normalized_quote
    content = normalize_evidence_quote(str(block.payload.get("text", "")))
    start = content.find(quote)
    if start < 0:
        result["status"] = "QUOTE_NOT_FOUND"
        result["evidence_block_id"] = block.payload.get("evidence_block_id")
        return result
    result.update(
        {
            "status": "VALID_EVIDENCE_QUOTE",
            "quote_match": True,
            "matched_span": [start, start + len(quote)],
            "evidence_block_id": block.payload.get("evidence_block_id"),
            "source_id": block.payload.get("source_id"),
            "contributing_chunk_ids": block.payload.get("contributing_chunk_ids", []),
        }
    )
    return result


def validate_evidence_backed_answer(
    answer: EvidenceBackedAnswer, chunks: list[SearchResult]
) -> EvidenceBackedValidation:
    evidence = _evidence_map(chunks)
    if answer.abstain:
        return EvidenceBackedValidation(answer, [], [], [], True, True, False)
    valid: list[EvidenceBackedAnswerPart] = []
    rejected: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, part in enumerate(answer.answer_parts):
        checks = [_quote_validation(item, evidence) for item in part.evidence]
        valid_checks = [item for item in checks if item["status"] == "VALID_EVIDENCE_QUOTE"]
        part_codes = []
        if not part.text:
            part_codes.append("ANSWER_PART_SCHEMA_INVALID")
        if not part.evidence:
            part_codes.append("MALFORMED_EVIDENCE_REFERENCE")
        part_codes.extend(
            item["status"] for item in checks if item["status"] != "VALID_EVIDENCE_QUOTE"
        )
        # A part contains one material claim.  If any reference attached to
        # that claim is invalid, deterministic validation cannot establish
        # that the remaining valid quote independently supports the whole
        # claim.  Reject the part conservatively; independent parts still
        # survive independently.
        if valid_checks and len(valid_checks) == len(checks) and part.text:
            valid.append(
                EvidenceBackedAnswerPart(
                    part.text,
                    [
                        EvidenceQuote(item["evidence_id"], item["raw_quote"])
                        for item in valid_checks
                    ],
                )
            )
        else:
            if not part_codes:
                part_codes.append("MALFORMED_EVIDENCE_REFERENCE")
            rejected.append(
                {
                    "part_index": index,
                    "text": part.text,
                    "evidence": [
                        {"evidence_id": item.evidence_id, "quote": item.quote}
                        for item in part.evidence
                    ],
                    "evidence_validation": checks,
                    "failure_codes": sorted(set(part_codes)),
                    "survived": False,
                }
            )
        codes.extend(part_codes)
    application_abstain = not valid
    if application_abstain:
        codes.append("NO_VALID_EVIDENCE_BACKED_CLAIMS")
    return EvidenceBackedValidation(
        answer,
        valid,
        rejected,
        sorted(set(codes)),
        True,
        False,
        application_abstain,
    )


def render_evidence_backed_answer(
    parts: list[EvidenceBackedAnswerPart], *, abstain: bool = False
) -> str:
    if abstain or not parts:
        return NOT_FOUND_PHRASE
    return "\n\n".join(
        f"{part.text} {' '.join(f'[{item.evidence_id}]' for item in part.evidence)}".strip()
        for part in parts
    )


def _evidence_part_observability(
    part: EvidenceBackedAnswerPart,
    *,
    survived: bool,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "text": part.text,
        "evidence": [
            {"evidence_id": item.evidence_id, "quote": item.quote} for item in part.evidence
        ],
        "evidence_validation": checks,
        "validation_status": "VALID" if survived else "REJECTED",
        "survived": survived,
    }


async def stream_evidence_backed_answer(
    query: str,
    chunks: list[SearchResult],
    provider: ChatProvider,
    *,
    model: str,
    prompt_version: str = "v3",
    validation_mode: SecurityValidationMode = "strict",
    context_serializer: Any,
    evaluation_observation: GenerationObservation | None = None,
    think: bool = False,
    num_ctx: int = 4096,
    num_predict: int | None = None,
    seed: int | None = None,
):
    """Pipeline v2.2 with exact evidence quotes and application abstention."""
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("generate.model", model)
        span.set_attribute("security.validation_mode", validation_mode)
        span.set_attribute("pipeline.version", EVIDENCE_BACKED_PIPELINE_VERSION)
        yield {
            "type": "metadata",
            "prompt_version": prompt_version,
            "pipeline_version": EVIDENCE_BACKED_PIPELINE_VERSION,
            "output_contract_version": EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
        }
        messages = build_messages(
            query,
            chunks,
            version=prompt_version,
            context_serializer=context_serializer,
            system_prompt_suffix=EVIDENCE_BACKED_OUTPUT_INSTRUCTIONS,
        )
        try:
            generation_kwargs = {
                "model": model,
                "think": think,
                "temperature": 0.0,
                "schema": EVIDENCE_BACKED_OUTPUT_SCHEMA,
                "num_ctx": num_ctx,
            }
            if num_predict is not None:
                generation_kwargs["num_predict"] = num_predict
            if seed is not None:
                generation_kwargs["seed"] = seed
            raw = await provider.chat_json(messages, **generation_kwargs)
        except Exception as exc:
            if evaluation_observation is not None:
                evaluation_observation.pipeline_version = EVIDENCE_BACKED_PIPELINE_VERSION
                evaluation_observation.output_contract_version = (
                    EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION
                )
                evaluation_observation.validator_failure_codes = ["OTHER_VALIDATION_FAILURE"]
            yield {
                "type": "error",
                "message": "The generation provider failed.",
                "provider_error": str(exc),
            }
            return

        try:
            parsed = parse_evidence_backed_answer(raw)
            validation = validate_evidence_backed_answer(parsed, chunks)
        except (ValueError, json.JSONDecodeError):
            parsed = None
            validation = EvidenceBackedValidation(
                None,
                [],
                [],
                ["TOP_LEVEL_SCHEMA_INVALID", "NO_VALID_EVIDENCE_BACKED_CLAIMS"],
                False,
                False,
                True,
            )
        rendered = render_evidence_backed_answer(
            validation.valid_parts,
            abstain=validation.model_abstain or validation.application_abstain,
        )
        # A safe abstention response is user-visible; raw unsupported claims are not.
        user_visible = validation.top_level_valid and bool(rendered)
        if evaluation_observation is not None:
            evidence_map = _evidence_map(chunks)
            observation_parts = []
            for part in parsed.answer_parts if parsed else []:
                checks = [_quote_validation(item, evidence_map) for item in part.evidence]
                survives = (
                    bool(checks)
                    and all(item["status"] == "VALID_EVIDENCE_QUOTE" for item in checks)
                    and bool(part.text)
                )
                observation_parts.append(
                    _evidence_part_observability(part, survived=survives, checks=checks)
                )
            evaluation_observation.raw_candidate_available = True
            evaluation_observation.raw_candidate_output = raw
            evaluation_observation.validator_input_available = True
            evaluation_observation.validator_pass = (
                validation.top_level_valid and not validation.failure_codes
            )
            evaluation_observation.validator_failure_codes = list(validation.failure_codes)
            evaluation_observation.validated_output_available = user_visible
            evaluation_observation.user_visible_output_available = user_visible
            evaluation_observation.validated_output = rendered if user_visible else None
            evaluation_observation.pipeline_version = EVIDENCE_BACKED_PIPELINE_VERSION
            evaluation_observation.output_contract_version = EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION
            evaluation_observation.model_abstention = validation.model_abstain
            evaluation_observation.application_forced_abstention = (
                validation.application_abstain and not validation.model_abstain
            )
            evaluation_observation.structured_candidate = (
                {
                    "answer_parts": [
                        {
                            "text": part.text,
                            "evidence": [
                                {"evidence_id": item.evidence_id, "quote": item.quote}
                                for item in part.evidence
                            ],
                        }
                        for part in parsed.answer_parts
                    ],
                    "abstain": parsed.abstain,
                    "reason_code": parsed.reason_code,
                }
                if parsed
                else None
            )
            evaluation_observation.validated_answer_parts = [
                item for item in observation_parts if item["survived"]
            ]
            evaluation_observation.rejected_answer_parts = [
                item for item in observation_parts if not item["survived"]
            ]
        span.set_attribute("security.output_policy_passed", user_visible)
        if user_visible:
            yield {"type": "token", "content": rendered}
        yield {
            "type": "security_validation",
            "passed": user_visible,
            "violations": list(validation.failure_codes),
            "validator_failure_codes": list(validation.failure_codes),
            "citation_suppressed": validation.application_abstain,
            "hidden_prompt_leaked": False,
            "abstain": validation.model_abstain or validation.application_abstain,
            "application_forced_abstention": validation.application_abstain
            and not validation.model_abstain,
        }
        if not user_visible:
            yield {
                "type": "error",
                "message": "The answer was withheld because structured output validation failed.",
            }


def render_hardened_answer_parts(parts: list[HardenedAnswerPart], *, abstain: bool = False) -> str:
    if abstain or not parts:
        return NOT_FOUND_PHRASE
    return "\n\n".join(
        f"{part.text} {' '.join(f'[{item}]' for item in part.evidence_ids)}".strip()
        for part in parts
    )


def _hardened_part_observability(
    part: HardenedAnswerPart, chunks: list[SearchResult]
) -> dict[str, Any]:
    evidence = _evidence_map(chunks)
    return {
        "text": part.text,
        "requested_evidence_ids": list(part.evidence_ids),
        "resolved_evidence": [
            {
                "evidence_id": evidence[item].payload.get("evidence_id", item),
                "evidence_block_id": evidence[item].payload.get("evidence_block_id"),
                "source_id": evidence[item].payload.get("source_id"),
                "contributing_chunk_ids": evidence[item].payload.get("contributing_chunk_ids", []),
            }
            for item in part.evidence_ids
            if item in evidence
        ],
        "validation_status": "VALID",
        "survived": True,
    }


async def stream_hardened_answer(
    query: str,
    chunks: list[SearchResult],
    provider: ChatProvider,
    *,
    model: str,
    prompt_version: str = "v3",
    validation_mode: SecurityValidationMode = "strict",
    context_serializer: Any,
    evaluation_observation: GenerationObservation | None = None,
    think: bool = False,
    num_ctx: int = 4096,
):
    """Pipeline v2.1: response-local IDs, per-part validation, safe rendering."""
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("generate.model", model)
        span.set_attribute("security.validation_mode", validation_mode)
        span.set_attribute("pipeline.version", HARDENED_PIPELINE_VERSION)
        yield {
            "type": "metadata",
            "prompt_version": prompt_version,
            "pipeline_version": HARDENED_PIPELINE_VERSION,
            "output_contract_version": HARDENED_OUTPUT_CONTRACT_VERSION,
        }
        messages = build_messages(
            query,
            chunks,
            version=prompt_version,
            context_serializer=context_serializer,
            system_prompt_suffix=HARDENED_OUTPUT_INSTRUCTIONS,
        )
        try:
            raw = await provider.chat_json(
                messages,
                model=model,
                think=think,
                temperature=0.0,
                schema=HARDENED_OUTPUT_SCHEMA,
                num_ctx=num_ctx,
            )
        except Exception as exc:
            if evaluation_observation is not None:
                evaluation_observation.pipeline_version = HARDENED_PIPELINE_VERSION
                evaluation_observation.output_contract_version = HARDENED_OUTPUT_CONTRACT_VERSION
                evaluation_observation.validator_failure_codes = ["OTHER_VALIDATION_FAILURE"]
            yield {
                "type": "error",
                "message": "The generation provider failed.",
                "provider_error": str(exc),
            }
            return
        try:
            parsed = parse_hardened_answer(raw)
            validation = validate_hardened_answer(parsed, chunks)
        except (ValueError, json.JSONDecodeError):
            parsed = None
            validation = HardenedValidation(
                None, [], [], ["TOP_LEVEL_SCHEMA_INVALID"], False, False
            )
        rendered = render_hardened_answer_parts(validation.valid_parts, abstain=validation.abstain)
        top_level_safe = validation.top_level_valid
        security_codes = {"UNAUTHORIZED_EVIDENCE_ID", "EVIDENCE_IDENTITY_MISMATCH"}
        user_visible = (
            top_level_safe
            and bool(rendered)
            and not security_codes.intersection(validation.failure_codes)
        )
        if evaluation_observation is not None:
            evaluation_observation.raw_candidate_available = True
            evaluation_observation.raw_candidate_output = raw
            evaluation_observation.validator_input_available = True
            evaluation_observation.validator_pass = top_level_safe and not validation.failure_codes
            evaluation_observation.validator_failure_codes = list(validation.failure_codes)
            evaluation_observation.validated_output_available = user_visible
            evaluation_observation.user_visible_output_available = user_visible
            evaluation_observation.validated_output = rendered if user_visible else None
            evaluation_observation.pipeline_version = HARDENED_PIPELINE_VERSION
            evaluation_observation.output_contract_version = HARDENED_OUTPUT_CONTRACT_VERSION
            evaluation_observation.structured_candidate = (
                {
                    "answer_parts": [
                        {"text": part.text, "evidence_ids": list(part.evidence_ids)}
                        for part in parsed.answer_parts
                    ],
                    "abstain": parsed.abstain,
                    "reason_code": parsed.reason_code,
                }
                if parsed
                else None
            )
            evaluation_observation.validated_answer_parts = [
                _hardened_part_observability(part, chunks) for part in validation.valid_parts
            ]
            evaluation_observation.rejected_answer_parts = list(validation.rejected_parts)
        span.set_attribute("security.output_policy_passed", user_visible)
        if user_visible:
            yield {"type": "token", "content": rendered}
        yield {
            "type": "security_validation",
            "passed": user_visible,
            "violations": list(validation.failure_codes),
            "validator_failure_codes": list(validation.failure_codes),
            "citation_suppressed": not user_visible,
            "hidden_prompt_leaked": False,
            "abstain": validation.abstain,
        }
        if not user_visible:
            yield {
                "type": "error",
                "message": "The answer was withheld because structured output validation failed.",
            }


def parse_structured_answer(raw: str) -> StructuredAnswer:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("top-level JSON must be an object")
    parts = value.get("answer_parts")
    abstain = value.get("abstain")
    if not isinstance(parts, list) or not isinstance(abstain, bool):
        raise ValueError("answer_parts must be a list and abstain must be boolean")
    parsed: list[AnswerPart] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            raise ValueError(f"answer_parts[{index}] has invalid text")
        citations = part.get("citations")
        if not isinstance(citations, list) or not all(isinstance(item, str) for item in citations):
            raise ValueError(f"answer_parts[{index}] has invalid citations")
        parsed.append(AnswerPart(text=part["text"].strip(), citations=list(citations)))
    if abstain and parsed:
        raise ValueError("abstain=true cannot carry answer parts")
    return StructuredAnswer(answer_parts=parsed, abstain=abstain)


def validate_structured_answer(
    answer: StructuredAnswer, chunks: list[SearchResult]
) -> StructuredValidation:
    if answer.abstain:
        return StructuredValidation(answer, [], [], [], True, True)
    valid: list[AnswerPart] = []
    rejected: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, part in enumerate(answer.answer_parts):
        part_codes: list[str] = []
        if not part.text:
            part_codes.append("OUTPUT_SCHEMA_FAILURE")
        if not part.citations:
            part_codes.append("MISSING_REQUIRED_CITATION")
        for citation in part.citations:
            status = citation_identity_status(citation, chunks)
            if status != "VALID":
                part_codes.append(status)
        if part_codes:
            unique = sorted(set(part_codes))
            rejected.append({"part_index": index, "text": part.text, "failure_codes": unique})
            codes.extend(unique)
        else:
            valid.append(part)
    return StructuredValidation(
        parsed=answer,
        valid_parts=valid,
        rejected_parts=rejected,
        failure_codes=sorted(set(codes)),
        top_level_valid=True,
        abstain=False,
    )


def render_answer_parts(parts: list[AnswerPart], *, abstain: bool = False) -> str:
    if abstain or not parts:
        return NOT_FOUND_PHRASE
    return "\n\n".join(f"{part.text} {' '.join(part.citations)}".strip() for part in parts)


def _record_structured_observation(
    observation: GenerationObservation,
    raw: str,
    parsed: StructuredAnswer | None,
    rendered: str,
    grounding: GroundingResult,
    output_policy: Any,
    validation: StructuredValidation,
    *,
    user_visible: bool,
) -> None:
    observation.raw_candidate_available = True
    observation.raw_candidate_output = raw
    observation.validator_input_available = True
    observation.validator_pass = bool(
        output_policy and output_policy.passed and not validation.failure_codes
    )
    observation.validator_failure_codes = sorted(
        set(validation.failure_codes)
        | (set(output_policy.violations) if output_policy and not output_policy.passed else set())
    )
    # A valid subset is a validated output even when another independent
    # answer part was rejected.  User visibility remains separately gated.
    observation.validated_output_available = bool(
        rendered and output_policy and output_policy.passed
    )
    observation.user_visible_output_available = user_visible
    observation.validated_output = rendered if user_visible else None
    observation.structured_candidate = (
        {
            "answer_parts": [
                {"text": part.text, "citations": list(part.citations)}
                for part in parsed.answer_parts
            ],
            "abstain": parsed.abstain,
        }
        if parsed
        else None
    )
    observation.citations_extracted_from_raw = list(extract_citations(raw))
    observation.citations_extracted_from_validated = (
        list(grounding.citations_found) if user_visible else []
    )
    observation.pipeline_version = PIPELINE_VERSION
    observation.output_contract_version = STRUCTURED_OUTPUT_CONTRACT_VERSION


async def stream_structured_answer(
    query: str,
    chunks: list[SearchResult],
    provider: ChatProvider,
    *,
    model: str,
    prompt_version: str = "v3",
    validation_mode: SecurityValidationMode = "strict",
    context_serializer: Any,
    evaluation_observation: GenerationObservation | None = None,
    think: bool = False,
    num_ctx: int = 4096,
):
    """Buffer structured candidate, validate parts, then release rendering."""
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("generate.model", model)
        span.set_attribute("generate.prompt_version", prompt_version)
        span.set_attribute("pipeline.version", PIPELINE_VERSION)
        yield {
            "type": "metadata",
            "prompt_version": prompt_version,
            "pipeline_version": PIPELINE_VERSION,
            "output_contract_version": STRUCTURED_OUTPUT_CONTRACT_VERSION,
        }
        messages = build_messages(
            query,
            chunks,
            version=prompt_version,
            context_serializer=context_serializer,
            system_prompt_suffix=STRUCTURED_OUTPUT_INSTRUCTIONS,
        )
        try:
            chat_json = getattr(provider, "chat_json", None)
            if callable(chat_json):
                raw = await chat_json(
                    messages,
                    model=model,
                    think=think,
                    temperature=0.0,
                    schema=STRUCTURED_OUTPUT_SCHEMA,
                    num_ctx=num_ctx,
                )
            else:
                pieces: list[str] = []
                async for piece in provider.stream_chat(messages, model=model):
                    pieces.append(piece)
                raw = "".join(pieces)
        except Exception as exc:
            if evaluation_observation is not None:
                evaluation_observation.pipeline_version = PIPELINE_VERSION
                evaluation_observation.output_contract_version = STRUCTURED_OUTPUT_CONTRACT_VERSION
                evaluation_observation.validator_failure_codes = ["OTHER_VALIDATION_FAILURE"]
            yield {
                "type": "error",
                "message": "The generation provider failed.",
                "provider_error": str(exc),
            }
            return
        validation_error: str | None = None
        parsed: StructuredAnswer | None = None
        try:
            parsed = parse_structured_answer(raw)
            validation = validate_structured_answer(parsed, chunks)
        except (ValueError, json.JSONDecodeError) as exc:
            validation_error = str(exc)
            validation = StructuredValidation(None, [], [], ["OUTPUT_SCHEMA_FAILURE"], False, False)
        rendered = render_answer_parts(validation.valid_parts, abstain=validation.abstain)
        grounding = check_grounding(rendered, chunks)
        policy = check_output_policy(rendered, chunks, load_system_prompt(prompt_version))
        all_codes = sorted(
            set(validation.failure_codes)
            | set(normalize_validator_failure_codes(policy.violations))
        )
        if validation_error:
            all_codes.append("OUTPUT_SCHEMA_FAILURE")
        all_codes = sorted(set(all_codes))
        # Independent invalid parts are suppressed, while valid parts can be
        # rendered.  A security boundary violation still withholds the whole
        # response; malformed top-level JSON also remains fail-closed.
        user_visible = (
            validation.top_level_valid
            and bool(rendered)
            and policy.passed
            and "UNAUTHORIZED_CITATION_ID" not in all_codes
        )
        if evaluation_observation is not None:
            _record_structured_observation(
                evaluation_observation,
                raw,
                parsed,
                rendered,
                grounding,
                policy,
                validation,
                user_visible=user_visible,
            )
            evaluation_observation.validator_failure_codes = all_codes
        span.set_attribute("security.output_policy_passed", policy.passed)
        if user_visible:
            yield {"type": "token", "content": rendered}
        yield {
            "type": "grounding",
            "grounded": grounding.grounded,
            "has_citations": grounding.has_citations,
            "citations_found": grounding.citations_found,
            "ungrounded_citations": grounding.ungrounded_citations,
        }
        yield {
            "type": "security_validation",
            "passed": user_visible,
            "violations": all_codes,
            "validator_failure_codes": all_codes,
            "citation_suppressed": not user_visible,
            "hidden_prompt_leaked": False,
            "abstain": validation.abstain,
        }
        if not user_visible:
            yield {
                "type": "error",
                "message": "The answer was withheld because structured output validation failed.",
            }
