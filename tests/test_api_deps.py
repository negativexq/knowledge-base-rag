from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, require_role
from app.security.auth import DEFAULT_DEV_TOKENS, TokenAuthenticator
from app.security.models import Role, UserContext


def _app(auth_enabled: bool = True) -> FastAPI:
    app = FastAPI()
    app.state.token_authenticator = TokenAuthenticator(DEFAULT_DEV_TOKENS)
    app.state.auth_enabled = auth_enabled

    @app.get("/whoami")
    def whoami(user: UserContext = Depends(get_current_user)):
        return {"user_id": user.user_id, "tenant_id": user.tenant_id}

    @app.post("/operator-only")
    def operator_only(user: UserContext = Depends(require_role(Role.OPERATOR))):
        return {"user_id": user.user_id}

    return app


def test_missing_credentials_returns_401():
    client = TestClient(_app())

    response = client.get("/whoami")

    assert response.status_code == 401


def test_invalid_token_returns_401():
    client = TestClient(_app())

    response = client.get("/whoami", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_malformed_authorization_header_returns_401():
    client = TestClient(_app())

    response = client.get("/whoami", headers={"Authorization": "not-bearer-format"})

    assert response.status_code == 401


def test_valid_token_resolves_a_real_user_context():
    client = TestClient(_app())

    response = client.get("/whoami", headers={"Authorization": "Bearer token-user-a"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_a", "tenant_id": "tenant-a"}


def test_user_role_is_forbidden_from_an_operator_endpoint():
    client = TestClient(_app())

    response = client.post(
        "/operator-only", headers={"Authorization": "Bearer token-user-a"}
    )

    assert response.status_code == 403


def test_operator_role_is_allowed_on_an_operator_endpoint():
    client = TestClient(_app())

    response = client.post(
        "/operator-only", headers={"Authorization": "Bearer token-operator-a"}
    )

    assert response.status_code == 200


def test_admin_role_is_also_allowed_on_an_operator_endpoint():
    """Role hierarchy: ADMIN satisfies an OPERATOR+ requirement."""
    client = TestClient(_app())

    response = client.post(
        "/operator-only", headers={"Authorization": "Bearer token-admin-a"}
    )

    assert response.status_code == 200


def test_missing_credentials_on_a_role_gated_endpoint_is_401_not_403():
    client = TestClient(_app())

    response = client.post("/operator-only")

    assert response.status_code == 401


def test_auth_disabled_bypasses_token_check_with_a_loud_local_dev_identity():
    client = TestClient(_app(auth_enabled=False))

    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "local-dev"


def test_no_authenticator_configured_returns_401_not_a_crash():
    app = FastAPI()
    app.state.auth_enabled = True

    @app.get("/whoami")
    def whoami(user: UserContext = Depends(get_current_user)):
        return {"user_id": user.user_id}

    client = TestClient(app)
    response = client.get("/whoami", headers={"Authorization": "Bearer token-user-a"})

    assert response.status_code == 401
