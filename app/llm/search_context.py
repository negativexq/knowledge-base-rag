"""Select complete parser chunks from expanded results; never summarize cells."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.retrieval.hybrid_search import SearchResult


def chunk_identity(block: SearchResult) -> tuple[Any, ...]:
    p = block.payload
    return (
        p.get("tenant_id"),
        p.get("source_type"),
        p.get("source_id"),
        p.get("document_version"),
        str(block.id),
        hashlib.sha256(str(p.get("text", "")).encode()).hexdigest(),
    )


def complete_chunks(block: SearchResult) -> list[SearchResult]:
    p = block.payload
    chunks = p.get("section_chunks") or []
    if not chunks or "\n\n".join(str(c["text"]) for c in chunks) != p.get("text"):
        return [block]
    return [
        SearchResult(
            id=str(c["chunk_id"]),
            score=block.score,
            payload={
                **p,
                **{
                    k: c[k]
                    for k in (
                        "text",
                        "section_key",
                        "heading_path",
                        "section_path",
                        "page_number",
                        "page_end",
                    )
                    if k in c
                },
                "section_chunks": [],
                "contributing_chunk_ids": [str(c["chunk_id"])],
                "evidence_block_id": str(c["chunk_id"]),
                "parent_source_block_id": str(block.id),
            },
        )
        for c in chunks
    ]


def targeted_chunks(blocks: list[SearchResult], query: str) -> list[SearchResult]:
    terms = set(re.findall(r"\w{3,}", query.casefold()))
    chosen = []
    seen = set()
    for parent in blocks:
        chunks = complete_chunks(parent)
        anchors = set(parent.payload.get("anchor_chunk_ids", []))

        # Local evidence selection only; retrieval/reranker scores stay intact.
        def score(c: SearchResult) -> tuple[int, int]:
            words = set(re.findall(r"\w{3,}", str(c.payload.get("text", "")).casefold()))
            return len(words & terms), int(str(c.id) in anchors)

        ranked = sorted(range(len(chunks)), key=lambda i: score(chunks[i]), reverse=True)
        indices = ranked[:3]
        # Keep same-page context for captions/units/footnotes without a whole section.
        for i in list(indices):
            page = chunks[i].payload.get("page_number")
            for j in (i - 1, i + 1):
                if (
                    0 <= j < len(chunks)
                    and page is not None
                    and chunks[j].payload.get("page_number") == page
                    and j not in indices
                ):
                    indices.append(j)
        for i in indices[:6]:
            c = chunks[i]
            key = chunk_identity(c)
            if key not in seen:
                chosen.append(
                    SearchResult(
                        id=c.id,
                        score=c.score,
                        payload={**c.payload, "reading_method": "parser_chunk"},
                    )
                )
                seen.add(key)
    return chosen
