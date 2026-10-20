"""Preserve terminal events separately from streamed answer text in trace exports."""

from typing import Any


def terminal_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    clarification = next((e for e in reversed(events) if e["type"] == "clarification"), None)
    metadata = next((e for e in reversed(events) if e["type"] == "metadata"), {})
    agentic = metadata.get("agentic", {})
    validation = next((e for e in reversed(events) if e["type"] == "security_validation"), {})
    if clarification is not None:
        kind = "needs_clarification"
    elif agentic.get("finalization") == "failed":
        kind = "failed"
    elif validation.get("abstain"):
        kind = agentic.get("source_disposition") or "insufficient_evidence"
    elif answer and validation.get("passed"):
        kind = "answer"
    else:
        kind = "unknown"
    return {
        "answer": answer,
        "terminal_kind": kind,
        "clarification": {k: v for k, v in clarification.items() if k != "type"}
        if clarification is not None
        else None,
    }
