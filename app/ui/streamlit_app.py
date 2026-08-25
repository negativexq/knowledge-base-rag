"""Multi-page Streamlit UI entrypoint: Chat, Sources, Sync Status. Runs on
the host, in its own venv (.venv-ui) — see docs/sprint-10-plan.md for why
(a real starlette version conflict between streamlit and this project's
fastapi pin, verified with `pip install`, not assumed).

Run with: make ui   (equivalent to `streamlit run app/ui/streamlit_app.py`)
"""

import streamlit as st

from app.ui.dev_auth import render_dev_token_selector

st.set_page_config(page_title="Knowledge Base RAG", page_icon="📚", layout="wide")

# Sprint 23: the backend now enforces auth/RBAC on /chat, /sources, and
# /sync/* — this UI must send a real (demo) bearer token or every page
# gets 401s. See app/ui/dev_auth.py; this selector is LOCAL DEV ONLY.
render_dev_token_selector()

pages = st.navigation(
    [
        st.Page("pages/chat.py", title="Chat", icon="💬"),
        st.Page("pages/sources.py", title="Sources", icon="🗂️"),
        st.Page("pages/sync_status.py", title="Sync Status", icon="🔄"),
    ]
)
pages.run()
