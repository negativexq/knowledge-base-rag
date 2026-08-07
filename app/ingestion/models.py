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
    # Same value as doc_id (the content hash) today, but a separate,
    # explicitly-named field: doc_id's job is "one ingredient of a unique
    # point ID," document_version's job is the filter key
    # QdrantStore.delete_stale_versions() deletes by during a deferred-
    # cleanup re-index (Sprint 13) — kept decoupled from doc_id so a future
    # change to point-ID hashing can't silently break re-index cleanup.
    # Defaulted for the same backward-compatibility reason heading_path
    # was (Sprint 3) — every existing Chunk(...) call site keeps working.
    document_version: str = ""
