"""Bounded claim repairs preserve accepted content and pending completions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.agentic import AgentAnswerPart
from app.llm.answer_coverage import LocatedOmission


class PartPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, le=49)
    part: AgentAnswerPart


class AnswerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    replacements: list[PartPatch] = Field(min_length=1, max_length=50)


class AnswerCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    additions: list[AgentAnswerPart] = Field(min_length=1, max_length=24)


class AnswerRepair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    parts: list[AgentAnswerPart]
    failed_indexes: list[int]
    failure_codes: list[str]
    omissions: list[LocatedOmission] = Field(default_factory=list, max_length=52)
    candidate_parts: list[AgentAnswerPart] = Field(default_factory=list, max_length=50)
    completion_status: Literal["not_started", "pending", "verified", "rejected"] = "not_started"

    def apply(self, patch: AnswerPatch) -> list[AgentAnswerPart]:
        replacements = {p.index: p.part for p in patch.replacements}
        if len(replacements) != len(patch.replacements) or set(replacements) != set(
            self.failed_indexes
        ):
            raise ValueError("PATCH_MUST_REPLACE_ONLY_FAILED_PARTS")
        return [replacements.get(i, part) for i, part in enumerate(self.parts)]
