"""When retrieval leaves no authorized evidence, POST /chat answers with the
fixed not-found reply and never calls the model: there is nothing to ground
an answer in, so a model call can only cost latency or invent one."""

import json

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.api.chat as chat_module
from app.api.chat import ChatDependencies
from app.llm.prompt import NOT_FOUND_PHRASE
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
from app.shared.config import Settings
from app.sync.history import SyncHistory


class _StubManager:
    known_source_types: list[str] = []

    def is_running(self, source_type):
        return False


def _chunk() -> SearchResult:
    return SearchResult(
        score=0.9,
        id="c1",
        payload={"text": "Refunds take 30 days.", "source_type": "pdf", "source_id": "doc"},
    )


class _Search:
    def __init__(self, results):
        self._results = results

    async def __call__(self, question, context, report):
        return list(self._results)


class _Stream:
    def __init__(self):
        self.calls = 0

    async def __call__(self, question, chunks):
        self.calls += 1
        yield {"type": "metadata", "prompt_version": "v3", "trace_id": "from-generate"}
        yield {"type": "token", "content": "Refunds take 30 days [E1.S1]"}


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(chat_module, "get_tracer", provider.get_tracer)
    return exporter


def _client(tmp_path, deps: ChatDependencies) -> TestClient:
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return TestClient(
        create_app(
            _StubManager(),
            history,
            registry,
            chat_deps=deps,
            token_authenticator=TokenAuthenticator(DEFAULT_DEV_TOKENS),
            auth_enabled=True,
            settings=Settings(_env_file=None),
        )
    )


def _events(response) -> list[tuple[str, dict]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        name = "message"
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :])
        events.append((name, data))
    return events


def _ask(client):
    return client.post(
        "/chat",
        json={"question": "What is the refund window?"},
        headers={"Authorization": "Bearer token-user-a"},
    )


def test_no_retrieved_evidence_skips_the_model_and_answers_not_found(tmp_path, spans):
    stream = _Stream()
    client = _client(tmp_path, ChatDependencies(search_fn=_Search([]), stream_fn=stream))

    response = _ask(client)

    assert response.status_code == 200
    assert stream.calls == 0
    tokens = [data["token"] for name, data in _events(response) if name == "message"]
    assert tokens == [NOT_FOUND_PHRASE]
    assert _events(response)[-1][0] == "done"


def test_skipped_generation_reports_an_abstention_and_a_trace_id(tmp_path, spans):
    client = _client(tmp_path, ChatDependencies(search_fn=_Search([]), stream_fn=_Stream()))

    events = _events(_ask(client))

    [metadata] = [data for name, data in events if name == "metadata"]
    chat_span = next(s for s in spans.get_finished_spans() if s.name == "chat_request")
    assert metadata["trace_id"] == format(chat_span.context.trace_id, "032x")
    assert metadata["generation_skipped"] == "NO_RETRIEVAL_CANDIDATES"
    validation = [data for name, data in events if name == "security" and "abstain" in data]
    assert validation == [
        {
            "passed": True,
            "violations": [],
            "validator_failure_codes": [],
            "citation_suppressed": True,
            "hidden_prompt_leaked": False,
            "abstain": True,
            "application_forced_abstention": False,
        }
    ]
    assert chat_span.attributes["answerability.generation_skipped"] is True
    assert not any(s.name == "generate" for s in spans.get_finished_spans())


def test_evidence_step_that_returns_nothing_also_skips_the_model(tmp_path, spans):
    stream = _Stream()

    async def no_evidence(chunks, context):
        return []

    client = _client(
        tmp_path,
        ChatDependencies(search_fn=_Search([_chunk()]), stream_fn=stream, evidence_fn=no_evidence),
    )

    events = _events(_ask(client))

    assert stream.calls == 0
    [metadata] = [data for name, data in events if name == "metadata"]
    assert metadata["generation_skipped"] == "NO_EVIDENCE_BLOCKS"


def test_retrieved_evidence_still_goes_to_the_model(tmp_path, spans):
    stream = _Stream()
    client = _client(tmp_path, ChatDependencies(search_fn=_Search([_chunk()]), stream_fn=stream))

    events = _events(_ask(client))

    assert stream.calls == 1
    [metadata] = [data for name, data in events if name == "metadata"]
    assert "generation_skipped" not in metadata
    chat_span = next(s for s in spans.get_finished_spans() if s.name == "chat_request")
    assert chat_span.attributes["answerability.generation_skipped"] is False
