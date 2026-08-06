import re


def slugify(name: str) -> str:
    """Citation-tag-safe identifier derived from a filename or title
    (extension stripped, non-word characters collapsed to `_`). Shared by
    ingestion (assigning a chunk's source_id) and the LLM layer (building
    and validating citation tags), so a citation is always checked against
    the exact same source_id it was built from.
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"[^\w\-]", "_", stem) or "doc"
