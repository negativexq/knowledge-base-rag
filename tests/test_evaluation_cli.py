"""The golden-set CLI must measure the production chat path: the same
search → evidence → support-ID generation steps app/api/chat.py runs,
taken from app/wiring.py::build_chat_dependencies, not a second,
hand-wired copy that can drift (legacy embedding model, legacy prompt
path)."""

import pytest

from app.api.chat import ChatDependencies
from app.evaluation.cli import evaluation_callables, evaluation_settings
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.security.models import RetrievalContext
from app.shared.config import Settings


def _chunk(text: str) -> SearchResult:
    return SearchResult(score=0.9, payload={"text": text, "source_id": "doc"})


class _Recorder:
    def __init__(self):
        self.search_context: RetrievalContext | None = None
        self.search_report: RetrievalReport | None = None
        self.evidence_input: list[SearchResult] | None = None
        self.generated_with: list[SearchResult] | None = None

    async def search(self, question, context, report):
        self.search_context = context
        self.search_report = report
        return [_chunk("retrieved")]

    async def evidence(self, chunks, context):
        self.evidence_input = chunks
        return [_chunk("evidence block")]

    async def stream(self, question, chunks):
        self.generated_with = chunks
        yield {"type": "metadata", "trace_id": "t"}
        yield {"type": "token", "content": "Answer "}
        yield {"type": "token", "content": "[E1.S1]"}
        yield {"type": "security_validation", "passed": True}


@pytest.mark.asyncio
async def test_search_runs_production_search_as_the_system_context():
    recorder = _Recorder()
    deps = ChatDependencies(
        search_fn=recorder.search, stream_fn=recorder.stream, evidence_fn=recorder.evidence
    )
    search_fn, _ = evaluation_callables(deps)

    chunks = await search_fn("q")

    assert [c.payload["text"] for c in chunks] == ["retrieved"]
    assert recorder.search_context == RetrievalContext.system()
    assert isinstance(recorder.search_report, RetrievalReport)


@pytest.mark.asyncio
async def test_generate_builds_evidence_then_joins_the_visible_tokens():
    recorder = _Recorder()
    deps = ChatDependencies(
        search_fn=recorder.search, stream_fn=recorder.stream, evidence_fn=recorder.evidence
    )
    _, generate_fn = evaluation_callables(deps)

    answer = await generate_fn("q", [_chunk("retrieved")])

    assert answer == "Answer [E1.S1]"
    assert [c.payload["text"] for c in recorder.evidence_input] == ["retrieved"]
    assert [c.payload["text"] for c in recorder.generated_with] == ["evidence block"]


@pytest.mark.asyncio
async def test_generate_without_an_evidence_step_uses_the_retrieved_chunks():
    recorder = _Recorder()
    deps = ChatDependencies(search_fn=recorder.search, stream_fn=recorder.stream)
    _, generate_fn = evaluation_callables(deps)

    await generate_fn("q", [_chunk("retrieved")])

    assert [c.payload["text"] for c in recorder.generated_with] == ["retrieved"]


def test_evaluation_settings_keep_production_defaults():
    base = Settings(_env_file=None)

    settings = evaluation_settings(base, generation_model=None, use_reranker=True)

    assert settings.ollama_model == base.ollama_model
    assert settings.embedding_model_key == base.embedding_model_key
    assert settings.reranker_enabled == base.reranker_enabled


def test_evaluation_settings_apply_overrides_without_touching_the_base():
    base = Settings(_env_file=None)

    settings = evaluation_settings(base, generation_model="other:1b", use_reranker=False)

    assert settings.ollama_model == "other:1b"
    assert settings.reranker_enabled is False
    assert base.ollama_model != "other:1b"
