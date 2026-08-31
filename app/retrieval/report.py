"""Sprint 24: a collector for what actually happened during one
retrieval call — the real material the operations console's Retrieval
inspector renders.

Deliberately a passive, caller-supplied collector rather than a changed
return type: `search()` takes an optional `report=` and fills it in, so
every existing caller (benchmarks, evaluation CLI, migration quality
gate) is completely unaffected and pays nothing.

Everything here is MEASURED or read from real configuration — there is
no field this module can populate by estimating. Stages the pipeline
genuinely doesn't run (e.g. reranking when `reranker=None`) are simply
absent from `stages`, never emitted with a fabricated duration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalStage:
    """One real stage of the retrieval pipeline.

    `candidates_in`/`candidates_out` are None when the stage has no
    meaningful count (e.g. query embedding produces a vector, not
    candidates). `detail` carries stage-specific, factual configuration
    (e.g. which fusion algorithm Qdrant was asked for) — never a
    derived or guessed metric.
    """

    name: str
    duration_ms: float
    candidates_in: int | None = None
    candidates_out: int | None = None
    top_score: float | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "candidates_in": self.candidates_in,
            "candidates_out": self.candidates_out,
            "top_score": self.top_score,
            "detail": self.detail,
        }


@dataclass
class RetrievalReport:
    stages: list[RetrievalStage] = field(default_factory=list)
    acl_applied: bool = False
    acl_tenant_id: str | None = None
    is_system_context: bool = False
    user_filters_applied: bool = False
    prompt_policy_version: str | None = None
    untrusted_context_enabled: bool = False
    security_validation_mode: str | None = None
    output_policy_passed: bool | None = None
    output_policy_violations: list[str] = field(default_factory=list)
    reranker: dict | None = None
    context: dict = field(default_factory=dict)
    answerability: dict | None = None
    semantic_answerability: dict | None = None
    validator: dict | None = None
    pre_acl_candidate_count: int | None = None
    authorized_candidate_count: int | None = None
    forensic_capture: Any = field(default=None, repr=False, compare=False)
    forensic_capture: Any = field(default=None, repr=False, compare=False)

    def record(self, stage: RetrievalStage) -> None:
        self.stages.append(stage)

    def as_dict(self) -> dict:
        return {
            "stages": [s.as_dict() for s in self.stages],
            "authorization": {
                "acl_applied": self.acl_applied,
                "tenant_id": self.acl_tenant_id,
                "is_system_context": self.is_system_context,
                "user_filters_applied": self.user_filters_applied,
            },
            "total_duration_ms": round(sum(s.duration_ms for s in self.stages), 3),
            "reranker": self.reranker,
            "answerability": self.answerability,
            "semantic_answerability": self.semantic_answerability,
            "validator": self.validator,
            "context": self.context,
            "security": {
                "prompt_policy_version": self.prompt_policy_version,
                "untrusted_context_enabled": self.untrusted_context_enabled,
                "security_validation_mode": self.security_validation_mode,
                "output_policy_passed": self.output_policy_passed,
                "output_policy_violations": self.output_policy_violations,
            },
        }


class stage_timer:  # noqa: N801 - used as a context manager, reads as a verb phrase
    """Times a block and records it on `report` (a no-op when report is
    None, which is the case for every non-UI caller). Counts/scores are
    set by the caller on the returned handle AFTER the real work, so
    they're always observed values, never predicted ones.
    """

    def __init__(self, report: RetrievalReport | None, name: str, **detail):
        self._report = report
        self._name = name
        self._detail = detail
        self._start = 0.0
        self.candidates_in: int | None = None
        self.candidates_out: int | None = None
        self.top_score: float | None = None

    def __enter__(self) -> stage_timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._report is None or exc_type is not None:
            return
        self._report.record(
            RetrievalStage(
                name=self._name,
                duration_ms=(time.perf_counter() - self._start) * 1000,
                candidates_in=self.candidates_in,
                candidates_out=self.candidates_out,
                top_score=self.top_score,
                detail=self._detail,
            )
        )
