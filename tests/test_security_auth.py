import json

from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator, build_token_authenticator
from app.security.models import Role


def test_default_dev_tokens_cover_both_tenants_and_all_three_roles():
    roles_seen = {user.roles for user in DEFAULT_DEV_TOKENS.values()}
    tenants_seen = {user.tenant_id for user in DEFAULT_DEV_TOKENS.values()}

    assert frozenset({Role.USER}) in roles_seen
    assert frozenset({Role.OPERATOR}) in roles_seen
    assert frozenset({Role.ADMIN}) in roles_seen
    assert tenants_seen == {"tenant-a", "tenant-b"}


def test_token_authenticator_resolves_a_known_token():
    authenticator = TokenAuthenticator(DEFAULT_DEV_TOKENS)

    user = authenticator.authenticate("token-user-a")

    assert user is not None
    assert user.tenant_id == "tenant-a"
    assert user.roles == frozenset({Role.USER})


def test_token_authenticator_returns_none_for_an_unknown_token():
    authenticator = TokenAuthenticator(DEFAULT_DEV_TOKENS)

    assert authenticator.authenticate("not-a-real-token") is None


def test_build_token_authenticator_uses_dev_tokens_when_none_given():
    authenticator = build_token_authenticator(None)

    assert authenticator.authenticate("token-user-a") is not None


def test_build_token_authenticator_replaces_dev_tokens_entirely_when_json_given():
    """A real deployment's AUTH_TOKENS_JSON must fully replace the demo
    fixture, not merge with it — otherwise the demo tokens would remain
    valid in production.
    """
    custom = json.dumps(
        {"prod-token-1": {"user_id": "real_user", "tenant_id": "real-tenant", "roles": ["ADMIN"]}}
    )

    authenticator = build_token_authenticator(custom)

    assert authenticator.authenticate("prod-token-1").tenant_id == "real-tenant"
    assert authenticator.authenticate("token-user-a") is None  # demo token no longer valid


def test_build_token_authenticator_parses_multiple_roles():
    custom = json.dumps(
        {"t": {"user_id": "u", "tenant_id": "x", "roles": ["USER", "OPERATOR"]}}
    )

    user = build_token_authenticator(custom).authenticate("t")

    assert user.roles == frozenset({Role.USER, Role.OPERATOR})
