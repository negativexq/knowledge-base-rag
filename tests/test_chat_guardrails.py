"""Input guardrails on POST /chat: a bounded question length and a
per-user request rate limit. Both reject before retrieval or generation
runs, so an oversized or flooding caller costs no embedding, reranker or
LLM work."""

from fastapi.testclient import TestClient

from app.api.chat import ChatDependencies
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
from app.security.models import RetrievalContext
from app.security.rate_limit import SlidingWindowRateLimiter
from app.shared.config import Settings
from app.sync.history import SyncHistory


class _StubManager:
    known_source_types: list[str] = []

    def is_running(self, source_type):
        return False


class _CountingSearch:
    def __init__(self):
        self.calls = 0

    async def __call__(
        self, question: str, context: RetrievalContext, report: RetrievalReport
    ) -> list[SearchResult]:
        self.calls += 1
        return []


async def _ok_stream(question: str, chunks: list[SearchResult]):
    yield {"type": "token", "content": "ok"}


def _client(tmp_path, search, **settings) -> TestClient:
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return TestClient(
        create_app(
            _StubManager(),
            history,
            registry,
            chat_deps=ChatDependencies(search_fn=search, stream_fn=_ok_stream),
            token_authenticator=TokenAuthenticator(DEFAULT_DEV_TOKENS),
            auth_enabled=True,
            settings=Settings(_env_file=None, **settings),
        )
    )


def _ask(client: TestClient, question: str, token: str = "token-user-a"):
    return client.post(
        "/chat", json={"question": question}, headers={"Authorization": f"Bearer {token}"}
    )


# --- question length -------------------------------------------------------


def test_question_at_the_limit_is_accepted(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_max_question_chars=10)

    response = _ask(client, "x" * 10)

    assert response.status_code == 200
    assert search.calls == 1


def test_question_over_the_limit_is_rejected_before_retrieval(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_max_question_chars=10)

    response = _ask(client, "x" * 11)

    assert response.status_code == 422
    assert "10" in response.json()["detail"]
    assert search.calls == 0


def test_blank_question_is_rejected_before_retrieval(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search)

    response = _ask(client, "   \n\t ")

    assert response.status_code == 422
    assert search.calls == 0


def test_length_is_measured_after_trimming_surrounding_whitespace(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_max_question_chars=5)

    assert _ask(client, "  hello  ").status_code == 200


# --- rate limit ------------------------------------------------------------


def test_requests_over_the_per_user_limit_get_429_with_retry_after(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_rate_limit_per_minute=2)

    assert _ask(client, "one").status_code == 200
    assert _ask(client, "two").status_code == 200
    response = _ask(client, "three")

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert search.calls == 2


def test_rate_limit_is_per_user_not_global(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_rate_limit_per_minute=1)

    assert _ask(client, "a", token="token-user-a").status_code == 200
    assert _ask(client, "a again", token="token-user-a").status_code == 429
    assert _ask(client, "b", token="token-user-b").status_code == 200


def test_rejected_long_questions_still_count_against_the_rate_limit(tmp_path):
    """Otherwise a client could flood the endpoint with oversized bodies
    for free."""
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_rate_limit_per_minute=1, chat_max_question_chars=3)

    assert _ask(client, "too long").status_code == 422
    assert _ask(client, "ok").status_code == 429


def test_unauthenticated_requests_get_401_not_429(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_rate_limit_per_minute=1)

    for _ in range(3):
        assert client.post("/chat", json={"question": "hi"}).status_code == 401


def test_rate_limit_zero_disables_it(tmp_path):
    search = _CountingSearch()
    client = _client(tmp_path, search, chat_rate_limit_per_minute=0)

    for i in range(5):
        assert _ask(client, f"q{i}").status_code == 200


# --- limiter unit ----------------------------------------------------------


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window_frees_slots_once_old_requests_leave_the_window():
    clock = _Clock()
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.check("k") is None
    clock.now += 10
    assert limiter.check("k") is None
    clock.now += 10
    retry_after = limiter.check("k")
    # The oldest request (t=1000) leaves the window at t=1060; now is 1020.
    assert retry_after == 40

    clock.now = 1060.5
    assert limiter.check("k") is None


def test_rejected_attempts_do_not_extend_the_window():
    clock = _Clock()
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.check("k") is None
    for _ in range(5):
        clock.now += 1
        assert limiter.check("k") is not None

    clock.now = 1060.5
    assert limiter.check("k") is None


def test_keys_with_no_recent_requests_are_dropped():
    clock = _Clock()
    limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60, clock=clock)
    for i in range(100):
        limiter.check(f"user-{i}")

    clock.now += 61
    limiter.check("someone-new")

    assert limiter.tracked_keys() == 1
