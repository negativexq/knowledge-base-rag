from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ConnectorDocument:
    """A document a Connector knows about, not yet chunked.

    source_id must be citation-tag-safe (see app/shared/slug.py) — paired
    with the connector's source_type, it becomes the PK the registry stores
    this document under and the SOURCE_TYPE:SOURCE_ID segment of every
    citation tag chunked from it.

    content_type picks which parser ingest_connector uses ("pdf" |
    "markdown"). path is filesystem-specific (LocalFilesystemConnector
    parses from a real file); it's None for connectors with no local file
    to point at (e.g. a future Notion connector) — see docs/sprint-03-plan.md
    for why ingest_connector isn't yet generalized to work without it.
    """

    source_id: str
    content_type: str
    path: Path | None = None


class Connector(Protocol):
    source_type: str

    def list_documents(self) -> list[ConnectorDocument]: ...
    def fetch_content(self, document: ConnectorDocument) -> bytes: ...
    def get_content_hash(self, document: ConnectorDocument) -> str: ...
