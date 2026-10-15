"""An advisory, process-wide lock that keeps pytest runs from overlapping.
See tests/conftest.py::pytest_configure."""

import fcntl
from pathlib import Path
from typing import IO


def acquire_run_lock(path: Path) -> IO[str] | None:
    """Return the open, locked file, or None when another holder has it.
    Keep the returned file open for as long as the lock should be held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle
