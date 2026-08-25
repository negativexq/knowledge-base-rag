"""Sprint 23: LOCAL DEV ONLY demo token selector for the Streamlit UI.

This UI is a local operator/demo tool, not a production frontend — there
is no login flow, no session cookie, no secret storage. The sidebar
selector below just lets a developer pick which of the well-known demo
tokens (app/security/auth.py::DEFAULT_DEV_TOKENS) the UI's own backend
requests carry, so the UI can exercise the real auth/RBAC boundary
instead of silently bypassing it. NEVER hardcode a real production
token/secret here — this module only ever knows about the demo fixture.
"""

# Streamlit is imported lazily inside each function, not at module level
# — app/ui/sources_client.py (imported by tests/test_sources_client.py
# in the main backend test suite/venv, which does NOT have streamlit
# installed; only the separate .venv-ui does, see docs/sprint-10-plan.md)
# needs auth_headers() importable without streamlit ever being present,
# as long as it's never actually CALLED outside the real Streamlit UI
# process.

# Label -> token, mirroring app/security/auth.py::DEFAULT_DEV_TOKENS
# exactly (kept as a literal copy, not an import, so this UI process —
# which runs in its own separate venv, .venv-ui — never needs the main
# app package importable to render its sidebar).
DEMO_TOKENS = {
    "tenant-a — user": "token-user-a",
    "tenant-a — operator": "token-operator-a",
    "tenant-a — admin": "token-admin-a",
    "tenant-b — user": "token-user-b",
    "tenant-b — operator": "token-operator-b",
}


def render_dev_token_selector() -> None:
    import streamlit as st

    st.sidebar.markdown("### 🔑 Dev identity (local only)")
    st.sidebar.caption(
        "Demo tokens only — never a real credential. Selects which "
        "tenant/role the backend sees for this UI session."
    )
    label = st.sidebar.selectbox("Acting as", list(DEMO_TOKENS.keys()))
    st.session_state["dev_token"] = DEMO_TOKENS[label]


def auth_headers() -> dict[str, str]:
    import streamlit as st

    token = st.session_state.get("dev_token")
    return {"Authorization": f"Bearer {token}"} if token else {}
