import os

import httpx

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_URL, timeout=30.0)


def fetch_sources(client: httpx.Client | None = None) -> list[dict]:
    owns_client = client is None
    client = client or _client()
    try:
        response = client.get("/sources")
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            client.close()


def trigger_sync(source_type: str, client: httpx.Client | None = None) -> dict:
    """Returns the response body on both success and a known-shaped error
    (409 "already running") rather than raising — the Sources page renders
    either as a message, it doesn't need an exception to distinguish them.
    """
    owns_client = client is None
    client = client or _client()
    try:
        response = client.post(f"/sync/{source_type}")
        if response.status_code >= 500:
            response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            client.close()


def fetch_sync_history(source_type: str, client: httpx.Client | None = None) -> list[dict]:
    owns_client = client is None
    client = client or _client()
    try:
        response = client.get(f"/sync/{source_type}/history")
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            client.close()
