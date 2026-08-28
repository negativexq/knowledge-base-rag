import re
from dataclasses import dataclass

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult

# location is a single opaque string — "2/0" for a PDF page/paragraph,
# "Kurulum/Adım 1" for a markdown heading path. It can't be constrained to
# digits the way the Sprint 0/1 format was, since markdown locations aren't
# numeric — so this captures everything up to the closing "]" instead.
_CITATION_RE = re.compile(r"\[s\.([\w\-]+):([^/\]]+)/([^\]]+)\]")


def extract_citations(answer: str) -> list[tuple[str, str, str]]:
    """Return server-contract citation identities found in candidate text."""
    return list(_CITATION_RE.findall(answer))


def _valid_citation_identities(chunks: list[SearchResult]) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        payload = chunk.payload
        identities.add(
            (
                payload.get("source_type", "doc"),
                payload.get("source_id", "doc"),
                location_for(payload),
            )
        )
        for alias in payload.get("citation_aliases", []):
            if isinstance(alias, dict) and alias.get("location") is not None:
                identities.add(
                    (
                        str(alias.get("source_type", "doc")),
                        str(alias.get("source_id", "doc")),
                        str(alias["location"]),
                    )
                )
    return identities


def citation_identity_status(
    citation: str, chunks: list[SearchResult]
) -> str:
    """Classify one citation without broadening the authorized boundary.

    Exact identity is preferred.  A case-insensitive match is accepted only
    when it resolves to one and only one identity already present in the
    authorized context.  This handles models copying human-readable heading
    labels with different casing while never accepting a new source/location.
    """
    found = extract_citations(citation)
    if len(found) != 1 or not found[0][0]:
        return "MALFORMED_CITATION_SYNTAX"
    identities = _valid_citation_identities(chunks)
    if found[0] in identities:
        return "VALID"
    folded = found[0]
    matches = {
        identity
        for identity in identities
        if tuple(part.casefold() for part in identity)
        == tuple(part.casefold() for part in folded)
    }
    if len(matches) == 1:
        return "VALID"
    # The validator only receives the authorized context, not the whole
    # corpus/tenant registry.  An absent identity is therefore safely
    # classified as unknown here; authorization-specific callers can promote
    # it to UNAUTHORIZED when they have a registry-backed tenant fact.
    return "UNKNOWN_CITATION_ID"


@dataclass(frozen=True)
class GroundingResult:
    has_citations: bool
    citations_valid: bool
    grounded: bool
    citations_found: list[tuple[str, str, str]]
    ungrounded_citations: list[tuple[str, str, str]]


def check_grounding(answer: str, chunks: list[SearchResult]) -> GroundingResult:
    """Post-hoc CITATION INTEGRITY check: does every
    [s.<source_type>:<source_id>/<location>] citation in the answer
    correspond to a chunk that was actually in the context, from the SAME
    source? Runs after generation completes.

    This is NOT semantic grounding — it doesn't verify that the claim next
    to a citation is actually supported by that chunk's text, only that
    the citation itself points to something real. A model can cite a real,
    correctly-attributed chunk beside a claim that chunk doesn't support,
    and this still reports grounded=True. Claim-level semantic support
    checking (e.g. NLI/entailment between a claim and its cited text) is
    real future work this doesn't attempt. See docs/sprint-12-plan.md.

    `grounded` requires BOTH `has_citations` and `citations_valid` — an
    answer with zero citations is NOT grounded (it's the most dangerous
    hallucination shape: no citation tag at all to even question), a
    distinct case from "has citations but at least one is fabricated"
    (also not grounded, but a caller like the UI may want to render these
    two differently — see has_citations).

    The (source_type, source_id) pair is required (not just location)
    because two different sources in the same collection can share the same
    location (e.g. two PDFs both citing page 2, paragraph 0) — a citation
    must be validated against the exact source it claims, not just any
    chunk with a matching location anywhere in context.
    """
    citations_found = extract_citations(answer)
    ungrounded_citations = [
        c for c in citations_found
        if citation_identity_status(
            f"[s.{c[0]}:{c[1]}/{c[2]}]", chunks
        ) != "VALID"
    ]

    has_citations = len(citations_found) > 0
    citations_valid = len(ungrounded_citations) == 0

    return GroundingResult(
        has_citations=has_citations,
        citations_valid=citations_valid,
        grounded=has_citations and citations_valid,
        citations_found=citations_found,
        ungrounded_citations=ungrounded_citations,
    )
