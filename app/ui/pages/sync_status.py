"""Sync Status page: per-connector run history (Sprint 7/8's sync_runs
table) — start/finish times, success/error, file counts, and a Jaeger
link built from each run's trace_id.
"""

import os

import pandas as pd
import streamlit as st

from app.ui.sources_client import fetch_sources, fetch_sync_history

JAEGER_URL = os.environ.get("JAEGER_URL", "http://localhost:16686")

st.title("🔄 Sync Status")

sources = fetch_sources()

if not sources:
    st.info("No connectors configured.")

for source in sources:
    source_type = source["source_type"]
    st.subheader(source_type)

    runs = fetch_sync_history(source_type)
    if not runs:
        st.caption("No sync runs recorded yet.")
        st.divider()
        continue

    rows = []
    for run in runs:
        rows.append(
            {
                "started_at": run["started_at"],
                "status": run["status"],
                "trigger": run["trigger"],
                "files_processed": run["files_processed"],
                "files_skipped": run["files_skipped"],
                "files_deleted": run["files_deleted"],
                "chunks_upserted": run["chunks_upserted"],
                "trace": (
                    f"{JAEGER_URL}/trace/{run['trace_id']}" if run.get("trace_id") else None
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        column_config={
            "trace": st.column_config.LinkColumn("Trace", display_text="Open in Jaeger")
        },
        hide_index=True,
    )
    st.divider()
