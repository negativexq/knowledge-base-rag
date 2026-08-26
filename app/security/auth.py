"""Token -> UserContext mapping — a real trust boundary, not
a full OAuth/OIDC stack (out of scope for this local-first portfolio
repo; see docs/security.md's known limitations). The server NEVER trusts
a tenant_id/role coming from the request itself — only from a token it
already knows about, validated server-side against this mapping.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from app.security.models import Role, UserContext

# Local-dev demo fixture — deliberately named so nobody mistakes these
# for real secrets (matches the docs/security.md convention of calling
# this out explicitly). A real deployment overrides this entirely via
# AUTH_TOKENS_JSON (see build_token_authenticator) rather than editing
# this dict — these exact tokens are also what tests exercise.
DEFAULT_DEV_TOKENS: dict[str, UserContext] = {
    "token-user-a": UserContext(
        user_id="user_a", tenant_id="tenant-a", roles=frozenset({Role.USER})
    ),
    "token-operator-a": UserContext(
        user_id="operator_a", tenant_id="tenant-a", roles=frozenset({Role.OPERATOR})
    ),
    "token-admin-a": UserContext(
        user_id="admin_a", tenant_id="tenant-a", roles=frozenset({Role.ADMIN})
    ),
    "token-user-b": UserContext(
        user_id="user_b", tenant_id="tenant-b", roles=frozenset({Role.USER})
    ),
    "token-operator-b": UserContext(
        user_id="operator_b", tenant_id="tenant-b", roles=frozenset({Role.OPERATOR})
    ),
}


class TokenAuthenticator:
    """Deliberately dumb: an in-memory dict lookup. Swappable later for
    a real JWT/OIDC verifier without touching any call site — every
    caller only ever sees `authenticate(token) -> UserContext | None`.
    """

    def __init__(self, tokens: dict[str, UserContext]):
        self._tokens = dict(tokens)

    def authenticate(self, token: str) -> UserContext | None:
        return self._tokens.get(token)


def _user_context_from_dict(token: str, data: object) -> UserContext:
    if not isinstance(data, Mapping):
        raise ValueError(f"AUTH_TOKENS_JSON entry {token!r} must be an object")

    missing = [field for field in ("user_id", "tenant_id", "roles") if field not in data]
    if missing:
        raise ValueError(
            f"AUTH_TOKENS_JSON entry {token!r} is missing required field(s): "
            f"{', '.join(missing)}"
        )

    user_id = data["user_id"]
    tenant_id = data["tenant_id"]
    roles = data["roles"]
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError(f"AUTH_TOKENS_JSON entry {token!r} requires a non-empty user_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError(f"AUTH_TOKENS_JSON entry {token!r} requires a non-empty tenant_id")
    if not isinstance(roles, list) or not roles:
        raise ValueError(f"AUTH_TOKENS_JSON entry {token!r} requires a non-empty roles list")

    try:
        parsed_roles = frozenset(Role(role) for role in roles)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"AUTH_TOKENS_JSON entry {token!r} contains an invalid role; "
            f"expected one of {[role.value for role in Role]}"
        ) from exc

    return UserContext(user_id=user_id, tenant_id=tenant_id, roles=parsed_roles)


def parse_auth_tokens(auth_tokens_json: str | None) -> dict[str, UserContext]:
    """Parse and validate the explicit token map, without environment policy."""
    if not auth_tokens_json or not auth_tokens_json.strip():
        return dict(DEFAULT_DEV_TOKENS)

    try:
        raw = json.loads(auth_tokens_json)
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_TOKENS_JSON must contain valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("AUTH_TOKENS_JSON must be a JSON object keyed by token")

    parsed: dict[str, UserContext] = {}
    for token, data in raw.items():
        if not isinstance(token, str) or not token.strip():
            raise ValueError("AUTH_TOKENS_JSON token keys must be non-empty strings")
        parsed[token] = _user_context_from_dict(token, data)
    if not parsed:
        raise ValueError("AUTH_TOKENS_JSON must contain at least one token")
    return parsed


def validate_auth_configuration(
    *, app_env: str, auth_enabled: bool, auth_tokens_json: str | None
) -> dict[str, UserContext]:
    """Enforce the environment boundary and return the server-owned token map."""
    if app_env == "production" and not auth_enabled:
        raise ValueError(
            "Production authentication must remain enabled. "
            "AUTH_ENABLED=false is development-only."
        )
    if app_env == "production" and (not auth_tokens_json or not auth_tokens_json.strip()):
        raise ValueError(
            "Production authentication requires explicit credentials/verifier configuration. "
            "Demo tokens are disabled."
        )
    return parse_auth_tokens(auth_tokens_json)


def build_token_authenticator(
    auth_tokens_json: str | None,
    *,
    app_env: str = "development",
    auth_enabled: bool = True,
) -> TokenAuthenticator:
    """Build the authenticator from validated, server-owned credentials."""
    tokens = validate_auth_configuration(
        app_env=app_env,
        auth_enabled=auth_enabled,
        auth_tokens_json=auth_tokens_json,
    )
    return TokenAuthenticator(tokens)
