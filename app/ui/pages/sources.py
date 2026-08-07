"""Sources page: which connectors are configured, how many documents each
has ingested, and a manual "Sync now" trigger per connector. Deliberately
its own page (not a tab inside Chat) — st.tabs() renders every tab's
content eagerly on each script run, so an expensive action (a real sync,
Sprint 7's POST /sync/{source_type}) sitting inside a tab would fire real
work just from switching tabs elsewhere on the page. A page is only
rendered when navigated to.
"""

import streamlit as st

from app.ui.sources_client import fetch_sources, trigger_sync

st.title("🗂️ Sources")

sources = fetch_sources()

if not sources:
    st.info("No connectors configured.")

for source in sources:
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        st.subheader(source["source_type"])
    with col2:
        st.metric("Documents", source["document_count"])
    with col3:
        if source["is_running"]:
            st.info("Sync in progress…")
        elif st.button("Sync now", key=f"sync-{source['source_type']}"):
            with st.spinner(f"Syncing {source['source_type']}..."):
                result = trigger_sync(source["source_type"])
            if result.get("status") == "success":
                stats = result.get("stats") or {}
                st.success(
                    f"Processed {stats.get('files_processed', 0)}, "
                    f"skipped {stats.get('files_skipped', 0)}, "
                    f"deleted {stats.get('files_deleted', 0)}."
                )
            else:
                st.error(f"Sync failed: {result.get('error') or result}")
            st.rerun()
    st.divider()
