"""Deterministic, ACL-scoped section-aware evidence presentation.

This module is deliberately a presentation step, not a second retrieval
system. It starts with the authorized reranked anchors and may only recover
points from the same tenant, source and logical section. It is enabled only by
the evidence-backed runtime path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext

# Points read per scroll request; a source is read to its end.
SCROLL_PAGE_SIZE = 1000
# A later anchor is cut to the remaining budget only when at least this
# much is left; a shorter tail is noise.
MIN_PARTIAL_TOKENS = 50


@dataclass(frozen=True)
class EvidenceBuildResult:
    blocks: list[SearchResult]
    input_chunk_ids: list[str]
    contributing_chunk_ids: list[str]
    context_tokens: int
    expanded: bool
    budget_exhausted: bool = False
    truncated_block_count: int = 0
    dropped_expansion_count: int = 0


def _section_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    headings = tuple(payload.get("heading_path") or ())
    if headings:
        return ("heading", headings, int(payload.get("heading_occurrence") or 0))
    # PDF chunks carry the section path of the document element they came
    # from; a PDF without detected headings falls back to its page, the
    # smallest stable logical section in that representation.
    sections = tuple(payload.get("section_path") or ())
    if sections:
        return ("section", sections)
    return ("page", payload.get("page_number"))


def _chunk_id(result: SearchResult) -> str:
    return result.id or str(result.payload.get("chunk_id", ""))


def _sort_key(result: SearchResult) -> tuple[Any, ...]:
    payload = result.payload
    char_range = payload.get("char_range") or [0, 0]
    return (
        int(payload.get("page_number") or 0),
        int(payload.get("paragraph_index") or 0),
        int(char_range[0] or 0),
        _chunk_id(result),
    )


def _estimate_tokens(text: str) -> int:
    """Fallback budget unit when no tokenizer is given: whitespace words."""
    return len(text.split())


def _cut_text(text: str, token_limit: int, count_tokens: Callable[[str], int]) -> str:
    """The longest prefix ending at a word that fits ``token_limit``. The
    text between words is kept as written, so paragraph breaks survive."""
    ends = [match.end() for match in re.finditer(r"\S+", text)]
    low, high = 0, min(len(ends), max(0, token_limit))
    while low < high:
        middle = (low + high + 1) // 2
        if count_tokens(text[: ends[middle - 1]]) <= token_limit:
            low = middle
        else:
            high = middle - 1
    return text[: ends[low - 1]] if low else ""


def _cut_chunk(
    item: SearchResult, token_limit: int, count_tokens: Callable[[str], int]
) -> SearchResult:
    payload = dict(item.payload)
    payload["text"] = _cut_text(str(payload.get("text", "")), token_limit, count_tokens)
    payload["truncated"] = True
    return SearchResult(score=item.score, id=item.id, payload=payload)


def _identity_alias(result: SearchResult) -> dict[str, Any]:
    payload = result.payload
    return {
        "chunk_id": _chunk_id(result),
        "source_type": payload.get("source_type", "doc"),
        "source_id": payload.get("source_id", "doc"),
        "location": location_for(payload),
    }


class SectionAwareEvidenceBuilder:
    """Expand BGE anchors within their already-authorized logical sections."""

    # Replaced per instance in __init__; the class default keeps instances
    # made without __init__ (tests) on the word-count fallback.
    _count: Callable[[str], int] = staticmethod(_estimate_tokens)

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        *,
        token_budget: int = 1200,
        count_tokens: Callable[[str], int] | None = None,
    ) -> None:
        """``count_tokens`` is the unit of ``token_budget``; production passes
        the generation model's tokenizer. Without it the budget counts words,
        which undercounts Turkish by about 2.5-3x."""
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self._client = client
        self._collection_name = collection_name
        self._token_budget = token_budget
        counter = count_tokens or _estimate_tokens
        cache: dict[str, int] = {}

        def cached(text: str) -> int:
            # Expansion re-measures the whole output for every candidate.
            if text not in cache:
                cache[text] = counter(text)
            return cache[text]

        self._count = cached

    def _scroll_source(self, anchor: SearchResult, context: RetrievalContext) -> list[SearchResult]:
        payload = anchor.payload
        must = [
            qmodels.FieldCondition(
                key="source_type", match=qmodels.MatchValue(value=payload.get("source_type"))
            ),
            qmodels.FieldCondition(
                key="source_id", match=qmodels.MatchValue(value=payload.get("source_id"))
            ),
            qmodels.FieldCondition(
                key="document_version",
                match=qmodels.MatchValue(value=payload.get("document_version")),
            ),
        ]
        if not context.is_system:
            if not context.tenant_id:
                # RetrievalContext already fails closed, but keep this
                # boundary local so an expansion can never be unrestricted.
                return []
            must.append(
                qmodels.FieldCondition(
                    key="tenant_id", match=qmodels.MatchValue(value=context.tenant_id)
                )
            )
        points: list[Any] = []
        offset = None
        while True:
            page, offset = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=qmodels.Filter(must=must),
                limit=SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points += page
            if offset is None:
                break
        return [
            SearchResult(score=anchor.score, id=str(point.id), payload=dict(point.payload or {}))
            for point in points
            if context.is_system or point.payload.get("tenant_id") == context.tenant_id
        ]

    @staticmethod
    def _same_section(anchor: SearchResult, candidates: list[SearchResult]) -> list[SearchResult]:
        anchor_payload = anchor.payload
        anchor_key = _section_key(anchor_payload)
        source = anchor_payload.get("source_id")
        version = anchor_payload.get("document_version")
        tenant = anchor_payload.get("tenant_id")
        return [
            item
            for item in candidates
            if item.payload.get("source_id") == source
            and item.payload.get("document_version") == version
            and item.payload.get("tenant_id") == tenant
            and _section_key(item.payload) == anchor_key
        ]

    def _select_source_sections(
        self, anchor: SearchResult, candidates: list[SearchResult]
    ) -> list[SearchResult]:
        """Keep a compact source's section structure together.

        The canonical standard-return fact is in the document preamble while
        its retrieved anchor is in ``Case record``.  Treating every heading
        as an isolated island would lose that legitimate relationship.  A
        small source can therefore be merged in full; larger sources fall
        back to the anchor section, then deterministic adjacent sections
        within the same source and budget.
        """
        ordered = sorted(candidates, key=_sort_key)
        if not ordered:
            return [anchor]
        total = sum(self._count(str(item.payload.get("text", ""))) for item in ordered)
        if total <= self._token_budget:
            return ordered
        same = self._same_section(anchor, ordered)
        return same or [anchor]

    @staticmethod
    def _same_authorized_boundary(
        anchor: SearchResult, candidate: SearchResult, context: RetrievalContext
    ) -> bool:
        anchor_payload = anchor.payload
        candidate_payload = candidate.payload
        if (
            candidate_payload.get("source_type") != anchor_payload.get("source_type")
            or candidate_payload.get("source_id") != anchor_payload.get("source_id")
            or candidate_payload.get("document_version") != anchor_payload.get("document_version")
            or candidate_payload.get("tenant_id") != anchor_payload.get("tenant_id")
        ):
            return False
        return context.is_system or candidate_payload.get("tenant_id") == context.tenant_id

    @staticmethod
    def _unique_ranked(anchors: list[SearchResult]) -> list[SearchResult]:
        """Anchors in reranker order, each chunk once."""
        seen: set[str] = set()
        ranked = []
        for anchor in anchors:
            if _chunk_id(anchor) not in seen:
                seen.add(_chunk_id(anchor))
                ranked.append(anchor)
        return ranked

    @staticmethod
    def _unique_chunks(chunks: list[SearchResult]) -> list[SearchResult]:
        result: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        for item in sorted(chunks, key=_sort_key):
            identity = (_chunk_id(item), str(item.payload.get("text", "")))
            if identity in seen:
                continue
            seen.add(identity)
            result.append(item)
        return result

    @staticmethod
    def _truncate_block(
        block: SearchResult,
        token_limit: int,
        count_tokens: Callable[[str], int] = _estimate_tokens,
    ) -> SearchResult:
        """Truncate only content, retaining the block's provenance metadata.
        Keeps the longest whole-word prefix that fits ``token_limit``."""
        text = str(block.payload.get("text", ""))
        original_count = count_tokens(text)
        visible_text = _cut_text(text, token_limit, count_tokens)
        visible_count = count_tokens(visible_text)
        block.payload["text"] = visible_text
        # The words no longer map back onto chunk boundaries.
        block.payload.pop("section_chunks", None)
        block.payload["token_count"] = visible_count
        block.payload["truncated"] = True
        block.payload["original_token_count"] = original_count
        block.payload["visible_token_count"] = visible_count
        return block

    @staticmethod
    def _block(
        anchor: SearchResult,
        section_chunks: list[SearchResult],
        count_tokens: Callable[[str], int] = _estimate_tokens,
    ) -> SearchResult:
        ordered = sorted(section_chunks, key=_sort_key)
        ids = [_chunk_id(item) for item in ordered]
        text = "\n\n".join(str(item.payload.get("text", "")) for item in ordered)
        anchor_payload = dict(anchor.payload)
        aliases = [_identity_alias(item) for item in ordered]
        section_json = json.dumps(
            {
                "source_type": anchor_payload.get("source_type", "doc"),
                "source_id": anchor_payload.get("source_id", "doc"),
                "version": anchor_payload.get("document_version"),
                "section": _section_key(anchor_payload),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        block_id = "evidence-" + hashlib.sha256(section_json.encode()).hexdigest()[:24]
        anchor_payload.update(
            {
                "text": text,
                "chunk_id": block_id,
                "evidence_block_id": block_id,
                "contributing_chunk_ids": ids,
                "citation_aliases": aliases,
                "section_aware": True,
                "section_key": list(_section_key(anchor_payload)),
                "anchor_chunk_id": _chunk_id(anchor),
                "token_count": count_tokens(text),
                # Per-chunk provenance, in text order: the block section is the
                # anchor's, but a merged small source spans several sections.
                "section_chunks": [
                    {
                        "chunk_id": _chunk_id(item),
                        "text": str(item.payload.get("text", "")),
                        "section_key": list(_section_key(item.payload)),
                        "heading_path": list(item.payload.get("heading_path") or []),
                        "section_path": list(item.payload.get("section_path") or []),
                        "page_number": item.payload.get("page_number"),
                        "page_end": item.payload.get("page_end"),
                    }
                    for item in ordered
                ],
            }
        )
        return SearchResult(score=anchor.score, id=block_id, payload=anchor_payload)

    def _group_block(self, group: dict[str, Any], chunks: list[SearchResult]) -> SearchResult:
        """A source group's block; a cut anchor marks the block truncated."""
        block = self._block(group["anchor"], chunks, self._count)
        if any(item.payload.get("truncated") for item in chunks):
            full = {_chunk_id(item): item for item in group["anchors"]}
            original = "\n\n".join(
                str(full.get(_chunk_id(item), item).payload.get("text", ""))
                for item in sorted(chunks, key=_sort_key)
            )
            block.payload["truncated"] = True
            block.payload["original_token_count"] = self._count(original)
            block.payload["visible_token_count"] = block.payload["token_count"]
        return block

    async def build(
        self, anchors: list[SearchResult], context: RetrievalContext
    ) -> EvidenceBuildResult:
        """Build evidence with anchor-first, graceful global budget allocation.

        Anchor chunks are reserved before any same-source section expansion.
        Expansion is opportunistic: a candidate that does not fit in the
        remaining global budget is skipped, while the valid anchor set is
        still returned.  This keeps budget pressure from becoming a query
        failure and preserves the existing source/version/tenant boundary.
        """
        input_ids = [_chunk_id(anchor) for anchor in anchors]
        groups: list[dict[str, Any]] = []
        group_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        for anchor in anchors:
            key = (
                anchor.payload.get("tenant_id"),
                anchor.payload.get("source_type"),
                anchor.payload.get("source_id"),
                anchor.payload.get("document_version"),
            )
            group = group_by_key.get(key)
            if group is None:
                group = {"anchor": anchor, "anchors": [], "points": [], "selected": []}
                group_by_key[key] = group
                groups.append(group)
            group["anchors"].append(anchor)

        for group in groups:
            anchor = group["anchor"]
            points = await asyncio.to_thread(self._scroll_source, anchor, context)
            points = [
                item for item in points if self._same_authorized_boundary(anchor, item, context)
            ]
            # A provider/storage race must not erase an anchor from the
            # model-visible evidence boundary.
            group["points"] = self._unique_chunks(points + group["anchors"])
            group["selected"] = self._unique_chunks(group["anchors"])

        # Phase A: reserve anchors in rank order.  Each source's best anchor
        # comes first (a fair share each when they do not all fit, so the
        # first large source cannot starve the others); then the remaining
        # anchors in reranker order, the last one cut to what is left.  A
        # cut keeps chunk and paragraph boundaries, and the block lists its
        # chunks in document order, so every unit keeps its own page.
        count = self._count
        separator = max(0, count("x\n\nx") - 2 * count("x"))
        chosen: list[list[SearchResult]] = [[] for _ in groups]
        taken: set[str] = set()
        truncated_count = 0
        budget_exhausted = False
        group_index = {id(group): index for index, group in enumerate(groups)}
        anchor_group: dict[str, int] = {}
        for group in groups:
            for anchor in group["anchors"]:
                anchor_group.setdefault(_chunk_id(anchor), group_index[id(group)])

        def cost(index: int, tokens: int) -> int:
            return tokens + (separator if chosen[index] else 0)

        def take(index: int, item: SearchResult, limit: int | None = None) -> int:
            nonlocal truncated_count
            if limit is not None:
                item = _cut_chunk(item, limit, count)
                truncated_count += 1
            used = cost(index, count(str(item.payload.get("text", ""))))
            chosen[index].append(item)
            taken.add(_chunk_id(item))
            return used

        # A group's anchor is its first, i.e. best-ranked, chunk.
        tops = [group["anchor"] for group in groups]
        top_sizes = [count(str(top.payload.get("text", ""))) for top in tops]
        allocations = list(top_sizes)
        if sum(top_sizes) > self._token_budget:
            budget_exhausted = True
            allocations = [0] * len(groups)
            remaining = self._token_budget
            while remaining > 0 and any(
                size > allocation for size, allocation in zip(top_sizes, allocations)
            ):
                for index, size in enumerate(top_sizes):
                    if remaining <= 0:
                        break
                    if allocations[index] < size:
                        allocations[index] += 1
                        remaining -= 1
        remaining = self._token_budget
        for index, (top, size, allocation) in enumerate(zip(tops, top_sizes, allocations)):
            if allocation <= 0:
                continue
            remaining -= take(index, top, None if allocation >= size else allocation)

        for anchor in self._unique_ranked(anchors):
            if _chunk_id(anchor) in taken:
                continue
            index = anchor_group[_chunk_id(anchor)]
            size = count(str(anchor.payload.get("text", "")))
            if cost(index, size) <= remaining:
                remaining -= take(index, anchor)
                continue
            budget_exhausted = True
            room = remaining - cost(index, 0)
            if room >= MIN_PARTIAL_TOKENS:
                remaining -= take(index, anchor, room)

        output: list[SearchResult] = []
        output_index_by_group: dict[int, int] = {}
        for index, group in enumerate(groups):
            if not chosen[index]:
                continue
            block = self._group_block(group, chosen[index])
            group["selected"] = chosen[index]
            output_index_by_group[id(group)] = len(output)
            output.append(block)

        # Phase B: add only same-boundary section candidates that fit the
        # remaining global budget.  The already reserved blocks are never
        # removed for expansion.
        dropped_expansions = 0
        expanded = False
        for index, group in enumerate(groups):
            output_index = output_index_by_group.get(id(group))
            if output_index is None:
                # This can only happen when the budget is smaller than the
                # number of non-empty anchor groups.
                dropped_expansions += max(0, len(group["points"]) - len(group["selected"]))
                continue
            current_chunks = list(group["selected"])
            section = self._select_source_sections(group["anchor"], group["points"])
            candidates = self._unique_chunks(
                [
                    item
                    for item in section
                    if self._same_authorized_boundary(group["anchor"], item, context)
                ]
            )
            selected_ids = {_chunk_id(item) for item in current_chunks}
            # Each candidate is priced on its own (text plus a separator)
            # against a running total, instead of re-tokenizing the whole
            # output per candidate, which was quadratic in the budget.
            total = sum(count(str(item.payload.get("text", ""))) for item in output)
            added: list[SearchResult] = []
            for candidate in candidates:
                if _chunk_id(candidate) in selected_ids:
                    continue
                price = count(str(candidate.payload.get("text", ""))) + separator
                if total + price <= self._token_budget:
                    added.append(candidate)
                    selected_ids.add(_chunk_id(candidate))
                    total += price
                else:
                    budget_exhausted = True
                    dropped_expansions += 1
            while added:
                trial = list(output)
                trial[output_index] = self._group_block(group, current_chunks + added)
                exact = sum(count(str(item.payload.get("text", ""))) for item in trial)
                if exact <= self._token_budget:
                    output = trial
                    current_chunks += added
                    expanded = True
                    break
                # Token counts are not exactly additive; give back the last one.
                added.pop()
                dropped_expansions += 1
            group["selected"] = current_chunks

        context_tokens = sum(self._count(str(block.payload.get("text", ""))) for block in output)
        for index, block in enumerate(output, 1):
            block.payload["evidence_id"] = f"E{index}"
        return EvidenceBuildResult(
            blocks=output,
            input_chunk_ids=input_ids,
            contributing_chunk_ids=[
                chunk_id
                for block in output
                for chunk_id in block.payload.get("contributing_chunk_ids", [])
            ],
            context_tokens=context_tokens,
            expanded=expanded,
            budget_exhausted=budget_exhausted,
            truncated_block_count=truncated_count,
            dropped_expansion_count=dropped_expansions,
        )


def serialize_section_aware_context(chunks: list[SearchResult]) -> str:
    """Serialize v2 blocks; raw document content remains untrusted data."""
    from app.llm.trust_boundary import _safe_json

    records: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        payload = chunk.payload
        metadata = {
            "evidence_id": payload.get("evidence_id", f"E{index}"),
            "evidence_block_id": payload.get("evidence_block_id", _chunk_id(chunk)),
            "source_type": payload.get("source_type", "doc"),
            "source_id": payload.get("source_id", "doc"),
            "location": location_for(payload),
            "section_key": payload.get("section_key"),
            "document_version": payload.get("document_version"),
            "tenant_id": payload.get("tenant_id"),
            "contributing_chunk_ids": payload.get("contributing_chunk_ids", [_chunk_id(chunk)]),
            "citation_aliases": payload.get("citation_aliases", [_identity_alias(chunk)]),
        }
        metadata["canonical_citations"] = [
            f"[s.{alias['source_type']}:{alias['source_id']}/{alias['location']}]"
            for alias in metadata["citation_aliases"]
            if isinstance(alias, dict) and alias.get("location") is not None
        ]
        encoded = _safe_json({"metadata": metadata, "content": payload.get("text", "")})
        records.append(
            f"[evidence_block {index} json_chars={len(encoded)}]\n"
            f"EVIDENCE METADATA (server-generated):\n{encoded}\n"
            f"[/evidence_block {index}]"
        )
    return (
        '<section_aware_evidence trust="untrusted" blocks="{}">\n{}\n' "</section_aware_evidence>"
    ).format(len(records), "\n".join(records))
