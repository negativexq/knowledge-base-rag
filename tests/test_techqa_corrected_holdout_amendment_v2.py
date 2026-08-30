from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.create_techqa_corrected_holdout_amendment_v2 import (
    SIDECAR,
    TARGET,
    V1,
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


def test_v1_is_not_overwritten_by_v2_artifact() -> None:
    assert TARGET.exists()
    assert SIDECAR.exists()
    assert len(V1.read_text(encoding="utf-8")) > 0
    value = json.loads(TARGET.read_text(encoding="utf-8"))
    assert value["amendment_version"] == 2
    assert value["supersedes"].endswith("preregistration-amendment-v1.json")
