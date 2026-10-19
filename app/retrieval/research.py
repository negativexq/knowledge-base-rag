"""Request-owned advanced retrieval; a tool can only narrow the caller's scope."""

from collections.abc import Awaitable, Callable

from qdrant_client.http import models as qm

from app.retrieval.hybrid_search import SearchResult


class ResearchRetriever:
    def __init__(self, retrieve: Callable[..., Awaitable[list[SearchResult]]]):
        self.retrieve = retrieve

    async def __call__(self, query: str) -> list[SearchResult]:
        return await self.retrieve(query)

    async def search(self, query: str, filters: qm.Filter) -> list[SearchResult]:
        if not filters.must and not filters.must_not:
            return await self.retrieve(query)
        return await self.retrieve(query, filters=filters)
