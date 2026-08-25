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
"""


def build_golden_api_reference_en(output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(GOLDEN_API_REFERENCE_EN_TEXT)


if __name__ == "__main__":
    import sys

    default_path = "golden_api_reference_en.md"
    build_golden_api_reference_en(sys.argv[1] if len(sys.argv) > 1 else default_path)
