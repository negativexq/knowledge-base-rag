"""Deterministic stopping policy above the SDK's hard shared usage limits."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResearchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_research_requests: int = Field(default=3, ge=1, le=10)
    max_tool_attempts: int = Field(default=4, ge=1, le=20)
    max_no_progress: int = Field(default=2, ge=1, le=5)
    max_validation_repairs: int = Field(default=1, ge=0, le=3)
    tool_timeout_seconds: float = Field(default=20, gt=0, le=120)
    model_timeout_seconds: float = Field(default=30, gt=0, le=120)
    finalize_reserve_seconds: float = Field(default=30, ge=0, le=120)


@dataclass
class ResearchBudget:
    policy: ResearchPolicy = field(default_factory=ResearchPolicy)
    deadline: float | None = None
    research_requests: int = 0
    tool_attempts: int = 0
    blocked_tool_calls: int = 0
    no_progress: int = 0
    validation_rejections: int = 0
    stop_reason: str | None = None
    terminal_reason: str | None = None
    signatures: dict[str, int] = field(default_factory=dict)

    def close(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason

    def terminate(self, reason: str) -> None:
        if self.terminal_reason is None:
            self.terminal_reason = reason
        self.close(reason)

    def tools_closed(self) -> bool:
        if self.deadline is not None and time.monotonic() >= (
            self.deadline - self.policy.finalize_reserve_seconds
        ):
            self.close("RESEARCH_TIME_EXHAUSTED")
        if self.research_requests >= self.policy.max_research_requests - 1:
            self.close("RESEARCH_TURN_LIMIT")
        if self.tool_attempts >= self.policy.max_tool_attempts:
            self.close("TOOL_ATTEMPT_LIMIT")
        return self.stop_reason is not None

    def before_tool(self, name: str, args: dict[str, Any], evidence_revision: int) -> str | None:
        # Same-request tool batches may continue after the soft stop. This check
        # therefore runs at execution time as well as hiding future definitions.
        if self.stop_reason is not None or self.tool_attempts >= self.policy.max_tool_attempts:
            self.close("TOOL_ATTEMPT_LIMIT")
            self.blocked_tool_calls += 1
            return self.stop_reason
        if self.deadline is not None and time.monotonic() >= (
            self.deadline - self.policy.finalize_reserve_seconds
        ):
            self.close("RESEARCH_TIME_EXHAUSTED")
            self.blocked_tool_calls += 1
            return self.stop_reason
        self.tool_attempts += 1
        signature = hashlib.sha256(
            json.dumps([name, args], sort_keys=True, default=str).encode()
        ).hexdigest()
        if self.signatures.get(signature) == evidence_revision:
            self.close("REPEATED_TOOL_CALL")
            self.blocked_tool_calls += 1
            return self.stop_reason
        self.signatures[signature] = evidence_revision
        return None

    def after_tool(self, progressed: bool) -> None:
        self.no_progress = 0 if progressed else self.no_progress + 1
        if self.no_progress >= self.policy.max_no_progress:
            self.close("NO_RESEARCH_PROGRESS")

    def tool_timeout(self) -> float:
        if self.deadline is None:
            return self.policy.tool_timeout_seconds
        return max(
            0.001,
            min(
                self.policy.tool_timeout_seconds,
                self.deadline - self.policy.finalize_reserve_seconds - time.monotonic(),
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy": self.policy.model_dump(),
            "research_requests": self.research_requests,
            "tool_attempts": self.tool_attempts,
            "blocked_tool_calls": self.blocked_tool_calls,
            "consecutive_no_progress": self.no_progress,
            "validation_rejections": self.validation_rejections,
            "stop_reason": self.stop_reason,
            "terminal_reason": self.terminal_reason,
        }
