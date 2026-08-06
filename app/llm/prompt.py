from pathlib import Path

from app.retrieval.hybrid_search import SearchResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
NOT_FOUND_PHRASE = "I could not find this in the document."


def load_system_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"answer_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt template for version {version!r}: {path}")
    return path.read_text().format(not_found_phrase=NOT_FOUND_PHRASE)


def citation_tag(source_type: str, source_id: str, page: int, paragraph: int) -> str:
    return f"[s.{source_type}:{source_id}/{page}/{paragraph}]"


def build_context(chunks: list[SearchResult]) -> str:
    parts = []
    for chunk in chunks:
        payload = chunk.payload
        source_type = payload.get("source_type", "doc")
        source_id = payload.get("source_id", "doc")
        page = payload["page_number"]
        paragraph = payload["paragraph_index"]
        tag = citation_tag(source_type, source_id, page, paragraph)
        label = (
            f"[Kaynak: {source_type}:{source_id}, Sayfa {page}, Paragraf {paragraph} "
            f"— citation tag: {tag}]"
        )
        parts.append(f"{label}\n{payload['text']}")
    return "\n\n".join(parts)


def build_messages(question: str, chunks: list[SearchResult], version: str) -> list[dict]:
    system_prompt = load_system_prompt(version)
    context = build_context(chunks)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
