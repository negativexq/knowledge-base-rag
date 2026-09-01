from __future__ import annotations

from pathlib import Path

import pytest

from scripts.operations.create_techqa_corrected_holdout_amendment_v2 import (
    write_once_bytes,
    writer_self_test,
)


def test_write_once_fails_closed_on_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "amendment.json"
    write_once_bytes(target, b"first")
    with pytest.raises(FileExistsError):
        write_once_bytes(target, b"second")
    assert target.read_bytes() == b"first"


def test_v2_writer_self_test() -> None:
    result = writer_self_test()
    assert result == {"write_once": True, "second_create_error": "AMENDMENT_V2_ALREADY_EXISTS"}
