import re
from dataclasses import dataclass

from app.retrieval.hybrid_search import SearchResult

_CITATION_RE = re.compile(r"\[s\.([\w\-]+):([\w\-]+)/(\d+)/(\d+)\]")


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    citations_found: list[tuple[str, str, int, int]]
    ungrounded_citations: list[tuple[str, str, int, int]]


def check_grounding(answer: str, chunks: list[SearchResult]) -> GroundingResult:
    """Post-hoc check: does every [s.<source_type>:<source_id>/<page>/<paragraph>]
    citation in the answer correspond to a chunk that was actually in the
    context, from the SAME source? Runs after generation completes.

    The (source_type, source_id) pair is required (not just page/paragraph)
    because two different sources in the same collection can share the same
    (page, paragraph) coordinates — a citation must be validated against the
    exact source it claims, not just any chunk with matching coordinates
    anywhere in context.
    """
    valid_locations = {
        (
            c.payload.get("source_type", "doc"),
            c.payload.get("source_id", "doc"),
            c.payload["page_number"],
            c.payload["paragraph_index"],
        )
        for c in chunks
    }

    citations_found = [
        (source_type, source_id, int(page), int(paragraph))
        for source_type, source_id, page, paragraph in _CITATION_RE.findall(answer)
    ]
    ungrounded_citations = [c for c in citations_found if c not in valid_locations]

    return GroundingResult(
        grounded=len(ungrounded_citations) == 0,
        citations_found=citations_found,
        ungrounded_citations=ungrounded_citations,
    )
