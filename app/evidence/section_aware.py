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
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext


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
    # PDF ingestion has no markdown heading path.  A page is the smallest
    # stable logical section available in that representation.
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
    return len(text.split())


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

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        *,
        token_budget: int = 1200,
    ) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self._client = client
        self._collection_name = collection_name
        self._token_budget = token_budget

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
        points, _ = self._client.scroll(
            collection_name=self._collection_name,
            scroll_filter=qmodels.Filter(must=must),
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
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
        total = sum(_estimate_tokens(str(item.payload.get("text", ""))) for item in ordered)
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
            or candidate_payload.get("document_version")
            != anchor_payload.get("document_version")
            or candidate_payload.get("tenant_id") != anchor_payload.get("tenant_id")
        ):
            return False
        return context.is_system or candidate_payload.get("tenant_id") == context.tenant_id

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
    def _truncate_block(block: SearchResult, token_limit: int) -> SearchResult:
        """Truncate only content, retaining the block's provenance metadata."""
        text = str(block.payload.get("text", ""))
        original_count = _estimate_tokens(text)
        visible_words = text.split()[: max(0, token_limit)]
        visible_text = " ".join(visible_words)
        block.payload["text"] = visible_text
        block.payload["token_count"] = len(visible_words)
        block.payload["truncated"] = True
        block.payload["original_token_count"] = original_count
        block.payload["visible_token_count"] = len(visible_words)
        return block

    @staticmethod
    def _block(anchor: SearchResult, section_chunks: list[SearchResult]) -> SearchResult:
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
                "token_count": _estimate_tokens(text),
            }
        )
        return SearchResult(score=anchor.score, id=block_id, payload=anchor_payload)

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
                item
                for item in points
                if self._same_authorized_boundary(anchor, item, context)
            ]
            # A provider/storage race must not erase an anchor from the
            # model-visible evidence boundary.
            group["points"] = self._unique_chunks(points + group["anchors"])
            group["selected"] = self._unique_chunks(group["anchors"])

        # Phase A: reserve anchor content fairly.  If all anchors fit, no
        # truncation is needed.  Otherwise each source group receives an
        # initial token and the remaining budget is distributed round-robin,
        # preventing the first large source from starving later anchors.
        full_anchor_blocks = [
            self._block(group["anchor"], group["selected"]) for group in groups
        ]
        full_anchor_sizes = [
            _estimate_tokens(str(block.payload.get("text", "")))
            for block in full_anchor_blocks
        ]
        allocations = list(full_anchor_sizes)
        anchor_total = sum(full_anchor_sizes)
        budget_exhausted = False
        if anchor_total > self._token_budget:
            budget_exhausted = True
            allocations = [0] * len(groups)
            remaining = self._token_budget
            while remaining and any(
                size > allocation
                for size, allocation in zip(full_anchor_sizes, allocations)
            ):
                progressed = False
                for index, size in enumerate(full_anchor_sizes):
                    if remaining <= 0:
                        break
                    if allocations[index] < size:
                        allocations[index] += 1
                        remaining -= 1
                        progressed = True
                if not progressed:
                    break

        output: list[SearchResult] = []
        truncated_count = 0
        output_index_by_group: dict[int, int] = {}
        for group, block, allocation, full_size in zip(
            groups, full_anchor_blocks, allocations, full_anchor_sizes
        ):
            if allocation <= 0:
                continue
            if full_size > allocation:
                self._truncate_block(block, allocation)
                truncated_count += 1
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
            for candidate in candidates:
                if _chunk_id(candidate) in selected_ids:
                    continue
                trial_chunks = current_chunks + [candidate]
                trial_block = self._block(group["anchor"], trial_chunks)
                trial_output = list(output)
                trial_output[output_index] = trial_block
                trial_tokens = sum(
                    _estimate_tokens(str(item.payload.get("text", "")))
                    for item in trial_output
                )
                if trial_tokens <= self._token_budget:
                    current_chunks.append(candidate)
                    selected_ids.add(_chunk_id(candidate))
                    output = trial_output
                    expanded = True
                else:
                    budget_exhausted = True
                    dropped_expansions += 1

            group["selected"] = current_chunks

        context_tokens = sum(
            _estimate_tokens(str(block.payload.get("text", ""))) for block in output
        )
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
        '<section_aware_evidence trust="untrusted" blocks="{}">\n{}\n'
        "</section_aware_evidence>"
    ).format(
        len(records), "\n".join(records)
    )
