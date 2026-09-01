from scripts.benchmarks.ragbench_emanual_common import (
    canonical_hash,
    choose_sample,
    normalize_text,
    token_f1,
)


def test_ragbench_sample_is_deterministic():
    rows = [{"id": f"q-{index}", "question": str(index)} for index in range(132)]
    first = [row["id"] for row in choose_sample(rows)]
    second = [row["id"] for row in choose_sample(rows)]
    assert first == second
    assert len(first) == 50
    assert len(set(first)) == 50


def test_reference_normalization_and_token_f1_are_deterministic():
    assert normalize_text("  A\u00a0b! ") == "a b!"
    assert token_f1("alpha beta", "beta alpha") == 1.0
    assert token_f1("alpha", "beta") == 0.0


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": [2]}) == canonical_hash({"b": [2], "a": 1})
