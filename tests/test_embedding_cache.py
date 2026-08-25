import pytest

from app.evaluation.embedding_cache import EmbeddingCache, StaleCacheError, cache_key


def test_cache_key_is_deterministic():
    a = cache_key("m", "r", 768, "instr", "query text", "fp1")
    b = cache_key("m", "r", 768, "instr", "query text", "fp1")

    assert a == b


def test_cache_key_changes_when_model_changes():
    a = cache_key("model-a", "r", 768, "instr", "q", "fp1")
    b = cache_key("model-b", "r", 768, "instr", "q", "fp1")

    assert a != b


def test_cache_key_changes_when_dimension_changes():
    a = cache_key("m", "r", 768, "instr", "q", "fp1")
    b = cache_key("m", "r", 1024, "instr", "q", "fp1")

    assert a != b


def test_cache_key_changes_when_instruction_changes():
    a = cache_key("m", "r", 768, "Instruct: A\nQuery: ", "q", "fp1")
    b = cache_key("m", "r", 768, "Instruct: B\nQuery: ", "q", "fp1")

    assert a != b


def test_cache_key_changes_when_query_text_changes():
    a = cache_key("m", "r", 768, "instr", "query one", "fp1")
    b = cache_key("m", "r", 768, "instr", "query two", "fp1")

    assert a != b


def test_cache_key_changes_when_fingerprint_changes():
    a = cache_key("m", "r", 768, "instr", "q", "fp1")
    b = cache_key("m", "r", 768, "instr", "q", "fp2")

    assert a != b


def test_cache_put_and_get_round_trip(tmp_path):
    cache = EmbeddingCache(tmp_path / "cache.json")
    key = cache_key("m", "r", 768, "instr", "q", "fp1")

    cache.put(key, [0.1, 0.2, 0.3], fingerprint="fp1")

    assert cache.get(key, expected_fingerprint="fp1") == [0.1, 0.2, 0.3]


def test_cache_get_returns_none_for_missing_key(tmp_path):
    cache = EmbeddingCache(tmp_path / "cache.json")

    assert cache.get("nonexistent", expected_fingerprint="fp1") is None


def test_cache_get_raises_stale_cache_error_on_fingerprint_mismatch(tmp_path):
    """The core Sprint 21 rule: a stale cache must never be silently
    reused — a frozen-mode run against embeddings computed under a
    different pipeline fingerprint would measure nothing real.
    """
    cache = EmbeddingCache(tmp_path / "cache.json")
    key = cache_key("m", "r", 768, "instr", "q", "fp1")
    cache.put(key, [0.1, 0.2], fingerprint="fp1")

    with pytest.raises(StaleCacheError, match="stale"):
        cache.get(key, expected_fingerprint="fp2")


def test_cache_persists_to_disk_and_reloads(tmp_path):
    path = tmp_path / "cache.json"
    cache = EmbeddingCache(path)
    key = cache_key("m", "r", 768, "instr", "q", "fp1")
    cache.put(key, [0.5, 0.6], fingerprint="fp1")
    cache.save()

    reloaded = EmbeddingCache(path)

    assert reloaded.get(key, expected_fingerprint="fp1") == [0.5, 0.6]
    assert len(reloaded) == 1


def test_cache_contains_reflects_put_entries(tmp_path):
    cache = EmbeddingCache(tmp_path / "cache.json")
    key = cache_key("m", "r", 768, "instr", "q", "fp1")

    assert key not in cache

    cache.put(key, [0.1], fingerprint="fp1")

    assert key in cache


def test_cache_loading_a_nonexistent_file_starts_empty(tmp_path):
    cache = EmbeddingCache(tmp_path / "does_not_exist.json")

    assert len(cache) == 0
