"""Bounded document navigation over the active index; no embedding or model calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.llm.agent_observability import operation
from app.retrieval.filters import build_acl_filter, combine_filters, filter_authorized_candidates
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=500)
    document_version: str = Field(min_length=1, max_length=200)


class DocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: DocumentRef
    action: Literal["outline", "search", "section", "page", "neighbors"] = "outline"
    query: str = Field(default="", max_length=500)
    section_id: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=100000)
    chunk_id: str = Field(default="", max_length=200)
    radius: int = Field(default=1, ge=0, le=3)
    offset: int = Field(default=0, ge=0, le=2000)
    limit: int = Field(default=20, ge=1, le=50)


def section_id(payload: dict[str, Any]) -> str:
    heading = payload.get("heading_path") or payload.get("section_path")
    key = (
        [heading, payload.get("heading_occurrence", 0)] if heading else [payload.get("page_number")]
    )
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def order(block: SearchResult) -> tuple[int, int, int, str]:
    p = block.payload
    return (
        int(p.get("page_number") or 0),
        int(p.get("paragraph_index") or 0),
        int((p.get("char_range") or [0])[0]),
        str(block.id),
    )


@dataclass
class DocumentResult:
    blocks: list[SearchResult]
    outline: list[dict[str, Any]]
    has_more: bool = False
    scan_limited: bool = False
    next_offset: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "passages": [
                {
                    "chunk_id": b.id,
                    "text": b.payload.get("text", ""),
                    "page_number": b.payload.get("page_number"),
                    "page_end": b.payload.get("page_end"),
                    "section_id": section_id(b.payload),
                    "heading_path": b.payload.get("heading_path")
                    or b.payload.get("section_path")
                    or [],
                }
                for b in self.blocks
            ],
            "outline": self.outline,
            "has_more": self.has_more,
            "scan_limited": self.scan_limited,
            "next_offset": self.next_offset,
        }


class DocumentReader:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        context: RetrievalContext,
        source_ids: list[str] | None = None,
    ) -> None:
        self.client, self.collection, self.context = client, collection, context
        self.source_ids = frozenset(source_ids) if source_ids is not None else None

    def _scan(self, ref: DocumentRef) -> tuple[list[SearchResult], bool]:
        return self._scan_scope(ref)

    def _scan_scope(self, ref: DocumentRef | None = None) -> tuple[list[SearchResult], bool]:
        # Fail closed before touching Qdrant, even for an empty source scope.
        acl = build_acl_filter(self.context)
        if ref and self.source_ids is not None and ref.source_id not in self.source_ids:
            return [], False
        if (
            ref is not None
            and self.context.document_permissions is not None
            and not self.context.document_permissions.rules().allows(ref.source_type, ref.source_id)
        ):
            return [], False
        conditions: list[qm.Condition] = [
            qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
            for k, v in (ref.model_dump().items() if ref else [])
        ]
        if self.source_ids is not None:
            conditions.append(
                qm.FieldCondition(key="source_id", match=qm.MatchAny(any=list(self.source_ids)))
            )
        query_filter = combine_filters(acl, qm.Filter(must=conditions))
        found: list[SearchResult] = []
        cursor = None
        for _ in range(8):
            points, cursor = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=250,
                offset=cursor,
                with_payload=True,
                with_vectors=False,
            )
            found.extend(
                SearchResult(id=str(p.id), score=0, payload=dict(p.payload or {})) for p in points
            )
            if cursor is None:
                break
        # Also verify filters locally to protect against malformed service responses.
        found = [
            b
            for b in filter_authorized_candidates(found, self.context)
            if (ref is None or all(b.payload.get(k) == v for k, v in ref.model_dump().items()))
            and (self.source_ids is None or b.payload.get("source_id") in self.source_ids)
            and b.payload.get("authorized", True) is True
            and b.payload.get("model_visible", True) is True
        ]
        return sorted(found, key=order), cursor is not None

    async def find(
        self,
        query: str,
        *,
        phrase: bool = False,
        document: DocumentRef | None = None,
        exclude_ids: set[str] | None = None,
        page: int | None = None,
        section: str = "",
        offset: int = 0,
    ) -> DocumentResult:
        """Bounded literal search, with explicit incomplete-scan and pagination flags."""

        def run() -> DocumentResult:
            blocks, limited = self._scan_scope(document)
            needle = " ".join(query.casefold().split())
            selected = []
            for b in blocks:
                p = b.payload
                text = " ".join(str(p.get("text", "")).casefold().split())
                matches = needle in text if phrase else all(t in text for t in needle.split())
                if not matches or b.id in (exclude_ids or set()):
                    continue
                if page is not None and not (
                    int(p.get("page_number") or 0)
                    <= page
                    <= int(p.get("page_end") or p.get("page_number") or 0)
                ):
                    continue
                if section and section_id(p) != section:
                    continue
                selected.append(b)
            visible: list[SearchResult] = []
            chars = 0
            for b in selected[offset : offset + 20]:
                cost = len(str(b.payload.get("text", "")))
                if chars + cost > 60000:
                    break
                visible.append(b)
                chars += cost
            more = len(selected) > offset + len(visible)
            return DocumentResult(
                visible,
                [],
                more,
                limited,
                offset + len(visible) if more and visible else None,
            )

        with operation("document.read", attributes={"document.action": "find"}) as span:
            result = await asyncio.to_thread(run)
            span.set_attribute("document.returned_passages", len(result.blocks))
            span.set_attribute("document.scan_limited", result.scan_limited)
            span.set_attribute("document.has_more", result.has_more)
            return result

    async def discover(
        self,
        query: str,
        *,
        version: str = "",
        offset: int = 0,
    ) -> DocumentResult:
        """Find authorized document anchors by indexed name/title/headings, without an LLM."""

        def run() -> DocumentResult:
            blocks, limited = self._scan_scope()
            anchors: dict[tuple[str, ...], SearchResult] = {}
            terms = query.casefold().split()
            for b in blocks:
                p = b.payload
                key = tuple(
                    str(p.get(k, "")) for k in ("source_type", "source_id", "document_version")
                )
                if not all(key) or (version and key[2] != version):
                    continue
                metadata = " ".join(
                    [
                        key[1],
                        str(p.get("title", "")),
                        " ".join(p.get("heading_path") or p.get("section_path") or []),
                    ]
                ).casefold()
                if all(term in metadata for term in terms):
                    anchors.setdefault(key, b)
            selected = sorted(
                anchors.values(),
                key=lambda b: (
                    str(b.payload.get("source_id")),
                    str(b.payload.get("document_version")),
                ),
            )
            page = selected[offset : offset + 10]
            more = len(selected) > offset + len(page)
            return DocumentResult(page, [], more, limited, offset + len(page) if more else None)

        with operation("document.read", attributes={"document.action": "discover"}) as span:
            result = await asyncio.to_thread(run)
            span.set_attribute("document.returned_passages", len(result.blocks))
            span.set_attribute("document.scan_limited", result.scan_limited)
            span.set_attribute("document.has_more", result.has_more)
            return result

    async def read(self, request: DocumentRead) -> DocumentResult:
        with operation("document.read", attributes={"document.action": request.action}) as span:
            result = await asyncio.to_thread(self._read, request)
            span.set_attribute("document.returned_passages", len(result.blocks))
            span.set_attribute("document.scan_limited", result.scan_limited)
            span.set_attribute("document.has_more", result.has_more)
            return result

    def _read(self, request: DocumentRead) -> DocumentResult:
        blocks, limited = self._scan(request.document)
        sections: dict[str, dict[str, Any]] = {}
        for b in blocks:
            p = b.payload
            key = section_id(p)
            entry = sections.setdefault(
                key,
                {
                    "section_id": key,
                    "title": " > ".join(p.get("heading_path") or p.get("section_path") or [])
                    or f"Page {p.get('page_number') or '?'}",
                    "page_number": p.get("page_number"),
                    "chunk_count": 0,
                },
            )
            entry["chunk_count"] += 1
        if request.action == "outline":
            entries = list(sections.values())
            page = entries[request.offset : request.offset + request.limit]
            more = len(entries) > request.offset + len(page)
            return DocumentResult(
                [], page, more, limited, request.offset + len(page) if more else None
            )
        selected = blocks
        if request.action == "search":
            terms = request.query.casefold().split()
            if not terms:
                raise ValueError("Search requires a query")
            selected = [
                b
                for b in blocks
                if all(t in str(b.payload.get("text", "")).casefold() for t in terms)
            ]
        elif request.action == "section":
            selected = [b for b in blocks if section_id(b.payload) == request.section_id]
        elif request.action == "page":
            selected = [
                b
                for b in blocks
                if int(b.payload.get("page_number") or 0)
                <= request.page
                <= int(b.payload.get("page_end") or b.payload.get("page_number") or 0)
            ]
        elif request.action == "neighbors":
            index = next((i for i, b in enumerate(blocks) if b.id == request.chunk_id), None)
            selected = (
                []
                if index is None
                else blocks[max(0, index - request.radius) : index + request.radius + 1]
            )
        # Return whole passages, never silently cut a qualifier or table row.
        page_blocks: list[SearchResult] = []
        chars = 0
        for b in selected[request.offset : request.offset + request.limit]:
            cost = len(str(b.payload.get("text", "")))
            if chars + cost > 60000:
                break
            page_blocks.append(b)
            chars += cost
        more = len(selected) > request.offset + len(page_blocks)
        return DocumentResult(
            page_blocks,
            [],
            more,
            limited,
            request.offset + len(page_blocks) if more and page_blocks else None,
        )


DocumentReaderFactory = Callable[[RetrievalContext, list[str] | None], DocumentReader]
