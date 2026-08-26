from sentence_transformers import CrossEncoder

from app.reranker.config import EXISTING_RERANKER_MODEL, RERANKER_BACKEND
from app.retrieval.hybrid_search import SearchResult

# Benchmarked on M2 CPU with real chunk-sized text: ~9s one-time model load
# (cached), ~2.8-9ms/pair to score. Reranking a top-20 batch costs ~60-180ms
# per query — acceptable (an LLM generation call afterwards already takes
# seconds).
MODEL_NAME = EXISTING_RERANKER_MODEL


class CrossEncoderReranker:
    backend = RERANKER_BACKEND

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        trust_remote_code: bool = False,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.trust_remote_code = trust_remote_code
        kwargs = {"trust_remote_code": True} if trust_remote_code else {}
        if device is not None:
            kwargs["device"] = device
        self.device = device
        self._model = CrossEncoder(model_name, **kwargs)

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int) -> list[SearchResult]:
        if not candidates:
            return []

        pairs = [[query, candidate.payload["text"]] for candidate in candidates]
        scores = self._model.predict(pairs)

        reranked = sorted(zip(candidates, scores), key=lambda pair: -pair[1])
        return [
            SearchResult(score=float(score), payload=candidate.payload)
            for candidate, score in reranked[:top_n]
        ]
