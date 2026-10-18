import json
from dataclasses import replace

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.llm.agentic import AgentCandidate, AgentDependencies, EvidenceLedger, run_agent
from app.llm.scope_validation import ScopeJudgment, scope_payload, validate_judgment
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult


def block(text="The service uses TLS.", id="c1"):
    return SearchResult(
        id=id, score=1, payload={"text": text, "source_id": "manual", "tenant_id": "a"}
    )


def raw(text="The backup service uses TLS.", support="E1.S1"):
    return json.dumps(
        {"answer_parts": [{"text": text, "support_ids": [support]}], "abstain": False}
    )


def output(info, data):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


def judgment(verdict="supported", reason="NONE", quote="The service uses TLS.", support="E1.S1"):
    return {
        "checks": [
            {
                "claim_index": 0,
                "verdict": verdict,
                "reason": reason,
                "witnesses": [{"support_id": support, "quote": quote}]
                if verdict == "supported"
                else [],
            }
        ]
    }


def ledger(text="The service uses TLS."):
    result = EvidenceLedger(lambda _: 1, 1000)
    result.add([block(text)])
    return result


@pytest.mark.parametrize(
    "change", ["question", "claim", "evidence", "source", "version", "visibility"]
)
def test_scope_receipt_cannot_be_replayed_after_material_change(change):
    units = ledger().units
    receipt = validate_judgment(
        scope_payload("Protocol?", raw(), units), ScopeJudgment.model_validate(judgment())
    )
    question, answer = "Protocol?", raw()
    if change == "question":
        question = "Other protocol?"
    if change == "claim":
        answer = raw("The primary service uses TLS.")
    if change == "evidence":
        units = [replace(units[0], text="Different text")]
    if change == "source":
        units = [replace(units[0], source_id="other")]
    if change == "version":
        units = [replace(units[0], document_version="new")]
    if change == "visibility":
        units = [replace(units[0], authorized=False)]
    assert not receipt.accepts(question, answer, units)


@pytest.mark.parametrize(
    "data",
    [
        {"checks": [{"claim_index": 1, "verdict": "supported", "reason": "NONE", "witnesses": []}]},
        judgment(quote="fabricated witness"),
        judgment(support="E99.S1"),
        {"checks": [{"claim_index": 0, "verdict": "supported", "reason": "NONE", "witnesses": []}]},
    ],
)
def test_incomplete_or_fabricated_verifier_outputs_fail_closed(data):
    receipt = validate_judgment(
        scope_payload("Protocol?", raw(), ledger().units), ScopeJudgment.model_validate(data)
    )
    assert "SCOPE_CHECK_INVALID" in receipt.failure_codes


async def test_scope_rejection_drives_search_and_new_evidence_before_release():
    attempts = 0

    def main_model(messages, info):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return output(info, json.loads(raw()))
        if attempts == 2:
            assert any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts)
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup protocol"})])
        assert any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        return output(info, json.loads(raw("The backup service uses SSH.", "E2.S1")))

    def verifier(messages, info):
        data = json.loads(messages[-1].parts[0].content)
        text = data["claims"][0]["claim"]["text"]
        if "TLS" in text:
            return output(info, judgment("insufficient", "SCOPE_NOT_ESTABLISHED"))
        return output(info, judgment(quote="The backup service uses SSH.", support="E2.S1"))

    async def retrieve(_):
        return [block("The backup service uses SSH.", id="c2")]

    deps = AgentDependencies(
        "What protocol does the backup service use?",
        ledger(),
        retrieve=retrieve,
        scope_validation_enabled=True,
    )
    candidate = await run_agent(
        FunctionModel(main_model), deps, scope_model=FunctionModel(verifier)
    )
    assert candidate.failure_code is None
    assert candidate.telemetry["requests"] == 5  # includes both verifier calls
    assert candidate.scope_receipt and candidate.scope_receipt.accepts(
        deps.question, candidate.raw, deps.ledger.units
    )
    assert candidate.telemetry["scope_validation"]["rejections"] == 1

    async def generate(*_):
        return candidate

    events = [
        e
        async for e in stream_support_unit_answer(
            deps.question, [], None, model="fake", candidate_generator=generate
        )
    ]
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert "SSH" in answer and "TLS" not in answer


async def test_scope_verifier_consumes_shared_request_budget():
    def model(messages, info):
        return output(info, json.loads(raw()))

    def verifier(messages, info):
        raise AssertionError("No budget to issue verifier request")

    candidate = await run_agent(
        FunctionModel(model),
        AgentDependencies("Protocol?", ledger(), scope_validation_enabled=True),
        max_requests=1,
        scope_model=FunctionModel(verifier),
    )
    assert candidate.failure_code == "AGENT_BUDGET_EXCEEDED"


@pytest.mark.parametrize("mode", ["missing", "mutated"])
async def test_final_release_requires_matching_server_owned_scope_receipt(mode):
    units = ledger().units
    receipt = validate_judgment(
        scope_payload("Protocol?", raw(), units), ScopeJudgment.model_validate(judgment())
    )
    candidate = AgentCandidate(
        raw("The primary service uses TLS.") if mode == "mutated" else raw(),
        [block()],
        scope_validation_required=True,
        scope_receipt=receipt if mode == "mutated" else None,
    )

    async def generate(*_):
        return candidate

    events = [
        e
        async for e in stream_support_unit_answer(
            "Protocol?", [], None, model="fake", candidate_generator=generate
        )
    ]
    security = next(e for e in events if e["type"] == "security_validation")
    assert security["application_forced_abstention"]
    assert "SCOPE_RELEASE_UNVERIFIED" in security["validator_failure_codes"]
    assert "TLS" not in "".join(e["content"] for e in events if e["type"] == "token")


async def test_scope_verifier_timeout_does_not_release_candidate():
    import asyncio

    def main_model(messages, info):
        return output(info, json.loads(raw()))

    async def verifier(*args):
        await asyncio.sleep(10)

    candidate = await run_agent(
        FunctionModel(main_model),
        AgentDependencies(
            "Protocol?",
            ledger(),
            scope_validation_enabled=True,
        ),
        scope_model=FunctionModel(verifier),
        timeout_seconds=0.02,
    )
    assert candidate.failure_code == "AGENT_TIMEOUT"
    assert json.loads(candidate.raw)["abstain"]


def test_each_claim_must_have_its_own_witness_and_complete_judgment():
    units = ledger().units
    data = json.loads(raw())
    data["answer_parts"].append({"text": "The service uses TLS.", "support_ids": ["E1.S1"]})
    payload = scope_payload("Protocol?", json.dumps(data), units)
    assert (
        "SCOPE_CHECK_INVALID"
        in validate_judgment(payload, ScopeJudgment.model_validate(judgment())).failure_codes
    )
    all_checks = judgment()
    all_checks["checks"].append({**all_checks["checks"][0], "claim_index": 1})
    assert not validate_judgment(payload, ScopeJudgment.model_validate(all_checks)).failure_codes


async def test_oversized_scope_payload_is_rejected_before_model_request(monkeypatch):
    monkeypatch.setattr("app.llm.agentic.MAX_SCOPE_PAYLOAD_CHARS", 1)

    def main_model(messages, info):
        return output(info, json.loads(raw()))

    def verifier(*_):
        raise AssertionError("Oversized verification must not be submitted")

    candidate = await run_agent(
        FunctionModel(main_model),
        AgentDependencies(
            "Protocol?",
            ledger(),
            scope_validation_enabled=True,
        ),
        scope_model=FunctionModel(verifier),
        retries=0,
    )
    assert candidate.failure_code == "AGENT_RUN_FAILED"
    assert candidate.telemetry["requests"] == 1
