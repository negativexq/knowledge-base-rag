"""Locate the pinned RAGBench eManual parquet used by the benchmark harness.

Dataset acquisition is intentionally separate from a benchmark run.  The
runner consumes the pinned revision and never silently falls back to a
different dataset version.
"""

from __future__ import annotations

import os
from pathlib import Path

REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEFAULT_PATH = Path(
    f"/Users/ofk/.cache/huggingface/hub/datasets--galileo-ai--ragbench/"
    f"snapshots/{REVISION}/emanual/test-00000-of-00001.parquet"
)


def dataset_path() -> Path:
    path = Path(os.environ.get("RAGBENCH_EMANUAL_PARQUET", DEFAULT_PATH))
    if not path.is_file():
        raise FileNotFoundError(
            f"Pinned RAGBench eManual parquet is unavailable: {path}. "
            "Set RAGBENCH_EMANUAL_PARQUET to the same pinned revision."
        )
    return path
