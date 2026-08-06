def location_for(payload: dict) -> str:
    """The LOCATION segment of a citation tag ([s.source_type:source_id/
    LOCATION]), derived the same way whether building a tag (prompt.py) or
    validating one (grounding.py) — so a citation is always checked
    against exactly what it was built from.

    Markdown chunks carry a non-empty heading_path (H1 > H2 > ...); their
    location is that path joined with "/", e.g. "Kurulum/Adım 1". Anything
    else (PDF chunks, or markdown content that appears before its first
    heading — rare) falls back to the page/paragraph pair PDF chunks use.
    """
    heading_path = payload.get("heading_path") or []
    if heading_path:
        return "/".join(heading_path)
    return f"{payload['page_number']}/{payload['paragraph_index']}"
