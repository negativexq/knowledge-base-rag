import json

import pytest

from app.llm.openai_client import (
    OPENAI_JUDGE_MODEL,
    OPENAI_MODEL,
    OpenAIGeneratorClient,
    canonical_hash,
    responses_strict_schema,
    validate_responses_strict_schema_shape,
)


def cost_for_usage(usage: dict[str, int]) -> float:
    return (usage.get("input_tokens", 0) * 0.80 + usage.get("output_tokens", 0) * 0.60) / 1_000_000


class _Usage:
    def model_dump(self, mode="json"):
        return {
            "input_tokens": 10,
            "output_tokens": 4,
            "total_tokens": 14,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 0},
        }


class _Response:
    id = "resp_test"
    output_text = '{"answer_parts":[],"abstain":true}'
    usage = _Usage()

    def model_dump(self, mode="json"):
        return {"id": self.id, "output_text": self.output_text}


class _Responses:
    def __init__(self):
        self.body = None

    async def create(self, **body):
        self.body = body
        return _Response()


class _Models:
    async def list(self):
        return type("Page", (), {"data": [type("Model", (), {"id": OPENAI_MODEL})()]})()


class _SDK:
    def __init__(self):
        self.responses = _Responses()
        self.models = _Models()

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_openai_responses_request_is_structured_and_secret_free():
    sdk = _SDK()
    client = OpenAIGeneratorClient(api_key="test-key", sdk_client=sdk)
    result = await client.chat_json(
        [{"role": "system", "content": "system"}, {"role": "user", "content": "question"}],
        model=OPENAI_MODEL,
        schema={"type": "object"},
        reasoning="none",
        max_output_tokens=1024,
        temperature=0.0,
        seed=42,
    )
    assert json.loads(result)["abstain"] is True
    assert sdk.responses.body["model"] == OPENAI_MODEL
    assert sdk.responses.body["reasoning"] == {"effort": "none"}
    assert sdk.responses.body["max_output_tokens"] == 1024
    assert sdk.responses.body["temperature"] == 0.0
    assert "api_key" not in sdk.responses.body
    assert client.last_call_observation["seed_sent"] is False
    assert client.last_call_observation["usage"]["input_tokens"] == 10
    await client.aclose()


@pytest.mark.asyncio
async def test_model_listing_requires_exact_luna_model():
    client = OpenAIGeneratorClient(api_key="test-key", sdk_client=_SDK())
    assert await client.available_models() == [OPENAI_MODEL]
    await client.aclose()


@pytest.mark.asyncio
async def test_model_mismatch_is_rejected_before_request():
    client = OpenAIGeneratorClient(api_key="test-key", sdk_client=_SDK())
    with pytest.raises(ValueError, match="model mismatch"):
        await client.chat_json([], model="another-model", schema=None)
    await client.aclose()


@pytest.mark.asyncio
async def test_judge_model_is_allowed_without_changing_generator_default():
    sdk = _SDK()
    client = OpenAIGeneratorClient(api_key="test-key", sdk_client=sdk)
    await client.chat_json(
        [{"role": "user", "content": "judge"}],
        model=OPENAI_JUDGE_MODEL,
        schema={"type": "object"},
        reasoning="medium",
        max_output_tokens=512,
        temperature=None,
    )
    assert sdk.responses.body["model"] == OPENAI_JUDGE_MODEL
    assert sdk.responses.body["reasoning"] == {"effort": "medium"}
    assert "temperature" not in sdk.responses.body
    await client.aclose()


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_responses_schema_keeps_logical_optional_reason_code_nullable():
    source = {
        "type": "object",
        "properties": {
            "answer_parts": {"type": "array"},
            "abstain": {"type": "boolean"},
            "reason_code": {"type": "string", "enum": ["INSUFFICIENT_EVIDENCE"]},
        },
        "required": ["answer_parts", "abstain"],
    }
    adapted = responses_strict_schema(source)
    assert adapted["required"] == ["answer_parts", "abstain", "reason_code"]
    assert adapted["properties"]["reason_code"]["anyOf"][1] == {"type": "null"}
    assert source["required"] == ["answer_parts", "abstain"]


def test_strict_schema_shape_rejects_object_without_additional_properties_false():
    with pytest.raises(ValueError, match="additionalProperties=false"):
        validate_responses_strict_schema_shape(
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            }
        )


def test_strict_schema_shape_rejects_untyped_property():
    with pytest.raises(ValueError, match="type or union"):
        validate_responses_strict_schema_shape(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"values": {"minItems": 1}},
                "required": ["values"],
            }
        )


def test_strict_schema_shape_rejects_root_union_before_provider_call():
    with pytest.raises(ValueError, match="cannot use a union at the root"):
        validate_responses_strict_schema_shape(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
                "required": [],
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {},
                        "required": [],
                    }
                ],
            }
        )


def test_cost_calculation_uses_supplied_input_output_rates():
    assert cost_for_usage({"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 1.4


def test_provider_config_contract_does_not_contain_api_key_field():
    from pathlib import Path

    config = Path(".env.example")
    if config.exists():
        payload = config.read_text(encoding="utf-8")
        assert ("OPENAI_" + "API_KEY=") not in payload
        assert "authorization" not in payload.lower()
