"""Sprint 23: token -> UserContext mapping — a real trust boundary, not
a full OAuth/OIDC stack (out of scope for this local-first portfolio
repo; see docs/security.md's known limitations). The server NEVER trusts
a tenant_id/role coming from the request itself — only from a token it
already knows about, validated server-side against this mapping.
"""

from __future__ import annotations

import json

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


def _user_context_from_dict(data: dict) -> UserContext:
    return UserContext(
        user_id=data["user_id"],
        tenant_id=data["tenant_id"],
        roles=frozenset(Role(r) for r in data["roles"]),
    )


def build_token_authenticator(auth_tokens_json: str | None) -> TokenAuthenticator:
    """auth_tokens_json (Settings.auth_tokens_json) is an optional raw
    JSON string — `{"token-...": {"user_id":..., "tenant_id":...,
    "roles": ["USER"]}}` — for a real deployment to supply its OWN token
    set via env, completely replacing DEFAULT_DEV_TOKENS (not merging:
    a real deployment should never accidentally also accept the demo
    tokens). None (the default) uses DEFAULT_DEV_TOKENS, appropriate for
    local development only — see docs/security.md.
    """
    if not auth_tokens_json:
        return TokenAuthenticator(DEFAULT_DEV_TOKENS)
    raw = json.loads(auth_tokens_json)
    return TokenAuthenticator({token: _user_context_from_dict(data) for token, data in raw.items()})
