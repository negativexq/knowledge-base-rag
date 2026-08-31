"""Opt-in local forensic capture for controlled RAG replay.

This module is deliberately separate from normal tracing.  It records bounded
stage metadata locally when explicitly enabled, and only records raw text when
the second explicit raw-text switch is also enabled.  Capture failures are
diagnostic-only and must never affect answer delivery.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_CURRENT_CAPTURE: ContextVar[ForensicCapture | None] = ContextVar(
    "current_forensic_capture", default=None
)

_FORBIDDEN_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token|database_url)",
    re.IGNORECASE,
)
_RAW_KEYS = {
    "raw_query",
    "raw_model_answer",
    "raw_model_output",
    "raw_visible_text",
    "raw_evidence_text",
    "raw_support_text",
    "local_context",
    "answer_local_context",
    "matching_local_context",
    "raw_quote",
    "normalized_quote",
    "raw_literal",
    "claim",
    "text",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_value(value: Any, *, raw_text: bool, key: str = "") -> Any:
    """Copy only JSON-safe values and redact forbidden fields."""
    if _FORBIDDEN_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _safe_value(child_value, raw_text=raw_text, key=str(child_key))
            for child_key, child_value in value.items()
            if raw_text or str(child_key) not in _RAW_KEYS
        }
    if isinstance(value, list | tuple):
        return [_safe_value(item, raw_text=raw_text, key=key) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        if key in _RAW_KEYS and not raw_text:
            return f"sha256:{_sha256(value)}" if isinstance(value, str) else "[OMITTED]"
        return value
    return str(value)


def _chunk_metadata(chunk: Any, rank: int, *, include_text: bool = False) -> dict[str, Any]:
    payload = getattr(chunk, "payload", {}) or {}
    result = {
        "rank": rank,
        "chunk_id": str(getattr(chunk, "id", "") or payload.get("chunk_id", "")),
        "source_id": payload.get("source_id"),
        "section_key": payload.get("section_key") or payload.get("heading_path"),
        "score": getattr(chunk, "score", None),
        "document_version": payload.get("document_version"),
        "authorized": payload.get("authorized", True),
    }
    if include_text:
        result["text"] = payload.get("text", "")
    return result


def _support_metadata(unit: Any, position: int) -> dict[str, Any]:
    return {
        "position": position,
        "support_id": unit.support_unit_id,
        "parent_evidence_block_id": unit.parent_evidence_block_id,
        "evidence_id": unit.evidence_id,
        "source_id": unit.source_id,
        "section_key": unit.section_id,
        "document_version": unit.document_version,
        "contributing_chunk_ids": list(unit.contributing_chunk_ids),
        "authorized": unit.authorized,
        "model_visible": unit.model_visible,
        "text": unit.text,
    }


@dataclass
class ForensicCapture:
    request_id: str
    raw_text: bool = False
    record: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, query: str, *, raw_text: bool) -> ForensicCapture:
        request_id = uuid.uuid4().hex
        capture = cls(request_id=request_id, raw_text=raw_text)
        capture.record = {
            "schema_version": "rag_forensic_capture_v1",
            "forensic_request_id": request_id,
            "query_hash": _sha256(query),
            "raw_text_enabled": raw_text,
            "stages": {},
        }
        if raw_text:
            capture.record["raw_query"] = query
        return capture

    def stage(self, name: str, values: dict[str, Any]) -> None:
        self.record.setdefault("stages", {})[name] = _safe_value(
            values, raw_text=self.raw_text
        )

    def merge_stage(self, name: str, values: dict[str, Any]) -> None:
        stage = self.record.setdefault("stages", {}).setdefault(name, {})
        stage.update(_safe_value(values, raw_text=self.raw_text))

    def set_generation(self, values: dict[str, Any]) -> None:
        self.stage("generation", values)

    def set_visible_outcome(self, values: dict[str, Any]) -> None:
        self.stage("visible_response", values)

    def snapshot(self) -> dict[str, Any]:
        return _safe_value(self.record, raw_text=self.raw_text)

    def write(self, directory: str | None) -> str | None:
        if not directory:
            logger.warning("forensic capture enabled without a capture directory")
            return None
        try:
            target_dir = Path(directory)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{self.request_id}.json"
            target.write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return str(target)
        except (OSError, TypeError, ValueError):
            logger.warning("forensic capture write failed", exc_info=True)
            return None


def metadata_for_chunks(
    chunks: list[Any], *, include_text: bool = False
) -> list[dict[str, Any]]:
    return [
        _chunk_metadata(chunk, index, include_text=include_text)
        for index, chunk in enumerate(chunks, 1)
    ]


def metadata_for_support_units(units: list[Any]) -> list[dict[str, Any]]:
    return [_support_metadata(unit, index) for index, unit in enumerate(units, 1)]


def redact_for_otel(values: dict[str, Any]) -> dict[str, Any]:
    """Return bounded-safe values suitable for diagnostic spans."""
    return _safe_value(values, raw_text=False)


def current_capture() -> ForensicCapture | None:
    return _CURRENT_CAPTURE.get()


def set_current_capture(capture: ForensicCapture | None) -> Token:
    return _CURRENT_CAPTURE.set(capture)


def reset_current_capture(token: Token) -> None:
    _CURRENT_CAPTURE.reset(token)
