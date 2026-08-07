"""Multi-page Streamlit UI entrypoint: Chat, Sources, Sync Status. Runs on
the host, in its own venv (.venv-ui) — see docs/sprint-10-plan.md for why
(a real starlette version conflict between streamlit and this project's
fastapi pin, verified with `pip install`, not assumed).

Run with: make ui   (equivalent to `streamlit run app/ui/streamlit_app.py`)
"""

import streamlit as st

st.set_page_config(page_title="Knowledge Base RAG", page_icon="📚", layout="wide")

pages = st.navigation(
    [
        st.Page("pages/chat.py", title="Chat", icon="💬"),
        st.Page("pages/sources.py", title="Sources", icon="🗂️"),
        st.Page("pages/sync_status.py", title="Sync Status", icon="🔄"),
    ]
)
pages.run()
