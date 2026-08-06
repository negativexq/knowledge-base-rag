from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    source_type: str
    source_id: str
    page_number: int
    paragraph_index: int
    char_range: tuple[int, int]
    text: str
    # Markdown-only: heading stack (H1 > H2 > ...) covering this chunk, e.g.
    # ("Kurulum", "Adım 1"). Empty for PDF chunks. When non-empty, this is
    # what the citation location is built from instead of page_number/
    # paragraph_index — see app/llm/citation_location.py.
    heading_path: tuple[str, ...] = ()
