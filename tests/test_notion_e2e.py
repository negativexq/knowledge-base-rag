"""Real Notion API test — skipped automatically unless NOTION_API_KEY is
set (same honesty pattern as Sprint 1's ANTHROPIC_API_KEY /
test_provider_comparison_e2e.py). This machine has neither a real key nor
a .env file, so this test has NOT been run against a live workspace — see
docs/PLANNING.md's Sprint 6 closing note.

If NOTION_API_KEY is set (pointing at an integration with access to at
least one page), this proves a real page is really listed, fetched, and
chunked.
"""

import pytest

from app.connectors.notion import NotionConnector
from app.shared.config import settings


@pytest.mark.skipif(not settings.notion_api_key, reason="requires NOTION_API_KEY")
@pytest.mark.asyncio
async def test_lists_and_fetches_at_least_one_real_page():
    connector = NotionConnector(api_key=settings.notion_api_key)
    try:
        documents = await connector.list_documents()
        assert documents, "integration has no accessible pages — share at least one with it"

        content = await connector.fetch_content(documents[0])
        assert isinstance(content, bytes)

        content_hash = await connector.get_content_hash(documents[0])
        assert content_hash
    finally:
        await connector.aclose()
