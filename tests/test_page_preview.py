"""Cited page previews: version-pinned, permission-checked, highlight when found."""

import hashlib

import fitz
import pytest

from app.evidence.page_preview import render_preview


def pdf(text="Revenue grew to 4,087 million in 2013."):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_preview_highlights_the_cited_line_when_it_is_on_the_page():
    png, found = render_preview(pdf(), 1, "Revenue grew to 4,087 million in 2013.")
    assert png.startswith(b"\x89PNG") and found


def test_preview_without_a_match_still_shows_the_page():
    png, found = render_preview(pdf(), 1, "A passage that is somewhere else")
    assert png.startswith(b"\x89PNG") and not found


def test_missing_page_is_none():
    assert render_preview(pdf(), 3, None) is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.api.chat import ChatDependencies
    from tests.test_chat_no_evidence import _client, _Search, _Stream

    content = pdf()
    version = hashlib.sha256(content).hexdigest()

    def preview(source_id, document_version, page, highlight):
        if source_id != "report.pdf" or document_version != version:
            return None
        return render_preview(content, page, highlight)

    deps = ChatDependencies(
        search_fn=_Search([]),
        stream_fn=_Stream(),
        page_preview_fn=preview,
        page_preview_tenant="tenant-a",
    )
    return _client(tmp_path, deps), version


def get(client, version, token="token-user-a", **params):
    query = {
        "source_type": "filesystem",
        "source_id": "report.pdf",
        "document_version": version,
        "page": 1,
        **params,
    }
    return client.get(
        "/research/documents/page", params=query, headers={"Authorization": f"Bearer {token}"}
    )


def test_endpoint_returns_the_pinned_page_with_highlight_status(client):
    http, version = client
    response = get(http, version, highlight="Revenue grew to 4,087 million")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-highlight-found"] == "1"
    assert "private" in response.headers["cache-control"]


def test_endpoint_hides_other_tenants_and_other_versions(client):
    http, version = client
    assert get(http, version, token="token-user-b").status_code == 404
    assert get(http, "0" * 64).status_code == 404
    assert get(http, version, page=9).status_code == 404
