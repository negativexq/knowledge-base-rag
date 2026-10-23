"""Scope validation and quantity checking can run at their own reasoning effort,
and a raw-text forensic capture keeps each model call's exact input, so the same
call can be replayed at another effort and the verdicts compared."""

import base64
import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.llm.adaptive import ResearchDecision
from app.shared.config import Settings
from tests.test_adaptive import deps, reply, session


def test_scope_and_check_reasoning_can_differ_from_final_reasoning():
    from app.wiring import adaptive_role_settings

    roles = adaptive_role_settings(Settings(_env_file=None))
    assert roles["scope_validator"]["openai_reasoning_effort"] == "medium"
    assert roles["quantity_checker"]["openai_reasoning_effort"] == "medium"

    roles = adaptive_role_settings(
        Settings(_env_file=None, adaptive_scope_reasoning="low", adaptive_check_reasoning="low")
    )
    assert roles["scope_validator"]["openai_reasoning_effort"] == "low"
    assert roles["quantity_checker"]["openai_reasoning_effort"] == "low"
    assert roles["scoped_extraction_checker"]["openai_reasoning_effort"] == "low"
    assert roles["finalizer"]["openai_reasoning_effort"] == "medium"
    assert roles["extraction_checker"]["openai_reasoning_effort"] == "low"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_text", [True, False])
async def test_a_raw_capture_keeps_the_exact_model_input(raw_text):
    def model(messages, info):
        return reply(info, {"action": "stop"})

    active = session(deps())
    active.model = FunctionModel(model)
    active.role_model_settings = {"reader": {"openai_reasoning_effort": "low"}}
    capture = ForensicCapture.create("question", raw_text=raw_text)
    token = set_current_capture(capture)
    try:
        await active.call(
            "reader",
            ResearchDecision,
            "Decide the next step.",
            {"question": "What does the service use?"},
            research=True,
            images=[b"\x89PNG-fake"],
        )
    finally:
        reset_current_capture(token)
    stage = capture.record["stages"]["adaptive_model_1_reader"]
    if not raw_text:
        assert "raw_model_input" not in stage
        return
    recorded = stage["raw_model_input"]
    assert recorded["instructions"] == "Decide the next step."
    assert json.loads(recorded["prompt_text"]) == {"question": "What does the service use?"}
    assert recorded["output_schema"] == ResearchDecision.model_json_schema()
    assert recorded["model_settings"]["openai_reasoning_effort"] == "low"
    assert [base64.b64decode(i) for i in recorded["images_png_base64"]] == [b"\x89PNG-fake"]


def test_replay_compares_only_the_fields_the_application_acts_on():
    from scripts.experiments.replay_model_calls import output_object, passes, verdict

    raw = json.dumps(
        [
            json.dumps(
                {
                    "checks": [{"claim_index": 0, "verdict": "supported", "reason": "NONE"}],
                    "requirement_bindings": [{"requirement_index": 0, "verdict": "mismatch"}],
                    "objections": [],
                    "material_omissions": [],
                    "source_disposition": None,
                }
            )
        ]
    )
    scope = verdict("scope_validator", output_object(raw))
    assert scope == {
        "checks": ["supported"],
        "requirements": ["mismatch"],
        "objections": 0,
        "omissions": 0,
        "disposition": None,
    }
    assert passes("scope_validator", scope) is False
    check = verdict(
        "quantity_checker",
        {
            "inputs": "supported",
            "coverage": "complete",
            "operation": "supported",
            "issues": [],
            "alternatives": [],
            "source_disposition": {"proposal": {"kind": "not_reported_in_scope"}},
        },
    )
    assert check["disposition"] == "not_reported_in_scope"
    assert passes("quantity_checker", check) is True
    assert output_object("not json") is None and verdict("scope_validator", None) is None
