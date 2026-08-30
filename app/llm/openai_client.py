"""OpenAI Responses API adapter for generator-only evaluation.

The adapter deliberately exposes the same small ``chat_json`` surface used by
the V2.2 structured-output runner.  It owns transport details, timeout/error
classification, usage extraction, and request observability; retrieval and
validation remain provider-agnostic.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

DEFAULT_OPENAI_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_OPENAI_READ_TIMEOUT_SECONDS = 180.0
DEFAULT_OPENAI_OVERALL_TIMEOUT_SECONDS = 240.0
OPENAI_MODEL = "gpt-5.6-luna"
OPENAI_JUDGE_MODEL = "gpt-5.6-terra"
SUPPORTED_OPENAI_MODELS = frozenset({OPENAI_MODEL, OPENAI_JUDGE_MODEL})


class OpenAIProviderError(RuntimeError):
    """A bounded, classified OpenAI provider failure."""

    def __init__(self, code: str, message: str, *, observation: dict[str, Any]):
        self.code = code
        self.observation = observation
        super().__init__(message)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dump_response(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return {}


def _usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    dumped = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else {}
    input_details = dumped.get("input_tokens_details") or {}
    output_details = dumped.get("output_tokens_details") or {}
    return {
        "input_tokens": dumped.get("input_tokens"),
        "output_tokens": dumped.get("output_tokens"),
        "reasoning_tokens": output_details.get("reasoning_tokens"),
        "cached_input_tokens": input_details.get("cached_tokens"),
        "total_tokens": dumped.get("total_tokens"),
    }


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return "OPENAI_AUTH_ERROR"
    if isinstance(exc, RateLimitError):
        return "OPENAI_RATE_LIMIT"
    if isinstance(exc, NotFoundError):
        return "OPENAI_MODEL_UNAVAILABLE"
    if isinstance(exc, BadRequestError):
        return "OPENAI_SCHEMA_FAILURE"
    if isinstance(exc, APITimeoutError | TimeoutError):
        return "OPENAI_READ_TIMEOUT"
    if isinstance(exc, APIConnectionError):
        return "OPENAI_CONNECT_FAILURE"
    if isinstance(exc, APIStatusError):
        return "OPENAI_HTTP_ERROR"
    return "OPENAI_UNKNOWN"


def responses_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt an existing logical schema to Responses strict-output rules.

    The project V2.2 parser treats ``reason_code`` as optional.  Responses
    strict JSON schema requires every declared property to be required, so
    the provider representation makes that property nullable while keeping
    the same logical contract and enum value.
    """
    adapted = copy.deepcopy(schema)
    properties = adapted.get("properties", {})
    reason = properties.get("reason_code")
    required = adapted.setdefault("required", [])
    if reason is not None and "reason_code" not in required:
        required.append("reason_code")
        properties["reason_code"] = {
            "anyOf": [
                {"type": "string", "enum": ["INSUFFICIENT_EVIDENCE"]},
                {"type": "null"},
            ]
        }

    def enforce(node: object) -> None:
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if node.get("type") == "object":
            if not isinstance(properties, dict):
                properties = {}
                node["properties"] = properties
            node["additionalProperties"] = False
            node["required"] = list(properties)
        if isinstance(properties, dict):
            for child in properties.values():
                enforce(child)
        items = node.get("items")
        if isinstance(items, dict):
            enforce(items)
        for keyword in ("anyOf", "allOf"):
            variants = node.get(keyword)
            if isinstance(variants, list):
                for variant in variants:
                    enforce(variant)

    enforce(adapted)
    return adapted


def validate_responses_strict_schema_shape(schema: dict[str, Any]) -> None:
    """Reject malformed strict-output schemas before a provider request.

    This intentionally checks only the structural invariants required by the
    repository's Responses schemas.  It is not a replacement for provider
    validation, but it prevents known-invalid object/array/property shapes
    from consuming a live preflight or official request.
    """

    def visit(node: object, path: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            raise ValueError(f"schema node must be an object at {'.'.join(path) or '<root>'}")
        node_type = node.get("type")
        if not path and any(keyword in node for keyword in ("anyOf", "allOf", "oneOf")):
            raise ValueError("Responses strict schema cannot use a union at the root")
        properties = node.get("properties")
        if node_type == "object":
            if node.get("additionalProperties") is not False:
                raise ValueError(
                    "object schema must set additionalProperties=false at "
                    f"{'.'.join(path) or '<root>'}"
                )
            if not isinstance(properties, dict):
                raise ValueError(
                    f"object schema must declare properties at {'.'.join(path) or '<root>'}"
                )
            required = node.get("required")
            if not isinstance(required, list) or set(required) != set(properties):
                raise ValueError(
                    "strict object schema must require every property at "
                    f"{'.'.join(path) or '<root>'}"
                )
        if isinstance(properties, dict):
            for name, child in properties.items():
                if not isinstance(child, dict) or not any(
                    key in child for key in ("type", "anyOf", "allOf", "$ref")
                ):
                    raise ValueError(
                        "property schema must declare a type or union at "
                        f"{'.'.join((*path, 'properties', name))}"
                    )
                visit(child, (*path, "properties", name))
        if node_type == "array":
            items = node.get("items")
            if not isinstance(items, dict):
                raise ValueError(
                    f"array schema must declare items at {'.'.join(path) or '<root>'}"
                )
            visit(items, (*path, "items"))
        for keyword in ("anyOf", "allOf"):
            variants = node.get(keyword)
            if variants is None:
                continue
            if not isinstance(variants, list) or not variants:
                raise ValueError(
                    f"{keyword} must be a non-empty array at {'.'.join(path) or '<root>'}"
                )
            for index, variant in enumerate(variants):
                visit(variant, (*path, keyword, str(index)))

    visit(schema, ())


class OpenAIGeneratorClient:
    """Small async Responses API client with no automatic retries."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        connect_timeout: float = DEFAULT_OPENAI_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = DEFAULT_OPENAI_READ_TIMEOUT_SECONDS,
        overall_timeout: float = DEFAULT_OPENAI_OVERALL_TIMEOUT_SECONDS,
        http_client: httpx.AsyncClient | None = None,
        sdk_client: AsyncOpenAI | None = None,
    ) -> None:
        if api_key is None and not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not configured")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.overall_timeout = overall_timeout
        self._http_client = http_client
        self._owns_http_client = http_client is None
        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        self._client = sdk_client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            http_client=http_client,
        )
        self.last_call_observation: dict[str, Any] | None = None

    @property
    def sdk_version(self) -> str:
        import openai

        return str(openai.__version__)

    async def available_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
        except Exception as exc:
            observation = {
                "status": "FAILED",
                "error_code": _error_code(exc),
                "error_type": type(exc).__name__,
                "completed_at": _now(),
            }
            self.last_call_observation = observation
            raise OpenAIProviderError(
                observation["error_code"], "OpenAI model listing failed", observation=observation
            ) from exc
        return [str(item.id) for item in page.data]

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        schema: dict[str, Any] | None = None,
        reasoning: str = "none",
        max_output_tokens: int = 1024,
        temperature: float | None = 0.0,
        seed: int | None = None,
        **_: Any,
    ) -> str:
        if model not in SUPPORTED_OPENAI_MODELS:
            supported = ", ".join(sorted(SUPPORTED_OPENAI_MODELS))
            raise ValueError(f"OpenAI model mismatch: expected one of {supported}, got {model}")
        text_config: dict[str, Any] | None = None
        sent_schema = responses_strict_schema(schema) if schema is not None else None
        if schema is not None:
            validate_responses_strict_schema_shape(sent_schema)
            text_config = {
                "format": {
                    "type": "json_schema",
                    "name": "rag_answer_v2_2",
                    "strict": True,
                    "schema": sent_schema,
                }
            }
        request_body: dict[str, Any] = {
            "model": model,
            "input": messages,
            "reasoning": {"effort": reasoning},
            "max_output_tokens": max_output_tokens,
            "text": text_config,
        }
        # Responses does not expose a seed parameter in the installed SDK.
        # Keep it in the observation for paired-protocol transparency, but do
        # not send an unsupported field to the provider.
        if temperature is not None:
            request_body["temperature"] = temperature
        observation = {
            "request_id": uuid4().hex,
            "provider": "openai",
            "endpoint": "responses.create",
            "model": model,
            "reasoning": reasoning,
            "max_output_tokens": max_output_tokens,
            "temperature_requested": temperature,
            "temperature_sent": temperature,
            "seed_requested": seed,
            "seed_sent": False,
            "seed_support": "not_supported_by_installed_responses_api",
            "request_hash": canonical_hash(request_body),
            "prompt_content_hash": canonical_hash(messages),
            "logical_schema_hash": canonical_hash(schema) if schema is not None else None,
            "schema_hash": canonical_hash(sent_schema) if sent_schema is not None else None,
            "request_started_at": _now(),
            "headers_received_at": None,
            "first_body_byte_at": None,
            "completed_at": None,
            "elapsed_ms": None,
            "streaming": False,
            "status_code": None,
            "response_bytes": None,
            "response_id": None,
            "status": "STARTED",
            "error_code": None,
            "attempt": 1,
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "cached_input_tokens": None,
                "total_tokens": None,
            },
        }
        self.last_call_observation = observation
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.overall_timeout):
                response = await self._client.responses.create(**request_body)
            observation["headers_received_at"] = _now()
            observation["first_body_byte_at"] = observation["headers_received_at"]
            observation["status_code"] = 200
            observation["response_id"] = getattr(response, "id", None)
            output = str(getattr(response, "output_text", "") or "")
            observation["response_bytes"] = len(output.encode("utf-8"))
            observation["usage"] = _usage(response)
            observation["raw_response"] = _dump_response(response)
            observation["status"] = "COMPLETE"
            return output
        except Exception as exc:
            code = _error_code(exc)
            observation["status"] = "TIMEOUT" if code.endswith("TIMEOUT") else "FAILED"
            observation["error_code"] = code
            observation["error_type"] = type(exc).__name__
            observation["error_message"] = str(exc)[:500]
            raise OpenAIProviderError(
                code, "OpenAI generation failed", observation=observation
            ) from exc
        finally:
            observation["completed_at"] = _now()
            observation["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)

    async def aclose(self) -> None:
        await self._client.close()
