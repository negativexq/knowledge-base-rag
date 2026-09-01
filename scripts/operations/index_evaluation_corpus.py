"""Index canonical Evaluation Corpus v2 through the production ingestion path."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.base import ConnectorDocument
from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.index_validation import validate_evaluation_index
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseEncoder
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
MANIFEST_PATH = CORPUS_DIR / "corpus-manifest.json"
FINGERPRINT_PATH = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
DEFAULT_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"


class ManifestFilesystemConnector:
    """Use the real filesystem connector while preserving manifest IDs.

    LocalFilesystemConnector intentionally preserves extensions in slugs so a
    ``file.md`` and ``file.pdf`` can coexist. The evaluation manifest has
    already assigned canonical source IDs, so this adapter changes only that
    identity field; fetching and hashing still delegate to the production
    connector implementation.
    """

    source_type = "filesystem"

    def __init__(self, root: Path, documents: list[dict]):
        self._connector = LocalFilesystemConnector(root)
        self._source_ids = {
            Path(document["path"]).name: document["source_id"] for document in documents
        }

    async def list_documents(self) -> list[ConnectorDocument]:
        documents = await self._connector.list_documents()
        return [
            replace(document, source_id=self._source_ids[document.path.name])
            for document in documents
        ]

    async def fetch_content(self, document: ConnectorDocument) -> bytes:
        return await self._connector.fetch_content(document)

    async def get_content_hash(self, document: ConnectorDocument) -> str:
        return await self._connector.get_content_hash(document)


def _manifest_by_tenant() -> dict[str, list[dict]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for document in manifest["documents"]:
        grouped.setdefault(document["tenant_id"], []).append(document)
    return grouped


async def run(args: argparse.Namespace) -> dict:
    fingerprints = json.loads(FINGERPRINT_PATH.read_text(encoding="utf-8"))
    corpus_fingerprint = fingerprints["corpus_fingerprint"]
    collection = args.collection or f"kb_eval_phase55_{corpus_fingerprint[:12]}"
    qdrant = QdrantClient(url=args.qdrant_url)
    if qdrant.collection_exists(collection):
        if not args.recreate:
            raise RuntimeError(f"refusing to reuse existing evaluation collection: {collection}")
        qdrant.delete_collection(collection)

    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    embedding = active_embedding_config(settings)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()
    grouped = _manifest_by_tenant()

    try:
        with tempfile.TemporaryDirectory(prefix="phase55-corpus-") as staging_root:
            staging = Path(staging_root)
            registry = DocumentRegistry(staging / "registry.db")
            store = QdrantStore(qdrant, collection, dense_dimension=embedding.dimension)

            async def embed_fn(text: str) -> list[float]:
                return await ollama.embed(
                    text,
                    model=embedding.ollama_model,
                    prefix=embedding.document_prefix(),
                    dimensions=embedding.output_dimension,
                )

            pipeline_fingerprint = build_pipeline_fingerprint(
                embedding, settings.chunking_config()
            )
            totals = {"files_processed": 0, "chunks_upserted": 0}
            for tenant_id, documents in sorted(grouped.items()):
                tenant_dir = staging / tenant_id
                tenant_dir.mkdir()
                for document in documents:
                    source = CORPUS_DIR / document["path"]
                    target = tenant_dir / document["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(source, target)
                stats = await ingest_connector(
                    ManifestFilesystemConnector(tenant_dir, documents),
                    store,
                    registry,
                    embed_fn,
                    sparse,
                    embedding_concurrency=settings.embedding_concurrency,
                    pipeline_fingerprint=pipeline_fingerprint,
                    tenant_id=tenant_id,
                    chunking_config=settings.chunking_config(),
                )
                totals["files_processed"] += stats.files_processed
                totals["chunks_upserted"] += stats.chunks_upserted
            registry.close()

        validation = validate_evaluation_index(
            qdrant,
            collection,
            MANIFEST_PATH,
            None,
            corpus_fingerprint,
            expected_dimension=embedding.dimension,
        )
        validation.update(
            {
                "dataset_fingerprint": fingerprints["dataset_fingerprint"],
                "embedding_model": embedding.ollama_model,
                "embedding_dimension": embedding.dimension,
                "chunking_mode": settings.chunking_mode,
                "ingest_totals": totals,
            }
        )
        DEFAULT_VALIDATION.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_VALIDATION.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return validation
    finally:
        await ollama.aclose()
        qdrant.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--collection")
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
