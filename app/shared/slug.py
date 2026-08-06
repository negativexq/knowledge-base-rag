import re


def slugify(name: str, strip_extension: bool = True) -> str:
    """Citation-tag-safe identifier derived from a filename or title
    (non-word characters collapsed to `_`). Shared by ingestion (assigning
    a chunk's source_id) and the LLM layer (building and validating
    citation tags), so a citation is always checked against the exact same
    source_id it was built from.

    strip_extension=False keeps the extension as part of the slug — needed
    when a single connector can list same-stem files of different formats
    (e.g. "handbook.pdf" and "handbook.md"), where stripping it would
    collide both onto the same source_id and corrupt the registry's
    (source_type, source_id) primary key.
    """
    stem = name.rsplit(".", 1)[0] if strip_extension and "." in name else name
    return re.sub(r"[^\w\-]", "_", stem) or "doc"
