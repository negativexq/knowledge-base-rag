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


async def nothing_found(query):
    return []


async def test_last_research_turn_hides_tools_and_keeps_scope_verification_slot():
    calls = 0

    def main(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            assert any(t.name == "search" for t in info.function_tools)
            return ModelResponse(parts=[ToolCallPart("search", {"query": "protocol"})])
        assert info.function_tools == []
        return output(info, json.loads(raw("The service uses TLS.")))

    def verifier(messages, info):
        return output(info, judgment())

    candidate = await run_agent(
        FunctionModel(main),
        AgentDependencies(
            "Protocol?", ledger(), retrieve=nothing_found, scope_validation_enabled=True
        ),
        max_requests=3,
        scope_model=FunctionModel(verifier),
    )
    assert candidate.failure_code is None
    assert candidate.telemetry["requests"] == 3
    assert candidate.scope_receipt is not None and not candidate.scope_receipt.failure_codes
    assert candidate.telemetry["budget"]["scope_request_reserve"] == 1


async def test_token_preflight_blocks_call_before_sending_an_oversized_history():
    seen = 0

    def main(messages, info):
        nonlocal seen
        seen += 1
        raise AssertionError("Oversized request must be blocked before provider call")

    evidence = EvidenceLedger(lambda text: len(text), 10000)
    evidence.add([block("A" * 500)])
    candidate = await run_agent(
        FunctionModel(main), AgentDependencies("Protocol?", evidence), max_tokens=100
    )
    assert candidate.failure_code == "AGENT_BUDGET_EXCEEDED"
    assert seen == 0
    assert candidate.telemetry["budget"]["preflight_events"][0]["reason"] == "token_preflight"


def line_judgment(**reference):
    from app.llm.scope_validation import LineScopeJudgment

    return LineScopeJudgment.model_validate(
        {
            "checks": [
                {
                    "claim_index": 0,
                    "verdict": "supported",
                    "reason": "NONE",
                    "witnesses": [
                        {"support_id": "E1.S1", "start_line": 1, "end_line": 1, **reference}
                    ],
                }
            ]
        }
    )


def test_line_references_resolve_original_whitespace_and_bind_original_receipt():
    from app.llm.scope_validation import line_scope_payload, resolve_line_judgment

    units = [replace(ledger().units[0], text="Header\r\n  The service uses TLS.\r\nFooter")]
    original = scope_payload("Protocol?", raw("The service uses TLS."), units)
    before = json.dumps(original)
    projected = line_scope_payload(original)
    assert json.dumps(original) == before
    evidence = projected["claims"][0]["cited_evidence"][0]
    assert evidence["support_id"] == "E1.S1" and "evidence_id" not in evidence
    assert evidence["text"][1] == {"line": 2, "content": "  The service uses TLS.\r\n"}
    checked = resolve_line_judgment(original, line_judgment(start_line=2, end_line=2))
    assert checked.checks[0].witnesses[0].quote == "  The service uses TLS.\r\n"
    receipt = validate_judgment(original, checked)
    assert receipt.accepts("Protocol?", raw("The service uses TLS."), units)
    assert not receipt.accepts("Other question", raw("The service uses TLS."), units)


@pytest.mark.parametrize(
    "reference",
    [
        {"support_id": "E99.S1"},
        {"end_line": 999},
        {"start_line": 2, "end_line": 1},
    ],
)
def test_invalid_line_references_fail_closed(reference):
    from app.llm.scope_validation import resolve_line_judgment

    with pytest.raises(ValueError, match="SCOPE_CHECK_INVALID"):
        resolve_line_judgment(
            scope_payload("Protocol?", raw(), ledger().units), line_judgment(**reference)
        )


@pytest.mark.parametrize("case", [
    "verified", "ordinary", "only_invalid", "unknown_source", "mismatch"
])
def test_redundant_bad_locator_requires_independent_authority_and_retained_valid_witness(case):
    from app.llm.scope_validation import LineScopeJudgment, resolve_line_judgment

    data = line_judgment().model_dump()
    data["checks"][0]["witnesses"].append(dict(
        support_id="E99.S1" if case == "unknown_source" else "E1.S1",
        start_line=99, end_line=99,
    ))
    if case == "only_invalid":
        data["checks"][0]["witnesses"] = data["checks"][0]["witnesses"][1:]
    if case == "mismatch":
        data["checks"][0].update(verdict="mismatch", reason="PERIOD_MISMATCH")
    proposed = LineScopeJudgment.model_validate(data)
    original = scope_payload("Protocol?", raw(), ledger().units)
    diagnostics = {}
    if case == "verified":
        checked = resolve_line_judgment(
            original, proposed, independently_verified_claims={0}, diagnostics=diagnostics
        )
        assert not validate_judgment(original, checked).failure_codes
        assert len(checked.checks[0].witnesses) == 1
        assert diagnostics == {"ignored_verified_claim_ocr_locators": 1}
    else:
        with pytest.raises(ValueError, match="SCOPE_CHECK_INVALID"):
            resolve_line_judgment(
                original, proposed,
                independently_verified_claims=set() if case == "ordinary" else {0},
                diagnostics=diagnostics,
            )


@pytest.mark.parametrize("text", [" \n"])
def test_empty_or_oversized_line_witnesses_fail_closed(text):
    from app.llm.scope_validation import resolve_line_judgment

    units = [replace(ledger().units[0], text=text)]
    with pytest.raises(ValueError, match="SCOPE_CHECK_INVALID"):
        resolve_line_judgment(
            scope_payload("Protocol?", raw(), units),
            line_judgment(end_line=3 if len(text) > 1600 else 1),
        )


def test_long_source_row_can_be_cited_without_loosening_witness_limits_or_rewriting_text():
    from app.llm.scope_validation import line_scope_payload, resolve_line_judgment

    text = "source metadata " * 150 + "The service uses TLS. " + "remaining cells " * 100
    units = [replace(ledger().units[0], text=text)]
    original = scope_payload("Protocol?", raw("The service uses TLS."), units)
    projected = line_scope_payload(original)
    rows = projected["claims"][0]["cited_evidence"][0]["text"]
    assert "".join(r["content"] for r in rows) == text
    selected = next(r["line"] for r in rows if "The service uses TLS." in r["content"])
    checked = resolve_line_judgment(original, line_judgment(start_line=selected, end_line=selected))
    quote = checked.checks[0].witnesses[0].quote
    assert quote in text and len(quote) <= 1600
    assert validate_judgment(original, checked).accepts(
        "Protocol?", raw("The service uses TLS."), units
    )
    resolved = resolve_line_judgment(original, line_judgment(start_line=1, end_line=len(rows)))
    witnesses = resolved.checks[0].witnesses
    assert all(len(w.quote) <= 1600 and w.quote in text for w in witnesses)
    assert "".join(w.quote for w in witnesses) == text


def test_locally_split_source_ranges_still_enforce_witness_count_limit():
    from app.llm.scope_validation import line_scope_payload, resolve_line_judgment

    original = scope_payload("Protocol?", raw(), [replace(ledger().units[0], text="x" * 40000)])
    count = len(line_scope_payload(original)["claims"][0]["cited_evidence"][0]["text"])
    with pytest.raises(ValueError, match="SCOPE_CHECK_INVALID"):
        resolve_line_judgment(original, line_judgment(start_line=1, end_line=count))
