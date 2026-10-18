"""A chat request can name the sources to answer from ("ask this document").
The scope only narrows retrieval: it is a user filter AND-ed with the
server-owned tenant ACL inside the Qdrant query, never a widening and never
part of RetrievalContext. MMLongBench is single-document QA, so its runner
scopes each question to its PDF (v2 audit: all six Hit@14 misses were chunks
from other PDFs)."""

import pytest
from pydantic import ValidationError

from app.api.chat import MAX_SCOPE_SOURCES, ChatDependencies, ChatRequest, _sse_event_stream
from app.retrieval.filters import RetrievalContext
from app.retrieval.hybrid_search import SearchResult


def _recording_search(received: dict):
    async def search_fn(question, context, report, **kwargs):
        received["kwargs"] = kwargs
        received["context"] = context
        return [SearchResult(score=1.0, payload={"text": "x", "tenant_id": context.tenant_id})]

    return search_fn


async def _ok_stream(question, chunks):
    yield {"type": "token", "content": "ok"}


async def _drain(deps, **kwargs):
    context = RetrievalContext(tenant_id="tenant-a")
    return [line async for line in _sse_event_stream("What is X?", deps, context, **kwargs)]


@pytest.mark.asyncio
async def test_a_scoped_request_passes_its_sources_to_search():
    received = {}
    deps = ChatDependencies(search_fn=_recording_search(received), stream_fn=_ok_stream)

    await _drain(deps, source_ids=["handbook.pdf"])

    assert received["kwargs"] == {"source_ids": ["handbook.pdf"]}
    assert received["context"].tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_an_unscoped_request_searches_as_before():
    received = {}
    deps = ChatDependencies(search_fn=_recording_search(received), stream_fn=_ok_stream)

    await _drain(deps)

    assert received["kwargs"] == {}


def test_the_scope_is_bounded_and_names_real_sources():
    assert ChatRequest(question="q", source_ids=["a.pdf"]).source_ids == ["a.pdf"]
    assert ChatRequest(question="q").source_ids is None
    with pytest.raises(ValidationError):
        ChatRequest(question="q", source_ids=[f"s{i}" for i in range(MAX_SCOPE_SOURCES + 1)])
    with pytest.raises(ValidationError):
        ChatRequest(question="q", source_ids=[""])


@pytest.mark.asyncio
async def test_the_production_search_fn_filters_on_the_scope(monkeypatch):
    import app.wiring as wiring
    from app.shared.config import Settings

    captured = {}

    async def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(wiring, "search", fake_search)
    deps, provider = wiring.build_chat_dependencies(
        Settings(_env_file=None, reranker_enabled=False), object(), object(), object(), "c"
    )
    from app.retrieval.report import RetrievalReport

    await deps.search_fn("q", RetrievalContext(tenant_id="t"), RetrievalReport())
    assert captured["source_ids"] is None
    await deps.search_fn(
        "q", RetrievalContext(tenant_id="t"), RetrievalReport(), source_ids=["a.pdf"]
    )
    assert captured["source_ids"] == ["a.pdf"]
    await provider.aclose()


def test_the_benchmark_scopes_each_question_to_its_pdf():
    from scripts.benchmarks import run_mmlongbench_pilot as runner

    assert runner.retrieval_scope("BESTBUY_2023_10K.pdf", open_corpus=False) == [
        runner.source_id_for("BESTBUY_2023_10K.pdf")
    ]
    assert runner.retrieval_scope("BESTBUY_2023_10K.pdf", open_corpus=True) is None


@pytest.mark.asyncio
async def test_the_operand_resolver_searches_within_the_request_scope():
    received = {}
    searches = []

    async def stream_fn(question, chunks, retrieve=None):
        searches.append(retrieve)
        if retrieve is not None:
            await retrieve("Costco total liabilities 2021")
        yield {"type": "token", "content": "ok"}

    deps = ChatDependencies(
        search_fn=_recording_search(received), stream_fn=stream_fn, operand_resolver_enabled=True
    )
    await _drain(deps, source_ids=["costco.pdf"])

    assert searches[0] is not None
    assert received["kwargs"] == {"source_ids": ["costco.pdf"]}
    assert received["context"].tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_without_the_resolver_the_stream_gets_no_search():
    seen = []

    async def stream_fn(question, chunks, **kwargs):
        seen.append(kwargs)
        yield {"type": "token", "content": "ok"}

    deps = ChatDependencies(search_fn=_recording_search({}), stream_fn=stream_fn)
    await _drain(deps)

    assert seen == [{}]
