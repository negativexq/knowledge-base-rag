# ruff: noqa: F811  (pytest fixtures imported from test_research_api)
"""A reviewed feedback report with a correct answer becomes an evaluation
candidate; unreviewed user text never does."""

import json

from app.security.models import Role
from tests.test_research_api import body, client, identity, user  # noqa: F401


def report(client, **kwargs):
    response = client.post(
        "/research/feedback",
        json=body(expected_answer="SSH", expected_source="windows.md", expected_page=3, **kwargs),
    )
    assert response.status_code == 201
    return response.json()


def test_users_can_say_what_the_right_answer_and_source_are(client):
    record = report(client)
    assert (record["expected_answer"], record["expected_source"], record["expected_page"]) == (
        "SSH",
        "windows.md",
        3,
    )


def test_only_an_operator_can_promote_and_the_reviewed_answer_wins(client):
    record = report(client)
    path = f"/research/feedback/{record['id']}/promote"
    assert client.post(path, json={}).status_code == 403
    identity(client, user(role=Role.OPERATOR))
    promoted = client.post(path, json={"expected_answer": "SSH 2"})
    assert promoted.status_code == 201
    candidate = promoted.json()
    assert candidate["question"] == "Which protocol?"
    assert candidate["expected_answer"] == "SSH 2"
    assert candidate["origin"] == "user_feedback" and candidate["feedback_id"] == record["id"]
    assert client.get("/research/feedback?status=resolved").json()[0]["id"] == record["id"]
    # Promoting twice keeps one candidate.
    assert client.post(path, json={}).status_code == 409


def test_a_report_without_any_expected_answer_cannot_be_promoted(client):
    record = client.post("/research/feedback", json=body()).json()
    identity(client, user(role=Role.OPERATOR))
    response = client.post(f"/research/feedback/{record['id']}/promote", json={})
    assert response.status_code == 422


def test_candidates_export_as_jsonl_per_tenant(client):
    record = report(client)
    identity(client, user(role=Role.OPERATOR))
    client.post(f"/research/feedback/{record['id']}/promote", json={})
    response = client.get("/research/evaluation-candidates.jsonl")
    assert response.headers["content-type"].startswith("application/x-ndjson")
    [row] = [json.loads(line) for line in response.text.splitlines()]
    assert set(row) == {
        "id",
        "question",
        "expected_answer",
        "expected_source",
        "expected_page",
        "reason",
        "origin",
        "feedback_id",
        "created_at",
    }
    identity(client, user(tenant="b", role=Role.OPERATOR))
    assert client.get("/research/evaluation-candidates.jsonl").text == ""
