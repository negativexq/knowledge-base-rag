import json
from pathlib import Path

import pytest

from app.evaluation.forensic_capture import (
    ForensicCapture,
    metadata_for_chunks,
    redact_for_otel,
    reset_current_capture,
    set_current_capture,
)
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings


def _block(text: str = "The limit is 120 requests per minute.") -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": "fixture",
            "page_number": 1,
            "paragraph_index": 0,
            "tenant_id": "tenant-a",
            "document_version": "v1",
            "section_key": "rate-limits",
            "authorized": True,
            "model_visible": True,
        },
    )


def test_forensic_capture_defaults_are_disabled_and_raw_text_is_off():
    settings = Settings(_env_file=None)

    assert settings.rag_forensic_capture_enabled is False
    assert settings.rag_forensic_capture_raw_text is False
    assert settings.rag_forensic_capture_dir is None


def test_raw_text_requires_explicit_capture_enablement():
    with pytest.raises(ValueError, match="requires RAG_FORENSIC_CAPTURE_ENABLED"):
        Settings(_env_file=None, rag_forensic_capture_raw_text=True)


def test_disabled_capture_writes_nothing(tmp_path):
    capture = ForensicCapture.create("secret question", raw_text=False)

    assert capture.write(None) is None
    assert list(tmp_path.iterdir()) == []


def test_metadata_capture_omits_raw_content(tmp_path):
    capture = ForensicCapture.create("secret question", raw_text=False)
    capture.stage(
        "generation",
        {"raw_model_output": "secret answer", "provider_model": "test-model"},
    )
    output = capture.write(str(tmp_path))

    assert output is not None
    data = json.loads(Path(output).read_text())
    assert "raw_query" not in data
    assert "raw_model_output" not in data["stages"]["generation"]
    assert data["stages"]["generation"]["provider_model"] == "test-model"


def test_raw_capture_is_local_and_redacts_secret_like_fields(tmp_path):
    capture = ForensicCapture.create("safe fixture question", raw_text=True)
    capture.stage(
        "generation",
        {
            "raw_model_output": "safe answer",
            "openai_api_key": "sk-not-persisted",
            "text": "safe local evidence",
        },
    )
    output = capture.write(str(tmp_path))
    data = json.loads(Path(output).read_text())

    assert data["raw_query"] == "safe fixture question"
    assert data["stages"]["generation"]["raw_model_output"] == "safe answer"
    assert data["stages"]["generation"]["text"] == "safe local evidence"
    assert data["stages"]["generation"]["openai_api_key"] == "[REDACTED]"


def test_otel_redaction_never_carries_raw_text():
    bounded = redact_for_otel(
        {"raw_query": "private query", "raw_model_output": "private answer", "outcome": "PASS"}
    )

    assert "raw_query" not in bounded
    assert "raw_model_output" not in bounded
    assert bounded["outcome"] == "PASS"


def test_capture_write_failure_is_non_fatal(tmp_path):
    not_a_directory = tmp_path / "capture-target"
    not_a_directory.write_text("not a directory")
    capture = ForensicCapture.create("question", raw_text=True)

    assert capture.write(str(not_a_directory)) is None


def test_metadata_for_chunks_is_bounded():
    metadata = metadata_for_chunks([_block()])

    assert metadata[0]["chunk_id"] == "chunk-1"
    assert metadata[0]["source_id"] == "fixture"
    assert "text" not in metadata[0]


class _FakeProvider:
    async def chat_json(self, messages, **kwargs):
        return json.dumps(
            {
                "answer_parts": [
                    {"text": "The limit is 120 requests per minute.", "support_ids": ["E1.S1"]}
                ],
                "abstain": False,
            }
        )


@pytest.mark.asyncio
async def test_raw_capture_covers_generation_validation_citation_and_visible_stages(tmp_path):
    capture = ForensicCapture.create("What is the limit?", raw_text=True)
    token = set_current_capture(capture)
    try:
        events = [
            event
            async for event in stream_support_unit_answer(
                "What is the limit?",
                [_block()],
                _FakeProvider(),
                model="fixture-model",
                validator_version="baseline",
                shadow_enabled=True,
            )
        ]
    finally:
        reset_current_capture(token)

    capture_path = capture.write(str(tmp_path))
    data = json.loads(Path(capture_path).read_text())
    stages = data["stages"]

    assert any(event["type"] == "token" for event in events)
    assert stages["generation"]["structured_output_parse_status"] == "PARSED"
    assert stages["generation"]["model_support_ids"] == ["E1.S1"]
    assert stages["support_id_validation"]["accepted_support_ids"] == ["E1.S1"]
    assert stages["support_id_validation"]["critical_validator"]["invocations"] == 1
    assert stages["support_id_validation"]["critical_validator"]["shadow_v3_outcomes"] == [
        "PASS"
    ]
    assert stages["citation_resolution"]["resolved_citation_ids"] == ["E1.S1"]
    assert stages["visible_response"]["outcome"] == "ANSWER"
