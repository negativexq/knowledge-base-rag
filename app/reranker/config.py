"""Single-source reranker configuration.

The benchmark names are intentionally stable so a result can be reproduced
without copying model strings into wiring, UI aggregation, and scripts.
"""

from dataclasses import dataclass

EXISTING_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MULTILINGUAL_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
RERANKER_CANDIDATE_K = 20
RERANKER_TOP_N = 5
RERANKER_BACKEND = "sentence-transformers"


@dataclass(frozen=True)
class RerankerConfig:
    enabled: bool
    model: str
    backend: str
    candidate_k: int = RERANKER_CANDIDATE_K
    top_n: int = RERANKER_TOP_N
    trust_remote_code: bool = False


def benchmark_config(name: str) -> RerankerConfig:
    """Return one of Sprint 26's pre-registered benchmark cells."""
    if name == "off":
        return RerankerConfig(False, "not enabled", RERANKER_BACKEND)
    if name == "existing":
        return RerankerConfig(True, EXISTING_RERANKER_MODEL, RERANKER_BACKEND)
    if name == "multilingual":
        return RerankerConfig(
            True,
            MULTILINGUAL_RERANKER_MODEL,
            RERANKER_BACKEND,
        )
    raise ValueError(f"unknown reranker benchmark config: {name!r}")
