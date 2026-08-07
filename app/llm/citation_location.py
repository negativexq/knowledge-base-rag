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
    """
    heading_path = payload.get("heading_path") or []
    if heading_path:
        location = "/".join(heading_path)
        occurrence = payload.get("heading_occurrence") or 0
        if occurrence:
            location = f"{location}#{occurrence + 1}"
        return location
    return f"{payload['page_number']}/{payload['paragraph_index']}"
