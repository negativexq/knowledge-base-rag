from dataclasses import dataclass

from fastembed import SparseTextEmbedding

# Qdrant/bm25 is a pure statistical (term-frequency) sparse representation,
# not a neural model — chosen after benchmarking on an M2 that a neural
# sparse model (SPLADE) cost ~134ms/chunk on CPU vs BM25's ~0.1ms/chunk.
# `requires_idf=True` on this model means Qdrant computes IDF server-side
# from its own indexed corpus (set via SparseVectorParams(modifier=IDF)) —
# no client-side corpus fitting needed.
MODEL_NAME = "Qdrant/bm25"


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class SparseEncoder:
    def __init__(self) -> None:
        self._model = SparseTextEmbedding(model_name=MODEL_NAME)

    def embed_document(self, text: str) -> SparseVector:
        embedding = next(self._model.embed([text]))
        return SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())

    def embed_query(self, text: str) -> SparseVector:
        embedding = next(self._model.query_embed([text]))
        return SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())
