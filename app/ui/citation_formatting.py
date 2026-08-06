import re

_CITATION_RE = re.compile(r"\[s\.[\w\-]+:[\w\-]+/\d+/\d+\]")


def highlight_citations(text: str) -> str:
    """Wrap [s.source_type:source_id/page/paragraph] citation markers in bold
    Markdown so they stand out visually in the Streamlit chat, without
    needing them to be clickable. Also escapes bare `$` so Streamlit's
    markdown renderer doesn't mistake dollar amounts (e.g. "$2.99/month")
    for LaTeX math.
    """
    escaped = text.replace("$", "\\$")
    return _CITATION_RE.sub(lambda m: f"**{m.group(0)}**", escaped)
