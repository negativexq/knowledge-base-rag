"""Qwen-compatible token counting and character offset helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from transformers import AutoTokenizer


@lru_cache(maxsize=4)
def get_tokenizer(model: str, revision: str):
    """Load one configured tokenizer and reuse it across documents.

    The tokenizer is an ingestion/evaluation dependency, not an embedding
    provider.  Keeping the model and revision as arguments prevents a model
    name from being hidden in the chunking algorithm and makes both values
    fingerprintable.
    """

    return AutoTokenizer.from_pretrained(model, revision=revision, use_fast=True)


def token_offsets(text: str, model: str, revision: str) -> list[tuple[int, int]]:
    tokenizer = get_tokenizer(model, revision)
    encoded: dict[str, Any] = tokenizer(
        text, add_special_tokens=False, return_offsets_mapping=True
    )
    return [tuple(offset) for offset in encoded["offset_mapping"] if offset[1] > offset[0]]


def token_count(text: str, model: str, revision: str) -> int:
    return len(token_offsets(text, model, revision))
