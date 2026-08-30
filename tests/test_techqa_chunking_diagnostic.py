from __future__ import annotations

import pytest


def test_chunking_grid_declares_only_the_preregistered_cells() -> None:
    from scripts.run_techqa_chunking_diagnostic import GRID

    assert [(item["target_tokens"], item["overlap_tokens"]) for item in GRID] == [
        (500, 50),
        (500, 150),
        (500, 250),
        (800, 50),
        (800, 150),
        (800, 250),
        (1200, 50),
        (1200, 150),
        (1200, 250),
    ]


def test_invalid_overlap_is_rejected() -> None:
    from scripts.run_techqa_chunking_diagnostic import grid_config

    with pytest.raises(ValueError, match="overlap"):
        grid_config(500, 500)
