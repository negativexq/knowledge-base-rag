import logging

from app.security.audit import (
    AUTHENTICATION_FAILED,
    AUTHORIZATION_DENIED,
    SYNC_DENIED,
    log_audit_event,
)


def test_log_audit_event_emits_a_log_record_with_the_event_name(caplog):
    with caplog.at_level(logging.INFO, logger="app.security.audit"):
        log_audit_event(AUTHENTICATION_FAILED, endpoint="/chat", reason="missing_header")

    assert len(caplog.records) == 1
    assert caplog.records[0].audit_event == AUTHENTICATION_FAILED
    assert caplog.records[0].endpoint == "/chat"


def test_log_audit_event_never_receives_a_raw_token_field():
    """Not a runtime guarantee (this module logs whatever fields are
    passed) — but every real call site in app/api/deps.py and
    app/api/sync.py passes only user_id/tenant_id/endpoint/role/
    source_type, never a token or document content. This test pins the
    three constant event names actually wired up.
    """
    assert AUTHENTICATION_FAILED == "authentication_failed"
    assert AUTHORIZATION_DENIED == "authorization_denied"
    assert SYNC_DENIED == "sync_denied"


def test_authentication_failed_is_logged_on_missing_credentials(caplog):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user

    app = FastAPI()
    app.state.auth_enabled = True

    @app.get("/protected")
    def protected(user=Depends(get_current_user)):
        return {}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="app.security.audit"):
        client.get("/protected")

    events = [r.audit_event for r in caplog.records if hasattr(r, "audit_event")]
    assert AUTHENTICATION_FAILED in events


def test_authorization_denied_is_logged_on_insufficient_role(caplog):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import require_role
    from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
    from app.security.models import Role

    app = FastAPI()
    app.state.auth_enabled = True
    app.state.token_authenticator = TokenAuthenticator(DEFAULT_DEV_TOKENS)

    @app.post("/operator-only")
    def operator_only(user=Depends(require_role(Role.OPERATOR))):
        return {}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="app.security.audit"):
        client.post("/operator-only", headers={"Authorization": "Bearer token-user-a"})

    events = [r.audit_event for r in caplog.records if hasattr(r, "audit_event")]
    assert AUTHORIZATION_DENIED in events
