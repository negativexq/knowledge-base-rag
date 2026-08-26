"""Trusted-control-plane and untrusted-context primitives.

This module deliberately does not try to identify or delete "bad" prose.
Retrieved text is data even when it contains imperative language. The
security property comes from keeping it in a separate user-message section,
encoding it as JSON records, and validating generated citations against the
server-owned authorized chunk set.
"""

from __future__ import annotations

import json

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult

PROMPT_POLICY_VERSION = "answer_v3"


def _citation_tag(source_type: str, source_id: str, location: str) -> str:
    return f"[s.{source_type}:{source_id}/{location}]"


def _safe_json(value: object) -> str:
    """Encode data so prompt delimiters cannot become structure.

    JSON already escapes quotes and newlines inside strings. Escaping angle
    brackets as well makes document text such as ``</system>`` visibly data
    rather than a prompt delimiter. The length prefix is an additional
    human-debuggable boundary; no parser is required by the model provider.
    """

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def serialize_user_question(question: str) -> str:
    return _safe_json({"question": question})


def _location(payload: dict) -> str | None:
    try:
        return location_for(payload)
    except (KeyError, TypeError):
        return None


def _record(index: int, chunk: SearchResult) -> str:
    payload = chunk.payload
    location = _location(payload)
    source_type = payload.get("source_type", "doc")
    source_id = payload.get("source_id", "doc")
    canonical = _citation_tag(source_type, source_id, location) if location else None
    record = {
        "metadata": {
            "source_type": source_type,
            "source_id": source_id,
            "location": location,
            "canonical_citation": canonical,
            "title": payload.get("title"),
            "source_name": payload.get("source_name"),
            "heading_path": payload.get("heading_path") or [],
            "document_version": payload.get("document_version"),
        },
        "content": payload.get("text", ""),
    }
    encoded = _safe_json(record)
    canonical_line = canonical or "none"
    return (
        f"[document {index} json_chars={len(encoded)}]\n"
        f"CANONICAL CITATION (server-approved): {canonical_line}\n"
        f"JSON RECORD (untrusted data):\n{encoded}\n"
        f"[/document {index}]"
    )


def serialize_untrusted_context(chunks: list[SearchResult]) -> str:
    """Serialize authorized chunks as explicitly untrusted reference data.

    Metadata and body are intentionally in the same untrusted record. The
    only citation the model may use is the server-generated
    ``canonical_citation`` value; raw citation-looking strings in content are
    still just content and are checked again by app.llm.grounding.
    """

    records = "\n".join(_record(index, chunk) for index, chunk in enumerate(chunks, 1))
    return (
        f'<retrieved_context trust="untrusted" records="{len(chunks)}">\n'
        f"{records}\n</retrieved_context>"
    )


def estimate_context_overhead(chunks: list[SearchResult]) -> dict[str, float | int]:
    """Compare legacy and v3 context size with a documented estimator.

    There is no provider-independent tokenizer in this repository. The
    whitespace estimate is intentionally labelled as such; it is useful for
    detecting an unexpected budget jump, not a substitute for model tokens.
    """

    legacy = "\n\n".join(
        f"[source: {chunk.payload.get('source_type', 'doc')}:"
        f"{chunk.payload.get('source_id', 'doc')}]\n"
        f"{chunk.payload.get('text', '')}"
        for chunk in chunks
    )
    old_tokens = max(1, len(legacy.split()))
    new_tokens = max(1, len(serialize_untrusted_context(chunks).split()))
    return {
        "estimator": "whitespace_token_estimate",
        "old_tokens": old_tokens,
        "new_tokens": new_tokens,
        "overhead_percent": round((new_tokens - old_tokens) / old_tokens * 100, 2),
    }
