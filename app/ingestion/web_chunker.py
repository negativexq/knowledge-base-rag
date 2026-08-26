import hashlib

from app.ingestion.chunker import DEFAULT_CHUNK_SIZE_TOKENS, DEFAULT_OVERLAP_TOKENS
from app.ingestion.chunking_config import ChunkingConfig
from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.models import Chunk
from app.parsing.web_parser import extract_main_content


def compute_html_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def chunk_web_page(
    html: str,
    source_id: str,
    source_type: str = "web",
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    doc_id: str | None = None,
    chunking_config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """Extracts a web page's main content and chunks it with the same
    heading-path location scheme as markdown (see app/parsing/web_parser.py
    for why). Returns [] if trafilatura finds no real content to extract —
    e.g. a page that's entirely navigation/ads (no article to cite from).
    """
    content = extract_main_content(html)
    if not content:
        return []
    doc_id = doc_id or compute_html_hash(html)
    return chunk_markdown_text(
        content,
        source_id,
        source_type,
        doc_id,
        chunk_size_tokens,
        overlap_tokens,
        chunking_config,
    )
