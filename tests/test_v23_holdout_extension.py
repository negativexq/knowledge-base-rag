import hashlib

from scripts.prepare_v23_holdout_extension import select_extension


def row(query_id, split="development", category="multi_document", sources=None):
    return {
        "id": query_id,
        "split": split,
        "category": category,
        "expected_source_ids": sources or ["s1", "s2"],
    }


def test_extension_selection_is_deterministic_and_excludes_initial_and_debug():
    dataset = [row("multi-00-0"), row("multi-03-3"), row("multi-00-1")]
    selected, eligible = select_extension(dataset, ["multi-00-0"], ["multi-00-1"])
    assert [item["id"] for item in eligible] == ["multi-03-3"]
    assert [item["id"] for item in selected] == ["multi-03-3"]


def test_extension_never_selects_calibration_or_frozen_queries():
    dataset = [row("cal", "calibration"), row("frozen", "frozen_test")]
    selected, eligible = select_extension(dataset, [], [])
    assert selected == []
    assert eligible == []


def test_extension_selection_order_uses_sha256_query_id():
    dataset = [row("multi-a"), row("multi-b")]
    selected, _ = select_extension(dataset, [], [])
    assert [item["id"] for item in selected] == sorted(
        ["multi-a", "multi-b"], key=lambda value: hashlib.sha256(value.encode()).hexdigest()
    )
