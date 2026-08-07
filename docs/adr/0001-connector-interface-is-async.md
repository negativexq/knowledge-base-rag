# 0001 — `Connector` Protocol methods are `async def`

## Context

Sprint 3 introduced the `Connector` Protocol (`list_documents()`,
`fetch_content()`, `get_content_hash()`) for `LocalFilesystemConnector`.
Local disk I/O is fast and synchronous in practice, so the Protocol was
originally defined with plain `def` methods — matching the synchronous
precedent already set by `QdrantStore` and `DocumentRegistry` at the
time.

Sprint 6 added `NotionConnector`, the first connector needing real
network I/O (`httpx.AsyncClient` calls to the Notion API, including
429-retry backoff sleeps). A synchronous Protocol cannot be satisfied by
a method that needs to `await` a network call without blocking the event
loop.

## Decision

Generalize the Protocol to `async def` for all three methods
(`list_documents`, `fetch_content`, `get_content_hash`) as part of
Sprint 6, rather than inventing a second, network-capable Protocol
alongside the original sync one.

`LocalFilesystemConnector` absorbs this at zero real cost — wrapping
synchronous disk I/O in an `async def` with no internal `await` is valid
Python and has no performance penalty. The reverse direction (fitting an
inherently-async connector into a sync Protocol) is not possible without
blocking hacks (`asyncio.run()` inside a sync method, thread pools, etc.)
— so async was the only direction that actually generalizes to both
current implementations.

## Consequences

- Every `Connector` implementation, present and future, must use
  `async def` for these three methods, even ones with no real I/O to
  await (e.g. a hypothetical in-memory test connector).
- `ingest_connector` (`app/ingestion/ingest.py`) awaits all three calls;
  no synchronous call sites remain.
- `ConnectorDocument` gained an `etag: str | None = None` field in the
  same sprint for a related reason: `get_content_hash()` originally
  assumed hashing the full fetched content was always cheap (true for
  local files, false for a network-bound page whose blocks would need a
  full re-fetch on every sync just to check "did this change"). `etag`
  lets a connector answer that cheaply when it already has one (Notion's
  `last_edited_time`, captured during `list_documents()`).
