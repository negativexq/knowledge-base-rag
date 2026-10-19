"""Prepared evidence reduces model calls without bypassing scope or research."""

import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.agentic import EvidenceLedger
from tests.test_adaptive import answer, block, deps, payload, reply, session


def draft(text="The service uses TLS.", support="E1.S1"):
    return {"answer_parts": [{"text": text, "support_ids": [support]}]}


def line_scope(messages, info, support, quote="The service uses TLS."):
    claim = payload(messages)["claims"][0]
    unit = next(u for u in claim["cited_evidence"] if u["support_id"] == support)
    line = next(r["line"] for r in unit["text"] if quote in r["content"])
    return reply(
        info,
        {
            "checks": [
                {
                    "claim_index": 0,
                    "verdict": "supported",
                    "reason": "NONE",
                    "witnesses": [{"support_id": support, "start_line": line, "end_line": line}],
                }
            ]
        },
    )


def expanded():
    chunks = [
        {"chunk_id": "cover", "section_key": "cover", "text": "Unrelated cover metadata."},
        {"chunk_id": "protocol", "section_key": "protocol", "text": "The service uses TLS."},
        {"chunk_id": "backup", "section_key": "backup", "text": "The backup uses SSH."},
        {"chunk_id": "values", "section_key": "values", "text": "Party A\n\n21%\n\nParty B\n\n21%"},
    ]
    dependencies = deps(scope_validation_enabled=True)
    dependencies.ledger = EvidenceLedger(lambda t: len(t.split()), 15000)
    dependencies.ledger.add(
        [
            block(
                "\n\n".join(c["text"] for c in chunks),
                section_chunks=chunks,
                anchor_chunk_ids=["protocol", "backup", "values"],
            )
        ]
    )
    return dependencies


@pytest.mark.asyncio
async def test_prepared_context_answers_in_two_calls_and_does_not_repeat_catalog():
    roles = []
    dependencies = expanded()

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "checks" in props:
            roles.append("scope")
            return line_scope(messages, info, support="E2.S1")
        roles.append("answerer")
        assert "action" not in props and "missing" in props
        data = payload(messages)
        assert "catalog" not in data and "tool_contracts" not in data
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["support_id"] == "E2.S1"
        assert "evidence_id" not in data["evidence"][0]
        assert "support_unit_id" not in data["evidence"][0]
        text = data["evidence"][0]["text"]
        assert "The service uses TLS." in text
        assert "Unrelated cover" not in text
        assert text.count("21%") == 2
        return reply(info, {"answer": draft(support="E2.S1")})

    result = await run_adaptive_agent(FunctionModel(model), dependencies, fast_path=True)
    assert result.failure_code is None
    assert roles == ["answerer", "scope"]
    assert result.telemetry["requests"] == 2 and result.telemetry["tool_calls"] == 0
    assert result.scope_receipt.accepts(
        dependencies.question, result.raw, dependencies.ledger.units
    )


@pytest.mark.asyncio
async def test_missing_evidence_opens_existing_research_without_forcing_abstention():
    searches = []

    async def retrieve(query):
        searches.append(query)
        return [block("The backup uses SSH.", "new")]

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "missing" in props:
            return reply(info, {"answer": None, "missing": ["The backup protocol is missing."]})
        if "action" in props:
            if not searches:
                return reply(info, {"action": "search", "query": "backup protocol"})
            return reply(
                info, {"action": "answer", "answer": answer("The backup uses SSH.", "E2.S1")}
            )
        return line_scope(messages, info, support="E2.S1", quote="The backup uses SSH.")

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(
            question="What does the backup use?",
            retrieve=retrieve,
            scope_validation_enabled=True,
        ),
        fast_path=True,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"]
    assert searches == ["backup protocol"]
    assert result.telemetry["requests"] == 4 and result.telemetry["tool_calls"] == 1


@pytest.mark.asyncio
async def test_fast_answer_cannot_bypass_scope_rejection():
    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "missing" in props:
            return reply(info, {"answer": draft("The service uses SSH.")})
        if "checks" in props:
            return reply(
                info,
                {
                    "checks": [
                        {
                            "claim_index": 0,
                            "verdict": "insufficient",
                            "reason": "SCOPE_NOT_ESTABLISHED",
                            "witnesses": [],
                        }
                    ]
                },
            )
        return reply(info, {"abstain": True})

    result = await run_adaptive_agent(
        FunctionModel(model), deps(scope_validation_enabled=True), fast_path=True, max_tool_calls=0
    )
    assert result.failure_code is None
    assert json.loads(result.raw)["abstain"]
    assert result.scope_receipt is None
    assert result.telemetry["requests"] == 3


def test_prepared_context_and_coverage_never_bypass_evidence_budget():
    active = session(expanded())
    active.compact_context = True
    active.deps.ledger._budget = active.deps.ledger._used
    active.prepare_initial_context()
    assert len(active.deps.ledger.blocks) == 1
    assert not active.state.read_coverage
    assert all(
        e["support_id"].startswith("E1.") for e in active.context(finalizing=True)["evidence"]
    )


def test_read_coverage_is_application_owned_and_retained_for_research_fallback():
    active = session(expanded())
    active.compact_context = True
    active.prepare_initial_context()
    coverage = next(iter(active.state.read_coverage.values()))
    assert coverage.source_id == "manual" and coverage.document_version == "v1"
    assert coverage.chunk_ids == ["protocol", "backup", "values"]
    assert coverage.support_ids == ["E2.S1"]
    research = active.context()
    assert research["read_coverage"][0]["support_ids"] == ["E2.S1"]
    # Already-opened chunks are not duplicated by small text units in the packet.
    assert len(research["evidence"]) == 2  # prepared packet + unrelated cover
