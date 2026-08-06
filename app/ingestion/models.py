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
