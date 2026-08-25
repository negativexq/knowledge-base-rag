"""Sprint 23: FastAPI dependencies enforcing the auth/RBAC boundary.

get_current_user reads `Authorization: Bearer <token>` and resolves it
via `request.app.state.token_authenticator` (wired in app/main.py's
create_app, real instance built in app/wiring.py::build_app — see
app/security/auth.py). It NEVER reads tenant_id/roles from the request
body/query string — those only ever come from a token the server itself
already knows about.

`app.state.auth_enabled` defaults to True; setting it False is a LOUD,
explicit local-dev-only escape hatch (app/wiring.py logs a warning at
startup when it's off) — never the silent default. See
docs/security.md.
"""

from fastapi import Depends, HTTPException, Request

from app.security.audit import AUTHENTICATION_FAILED, AUTHORIZATION_DENIED, log_audit_event
from app.security.models import Role, UserContext

_DEV_BYPASS_USER = UserContext(
    user_id="dev-bypass", tenant_id="local-dev", roles=frozenset({Role.ADMIN})
)


def get_current_user(request: Request) -> UserContext:
    if getattr(request.app.state, "auth_enabled", True) is False:
        # Explicit, documented local-dev-only bypass — never the default.
        # See app/wiring.py's startup warning log for this exact case.
        return _DEV_BYPASS_USER

    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        log_audit_event(AUTHENTICATION_FAILED, endpoint=request.url.path, reason="missing_header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    authenticator = getattr(request.app.state, "token_authenticator", None)
    if authenticator is None:
        log_audit_event(
            AUTHENTICATION_FAILED, endpoint=request.url.path, reason="not_configured"
        )
        raise HTTPException(status_code=401, detail="Authentication is not configured")

    user = authenticator.authenticate(token)
    if user is None:
        log_audit_event(AUTHENTICATION_FAILED, endpoint=request.url.path, reason="invalid_token")
        raise HTTPException(status_code=401, detail="Invalid or unknown token")
    return user


def require_role(required: Role):
    """Returns a FastAPI dependency that first resolves the caller's
    UserContext (401 on missing/invalid credentials, same as
    get_current_user), then requires role >= `required` (403 otherwise).
    A separate factory function, not a single fixed dependency, since
    different endpoints need different minimum roles
    (/sync needs OPERATOR+, /chat only needs USER+).
    """

    def _dependency(
        request: Request, user: UserContext = Depends(get_current_user)
    ) -> UserContext:
        if not user.has_role(required):
            log_audit_event(
                AUTHORIZATION_DENIED,
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                endpoint=request.url.path,
                required_role=required.value,
                actual_roles=[r.value for r in user.roles],
            )
            raise HTTPException(
                status_code=403,
                detail=f"This action requires role {required.value} or higher",
            )
        return user

    return _dependency
