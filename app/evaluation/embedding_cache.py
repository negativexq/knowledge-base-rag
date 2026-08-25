import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class StaleCacheError(Exception):
    """Raised when a cached embedding's stored fingerprint doesn't match
    the CURRENT pipeline fingerprint — Sprint 21's explicit rule: a stale
    cache must never be silently reused (a frozen-mode benchmark run
    against embeddings computed under a different model/dimension/
    instruction would be measuring nothing real). Callers must either
    recompute (live) or fail loudly, never fall through quietly.
    """


def cache_key(
    model: str, revision: str, dimension: int, instruction: str, query: str, fingerprint: str
) -> str:
    """The cache key genuinely covers everything that determines the
    embedding output: model, revision, dimension, the exact instruction/
    prefix used, the query text itself, AND the pipeline fingerprint
    digest (which already folds in model/revision/dimension/instruction/
    index-schema-version — included redundantly here so a cache built
    under one fingerprint can never collide with one built under a
    different index-schema-version even if model/dimension happen to
    match).
    """
    raw = json.dumps(
        {
            "model": model,
            "revision": revision,
            "dimension": dimension,
            "instruction": instruction,
            "query": query,
            "fingerprint": fingerprint,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    key: str
    vector: list[float]
    fingerprint: str


class EmbeddingCache:
    """A frozen-mode embedding store — Sprint 21's separation of "quality
    measurement" from "serving variability." Populated once (live calls),
    then reused across many retrieval-determinism-check passes with ZERO
    further embedding calls, so those passes measure ONLY Qdrant/RRF
    behavior, not embedding-model nondeterminism.
    """

    def __init__(self, path: Path):
        self._path = path
        self._entries: dict[str, CacheEntry] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._entries = {
                k: CacheEntry(key=k, vector=v["vector"], fingerprint=v["fingerprint"])
                for k, v in raw.items()
            }

    def get(self, key: str, expected_fingerprint: str) -> list[float] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.fingerprint != expected_fingerprint:
            raise StaleCacheError(
                f"Cached embedding for key {key!r} was computed under fingerprint "
                f"{entry.fingerprint!r}, but the current pipeline fingerprint is "
                f"{expected_fingerprint!r} — refusing to silently reuse a stale "
                "embedding. Repopulate the cache (live mode) before running frozen mode."
            )
        return entry.vector

    def put(self, key: str, vector: list[float], fingerprint: str) -> None:
        self._entries[key] = CacheEntry(key=key, vector=vector, fingerprint=fingerprint)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            k: {"vector": e.vector, "fingerprint": e.fingerprint}
            for k, e in self._entries.items()
        }
        self._path.write_text(json.dumps(raw), encoding="utf-8")
