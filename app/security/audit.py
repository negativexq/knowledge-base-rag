"""Sprint 23 section 22: minimal structured audit events — NOT a SIEM.
A single logger call per security-relevant decision, carrying only
non-sensitive identifiers (user_id, tenant_id, endpoint, action) — never
a raw token, request body, or document content. `extra=` puts these
fields on the LogRecord so any real log pipeline (structured JSON
logging, an aggregator) can filter/query on them without parsing the
message string.
"""

import logging

logger = logging.getLogger("app.security.audit")

AUTHENTICATION_FAILED = "authentication_failed"
AUTHORIZATION_DENIED = "authorization_denied"
SYNC_DENIED = "sync_denied"


def log_audit_event(event: str, **fields: object) -> None:
    logger.info("security_audit_event=%s %s", event, fields, extra={"audit_event": event, **fields})
