import hashlib
from pathlib import Path

from app.connectors.base import ConnectorDocument
from app.shared.slug import slugify

_EXTENSION_TO_CONTENT_TYPE = {".pdf": "pdf", ".md": "markdown"}


class LocalFilesystemConnector:
    """Scans one local folder, non-recursively (matching Sprint 0's
    ingest_path glob("*.pdf") precedent — subfolder support is a real but
    unproven need, not added speculatively).
    """

    source_type = "filesystem"

    def __init__(self, root: str | Path):
        self._root = Path(root)

    async def list_documents(self) -> list[ConnectorDocument]:
        paths = sorted(
            p
            for p in self._root.iterdir()
            if p.is_file() and p.suffix.lower() in _EXTENSION_TO_CONTENT_TYPE
        )
        return [
            ConnectorDocument(
                # strip_extension=False: a folder can hold "handbook.pdf"
                # and "handbook.md" side by side — stripping the extension
                # would collide both onto the same source_id and corrupt
                # the registry's (source_type, source_id) primary key.
                source_id=slugify(p.name, strip_extension=False),
                content_type=_EXTENSION_TO_CONTENT_TYPE[p.suffix.lower()],
                path=p,
            )
            for p in paths
        ]

    async def fetch_content(self, document: ConnectorDocument) -> bytes:
        return document.path.read_bytes()

    async def get_content_hash(self, document: ConnectorDocument) -> str:
        # Same algorithm as app/ingestion/chunker.py::compute_doc_id (sha256
        # of raw file bytes) — ingest_connector passes this hash straight
        # into chunk_document/chunk_markdown_document's doc_id override, so
        # the file is never read+hashed twice with a risk of divergence.
        return hashlib.sha256(await self.fetch_content(document)).hexdigest()
