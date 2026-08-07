from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnectorDocument:
    """A document a Connector knows about, not yet chunked.

    source_id must be citation-tag-safe (see app/shared/slug.py) — paired
    with the connector's source_type, it becomes the PK the registry stores
    this document under and the SOURCE_TYPE:SOURCE_ID segment of every
    citation tag chunked from it.

    content_type picks which parser ingest_connector uses ("pdf" |
    "markdown" | "notion"). path is filesystem-specific
    (LocalFilesystemConnector parses from a real file); it's None for
    connectors with no local file to point at.

    etag is a cheap staleness marker a connector may already have on hand
    from list_documents() (e.g. Notion's last_edited_time) — when set,
    get_content_hash() can hash just this instead of fetching the full
    document, so an unchanged-content check (Sprint 4's has_changed(), run
    on every sync) doesn't pay a full-fetch API cost for documents that
    turn out not to have changed. None for connectors where reading the
    full content is already cheap (LocalFilesystemConnector: local disk).
    """

    source_id: str
    content_type: str
    path: Path | None = None
    etag: str | None = None


@runtime_checkable
class Connector(Protocol):
    """async because a real remote connector (Notion, ...) needs network
    I/O here. See docs/adr/0001-connector-interface-is-async.md for why.
    """

    source_type: str

    async def list_documents(self) -> list[ConnectorDocument]: ...
    async def fetch_content(self, document: ConnectorDocument) -> bytes: ...
    async def get_content_hash(self, document: ConnectorDocument) -> str: ...
