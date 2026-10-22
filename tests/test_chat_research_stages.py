"""Research mode tells the browser it is searching before retrieval returns,
so a long first search is not a silent screen."""

from app.api.chat import ChatDependencies
from tests.test_chat_no_evidence import _ask, _chunk, _client, _events, _Search


class _ResearchStream:
    async def __call__(self, question, chunks, **kwargs):
        yield {"type": "metadata", "prompt_version": "v3", "trace_id": "t"}
        yield {"type": "token", "content": "Refunds take 30 days [E1.S1]"}


def test_research_mode_reports_retrieval_before_the_first_source(tmp_path):
    deps = ChatDependencies(
        search_fn=_Search([_chunk()]), stream_fn=_ResearchStream(), agentic_rag_enabled=True
    )
    events = _events(_ask(_client(tmp_path, deps)))
    names = [name for name, _ in events]
    stages = [data for name, data in events if name == "research_progress"]
    assert [(s["stage"], s["status"]) for s in stages] == [
        ("retrieval", "running"),
        ("retrieval", "completed"),
    ]
    assert stages[0]["kind"] == "stage" and stages[0]["message"]
    assert isinstance(stages[1]["duration_ms"], int)
    assert names.index("research_progress") < names.index("sources")


def test_answer_mode_keeps_its_event_stream(tmp_path):
    deps = ChatDependencies(search_fn=_Search([_chunk()]), stream_fn=_ResearchStream())
    events = _events(_ask(_client(tmp_path, deps)))
    assert "research_progress" not in [name for name, _ in events]
