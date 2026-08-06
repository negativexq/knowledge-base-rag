from dataclasses import dataclass


@dataclass(frozen=True)
class Paragraph:
    page_number: int
    paragraph_index: int
    text: str
