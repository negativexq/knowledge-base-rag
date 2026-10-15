"""One pytest run at a time: two concurrent runs each load torch, the
reranker and the live models, and on a 16 GB machine that pushed the system
into heavy swap. The lock is advisory (flock), so it is released when the
holding process exits, even on a crash."""

import subprocess
import sys

from tests.run_lock import acquire_run_lock


def test_lock_is_granted_when_free_and_refused_while_held(tmp_path):
    lock_path = tmp_path / "pytest-run.lock"

    first = acquire_run_lock(lock_path)
    assert first is not None
    try:
        assert acquire_run_lock(lock_path) is None
    finally:
        first.close()

    again = acquire_run_lock(lock_path)
    assert again is not None
    again.close()


def test_lock_held_by_another_process_is_refused(tmp_path):
    lock_path = tmp_path / "pytest-run.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, sys, time\n"
            f"f = open({str(lock_path)!r}, 'w')\n"
            "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "print('held', flush=True)\n"
            "time.sleep(30)\n",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        assert acquire_run_lock(lock_path) is None
    finally:
        holder.kill()
        holder.wait()

    released = acquire_run_lock(lock_path)
    assert released is not None
    released.close()
