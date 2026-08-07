def _escape_heading_component(component: str) -> str:
    """Escapes the two characters this module gives reserved meaning to
    when assembling a location string: "/" (the component separator) and
    "#" (the occurrence-suffix delimiter, Sprint 17.5). "\\" is escaped
    first so its own escape doesn't get re-escaped by the other two
    replacements.
    """
    return component.replace("\\", "\\\\").replace("/", "\\/").replace("#", "\\#")


def location_for(payload: dict) -> str:
    """The LOCATION segment of a citation tag ([s.source_type:source_id/
    LOCATION]), derived the same way whether building a tag (prompt.py) or
    validating one (grounding.py) — so a citation is always checked
    against exactly what it was built from.

    Markdown chunks carry a non-empty heading_path (H1 > H2 > ...); their
    location is that path joined with "/", e.g. "Kurulum/Adım 1". Anything
    else (PDF chunks, or markdown content that appears before its first
    heading — rare) falls back to the page/paragraph pair PDF chunks use.

    Sprint 17.5: the same heading_path can legitimately occur more than
    once in one document (two separate "# Overview" sections) — without a
    tiebreaker, both occurrences would produce the identical location
    string, making their citations indistinguishable. `heading_occurrence`
    (0 for the first occurrence) is appended as "#N" (1-indexed, so the
    first REPEAT reads "#2") only when it's nonzero, so a heading that
    never repeats keeps the exact location string it always had — no
    change for the common case. This only affects the internal citation
    LOCATION, not the human-facing label (app/llm/prompt.py::_human_label
    still shows the plain heading path).

    Sprint 17.6: the Sprint 17.5 scheme above had two real collisions.
    (a) A document with a heading that's ACTUALLY named e.g. "Overview#2"
    produces the identical location string as the SECOND occurrence of a
    plain "Overview" heading. (b) A heading component containing "/"
    (e.g. "## A/B") produces the identical joined string as two separate
    nested components ["A", "B"]. Fixed by escaping "\\", "/", and "#"
    within each heading component before joining — after escaping, an
    unescaped "#" in the final string can only ever be the occurrence
    delimiter this function appends itself, never part of a real heading,
    so the two can't collide. This only changes locations for headings
    that actually contain "/" or "#" (rare) or that repeat (Sprint 17.5's
    case) — an ordinary, non-repeating, slash/hash-free heading path
    (the common case) still round-trips to the exact string it always
    produced, since escaping a component with none of those characters
    is a no-op.
    """
    heading_path = payload.get("heading_path") or []
    if heading_path:
        location = "/".join(_escape_heading_component(c) for c in heading_path)
        occurrence = payload.get("heading_occurrence") or 0
        if occurrence:
            location = f"{location}#{occurrence + 1}"
        return location
    return f"{payload['page_number']}/{payload['paragraph_index']}"
