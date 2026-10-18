"""Research tools exercise real authorization, evidence admission and the agent loop."""

import uuid

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.evidence.documents import DocumentRead, DocumentReader, DocumentRef
from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.retrieval.research import ResearchRetriever
from app.security.models import RetrievalContext


@pytest.fixture
def research_reader():
    client = QdrantClient(":memory:")
    client.create_collection("docs", vectors_config=qm.VectorParams(size=1, distance="Cosine"))
    points = []
    for tenant, source, version, text in [
        ("a", "manual", "v1", "TLS requires an explicit setting."),
        ("a", "manual", "v1", "SSH uses port 22."),
        ("a", "manual", "v2", "SSH uses port 2222."),
        ("a", "other", "v1", "Other instructions."),
        ("b", "secret", "v1", "Secret instructions."),
    ]:
        points.append(
            qm.PointStruct(
                id=str(uuid.uuid4()),
                vector=[1.0],
                payload={
                    "tenant_id": tenant,
                    "source_type": "filesystem",
                    "source_id": source,
                    "document_version": version,
                    "text": text,
                    "page_number": 1,
                    "heading_path": ["Configuration"],
                },
            )
        )
    client.upsert("docs", points)
    yield DocumentReader(client, "docs", RetrievalContext("a"))
    client.close()


async def ledger_for(reader):
    result = await reader.read(
        DocumentRead(
            document=DocumentRef(
                source_type="filesystem", source_id="manual", document_version="v1"
            ),
            action="page",
        )
    )
    initial = next(b for b in result.blocks if "TLS" in b.payload["text"])
    ledger = EvidenceLedger(lambda t: len(t.split()), 1000, reader.context, reader.source_ids)
    ledger.add([initial])
    return ledger


def refuse(info):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"abstain": True})])


def returned(messages):
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


@pytest.mark.asyncio
async def test_literal_search_keeps_document_version_and_support_ids(research_reader):
    ledger = await ledger_for(research_reader)

    def model(messages, info):
        if not returned(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "search",
                        {
                            "query": "SSH uses",
                            "mode": "phrase",
                            "support_id": "E1.S1",
                        },
                    )
                ]
            )
        content = returned(messages)[0].content
        assert "E2.S1" in content and "port 22." in content
        assert "2222" not in content and "Secret" not in content
        return refuse(info)

    result = await run_agent(
        FunctionModel(model), AgentDependencies("SSH?", ledger, documents=research_reader)
    )
    assert result.failure_code is None
    assert result.telemetry["tools"][0]["added_blocks"] == 1


@pytest.mark.asyncio
async def test_discovery_respects_caller_source_scope(research_reader):
    research_reader.source_ids = frozenset({"manual"})
    result = await research_reader.discover("Configuration")
    assert {b.payload["source_id"] for b in result.blocks} == {"manual"}
    assert {b.payload["document_version"] for b in result.blocks} == {"v1", "v2"}
    assert (await research_reader.discover("secret")).blocks == []
    result = await research_reader.discover("manual", version="v2")
    assert len(result.blocks) == 1


@pytest.mark.asyncio
async def test_discovery_returns_usable_new_anchor(research_reader):
    ledger = await ledger_for(research_reader)

    def model(messages, info):
        if not returned(messages):
            return ModelResponse(parts=[ToolCallPart("find_documents", {"query": "other"})])
        result = returned(messages)[0].content
        assert result["documents"][0]["source_id"] == "other"
        assert result["documents"][0]["support_id"] == "E2.S1"
        assert "Other instructions" in result["evidence"]
        return refuse(info)

    result = await run_agent(
        FunctionModel(model), AgentDependencies("Find other", ledger, documents=research_reader)
    )
    assert result.failure_code is None


@pytest.mark.asyncio
async def test_hybrid_excludes_seen_points_before_retrieval(research_reader):
    ledger = await ledger_for(research_reader)
    observed = []

    async def retrieve(query, filters=None):
        observed.append(filters)
        return []

    def model(messages, info):
        if not returned(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "search",
                        {
                            "query": "SSH",
                            "support_id": "E1.S1",
                        },
                    )
                ]
            )
        return refuse(info)

    result = await run_agent(
        FunctionModel(model),
        AgentDependencies(
            "SSH?", ledger, retrieve=ResearchRetriever(retrieve), documents=research_reader
        ),
    )
    assert result.failure_code is None
    filters = observed[0]
    assert filters.must_not[0].has_id == [ledger.blocks[0].id]
    assert {c.key: c.match.value for c in filters.must} == {
        "source_id": "manual",
        "source_type": "filesystem",
        "document_version": "v1",
    }


def test_admission_reports_duplicate_and_budget_exclusion_separately():
    from app.retrieval.hybrid_search import SearchResult

    first = SearchResult(id="a", score=1, payload={"text": "small"})
    large = SearchResult(id="b", score=1, payload={"text": "large " * 100})
    ledger = EvidenceLedger(lambda t: len(t.split()), 50)
    ledger.add([first])
    ledger.add([first, large])
    assert ledger.last_admission == {
        "duplicate_blocks": 1,
        "empty_blocks": 0,
        "budget_excluded_blocks": 1,
    }
    assert ledger.remaining_tokens == 9
    assert ledger.add([first], allowance=0) == []
