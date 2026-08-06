import re
from dataclasses import dataclass

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult

# location is a single opaque string — "2/0" for a PDF page/paragraph,
# "Kurulum/Adım 1" for a markdown heading path. It can't be constrained to
# digits the way the Sprint 0/1 format was, since markdown locations aren't
# numeric — so this captures everything up to the closing "]" instead.
_CITATION_RE = re.compile(r"\[s\.([\w\-]+):([\w\-]+)/([^\]]+)\]")


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    citations_found: list[tuple[str, str, str]]
    ungrounded_citations: list[tuple[str, str, str]]


def check_grounding(answer: str, chunks: list[SearchResult]) -> GroundingResult:
    """Post-hoc check: does every [s.<source_type>:<source_id>/<location>]
    citation in the answer correspond to a chunk that was actually in the
    context, from the SAME source? Runs after generation completes.

    The (source_type, source_id) pair is required (not just location)
    because two different sources in the same collection can share the same
    location (e.g. two PDFs both citing page 2, paragraph 0) — a citation
    must be validated against the exact source it claims, not just any
    chunk with a matching location anywhere in context.
    """
    valid_locations = {
        (
            c.payload.get("source_type", "doc"),
            c.payload.get("source_id", "doc"),
            location_for(c.payload),
        )
        for c in chunks
    }

    citations_found = list(_CITATION_RE.findall(answer))
    ungrounded_citations = [c for c in citations_found if c not in valid_locations]

    return GroundingResult(
        grounded=len(ungrounded_citations) == 0,
        citations_found=citations_found,
        ungrounded_citations=ungrounded_citations,
    )
