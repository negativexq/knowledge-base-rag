"""Sprint 18: a second, real English Markdown fixture — "Nimbus API
Reference" — written to expand the EN-content side of the multilingual
embedding benchmark's golden set past the original PDF handbook's 6
usable facts. Flat H1-only sections (no nesting) so each fact maps to
one unambiguous heading-path location, same discipline
golden_markdown_source.py already established for the TR side.
"""

GOLDEN_API_REFERENCE_EN_TEXT = """\
# Authentication

All Nimbus API requests must include an `Authorization: Bearer <token>`
header. Tokens are obtained via the `/oauth/token` endpoint and expire
after 60 minutes; there is no refresh-token grant for the public API,
so a client must request a new token on expiry.

# Rate Limits

The default rate limit is 120 requests per minute per API key. A request
that exceeds the limit receives a 429 status code with a `Retry-After`
header indicating how many seconds to wait before retrying.

# Pagination

List endpoints return at most 50 items per page by default, controlled
by the `limit` query parameter (maximum 200). The response includes a
`next_cursor` field; passing it as the `cursor` query parameter on the
next request continues the listing.

# Webhooks

Webhook payloads are signed with HMAC-SHA256 using the webhook secret
shown in the dashboard. The signature is sent in the
`X-Nimbus-Signature` header, and Nimbus retries a failed delivery up to
5 times with exponential backoff before giving up.

# Error Codes

A 409 Conflict response means the requested operation would violate a
uniqueness constraint, most commonly creating a folder whose name
already exists at the same path. A 422 Unprocessable Entity means the
request body was valid JSON but failed schema validation.

# API Versioning

The current API version is v3, specified via the `Nimbus-Version`
request header. Omitting the header defaults to v2 for backward
compatibility, but v2 is deprecated and scheduled for removal;
new integrations should always send `Nimbus-Version: v3` explicitly.

# File Upload Size Limits

The direct upload endpoint accepts files up to 5GB. Files larger than
5GB must use the multipart upload endpoint, which accepts individual
parts of up to 500MB each and requires a final `/complete` call to
assemble them.

# Idempotency

Write endpoints (POST, PUT) accept an optional `Idempotency-Key` header.
Replaying the same request with the same key within 24 hours returns
the original response without performing the operation again, which is
the recommended way to safely retry a request after a timeout.

# Sandbox Environment

A sandbox environment is available at `https://sandbox-api.nimbuscloud.example`
for testing integrations without affecting production data. Sandbox API
keys are prefixed with `sk_test_` and never count against production
rate limits.

# Deprecation Policy

A deprecated endpoint remains available for at least 12 months after
its replacement ships, and every response from a deprecated endpoint
includes a `Sunset` header with the exact removal date.

# Authentication Scopes

OAuth tokens carry one or more scopes: `files:read`, `files:write`,
`admin:users`, and `admin:billing`. A token missing the required scope
for an endpoint receives a 403 Forbidden, distinct from a 401
Unauthorized (which means the token itself is invalid or expired).

# Bulk Operations

The `/files/bulk-delete` endpoint accepts up to 1000 file IDs in a
single request. Requests with more than 1000 IDs are rejected with a
400 Bad Request before any deletion happens — bulk operations are
all-or-nothing at the validation stage, though individual deletions
within a valid batch can still fail independently.

# Search Endpoint

The `/search` endpoint supports full-text query via the `q` parameter
and accepts an optional `filetype` filter (e.g. `pdf`, `docx`, `png`).
Search results are capped at 100 matches per request regardless of the
`limit` parameter; retrieving more requires narrowing the query.

# Metadata Fields

Every file object includes `created_at`, `modified_at`, and
`content_hash` (a SHA-256 hex digest of the file's raw bytes, used by
clients to detect whether a local copy is stale without downloading
the full file).

# Retry Policy

Client libraries should retry on 502, 503, and 504 responses using
exponential backoff starting at 1 second, capped at 30 seconds, for up
to 5 attempts. A 500 Internal Server Error should NOT be retried
automatically — it usually indicates a bug that a retry won't resolve.

# Webhook Event Types

Webhook events include `file.created`, `file.deleted`,
`file.shared`, and `quota.exceeded`. The `quota.exceeded` event fires
once per billing period the first time an account crosses 90% of its
storage limit, not on every subsequent write past that threshold.

# Content-Type Requirements

The `/files/upload` endpoint requires `Content-Type:
multipart/form-data` — a JSON body for this endpoint is rejected with
a 415 Unsupported Media Type. All other write endpoints require
`Content-Type: application/json`.

# Timezone Handling

All timestamps returned by the API are in UTC, formatted as ISO 8601
with a trailing `Z` (e.g. `2024-03-01T12:00:00Z`). The API never
returns timestamps in a client's local timezone; conversion is the
client's responsibility.

# API Key Rotation

An account can have up to 2 active API keys simultaneously,
specifically to support zero-downtime rotation: generate a new key,
update the client, then revoke the old key. A third key cannot be
created until one of the existing two is revoked.

# Health Check Endpoint

`/health` requires no authentication and returns a 200 status with
`{"status": "ok"}` when the API is reachable. It does not verify
downstream storage or database connectivity — a 200 from `/health`
does not guarantee that file operations will succeed.
"""


def build_golden_api_reference_en(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(GOLDEN_API_REFERENCE_EN_TEXT)


if __name__ == "__main__":
    import sys

    default_path = "golden_api_reference_en.md"
    build_golden_api_reference_en(sys.argv[1] if len(sys.argv) > 1 else default_path)
