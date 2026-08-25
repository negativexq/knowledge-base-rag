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
    # Sprint 17.5: which occurrence of heading_path this chunk belongs to
    # (0-indexed) — needed because the same heading_path can legitimately
    # recur in one document (two separate "# Overview" sections), which
    # heading_path alone can't distinguish. See
    # app/llm/citation_location.py for how this turns into a citation
    # location, and app/parsing/markdown_parser.py::MarkdownBlock for
    # where it's computed.
    heading_occurrence: int = 0
    # Same value as doc_id (the content hash) today, but a separate,
    # explicitly-named field: doc_id's job is "one ingredient of a unique
    # point ID," document_version's job is the filter key
    # QdrantStore.delete_stale_versions() deletes by during a deferred-
    # cleanup re-index (Sprint 13) — kept decoupled from doc_id so a future
    # change to point-ID hashing can't silently break re-index cleanup.
    # Defaulted for the same backward-compatibility reason heading_path
    # was (Sprint 3) — every existing Chunk(...) call site keeps working.
    document_version: str = ""
    # Sprint 23: which tenant owns this chunk — the security boundary
    # this whole field exists for is enforced at retrieval time
    # (app/retrieval/filters.py::build_acl_filter), but it has to be
    # written into every point's Qdrant payload AND folded into the
    # point-identity key (QdrantStore.point_id_for) at ingest time for
    # that enforcement to have anything to filter on. NOT set by the
    # chunker functions themselves (chunk_document/chunk_markdown_*
    # have no notion of tenancy) — app/ingestion/ingest.py::
    # ingest_connector sets it via dataclasses.replace() immediately
    # after chunking, from the tenant_id the caller (SyncManager, itself
    # wired from server-side connector configuration — never a request
    # body value) supplies. Defaulted to "default" for the same
    # backward-compatibility reason document_version was — every
    # existing Chunk(...) call site (chunker/tests) keeps working
    # unchanged; production ingest always overwrites it explicitly.
    tenant_id: str = "default"
