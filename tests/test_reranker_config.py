import pytest

from app.reranker.config import (
    EXISTING_RERANKER_MODEL,
    MULTILINGUAL_RERANKER_MODEL,
    benchmark_config,
)
from app.reranker.cross_encoder import CrossEncoderReranker
from app.shared.config import Settings
from scripts.benchmarks.benchmark_rerankers import classify_case


def test_benchmark_configs_are_explicit_and_keep_candidate_contract():
    assert benchmark_config("off").enabled is False
    assert benchmark_config("existing").model == EXISTING_RERANKER_MODEL
    multilingual = benchmark_config("multilingual")
    assert multilingual.model == MULTILINGUAL_RERANKER_MODEL
    assert (multilingual.candidate_k, multilingual.top_n) == (20, 5)


def test_runtime_profiles_keep_local_and_reference_candidate_budgets_distinct():
    config = Settings(_env_file=None)
    assert config.reranker_enabled is True
    assert config.reranker_model == MULTILINGUAL_RERANKER_MODEL
    assert config.reranker_candidate_k == 15
    assert config.reranker_top_n == 5
    assert Settings.benchmark_reference().reranker_candidate_k == 20


def test_reranker_can_be_disabled_without_constructing_model(monkeypatch):
    import app.wiring as wiring

    monkeypatch.setattr(
        wiring, "CrossEncoderReranker", lambda *args, **kwargs: pytest.fail("model constructed")
    )
    assert wiring.build_reranker(Settings(_env_file=None, reranker_enabled=False)) is None


def test_cross_encoder_config_is_forwarded(monkeypatch):
    import app.reranker.cross_encoder as module

    captured = {}

    class FakeCrossEncoder:
        def __init__(self, model, **kwargs):
            captured.update(model=model, kwargs=kwargs)

    monkeypatch.setattr(module, "CrossEncoder", FakeCrossEncoder)
    CrossEncoderReranker("candidate-model", trust_remote_code=True, device="cpu")
    assert captured == {
        "model": "candidate-model",
        "kwargs": {"trust_remote_code": True, "device": "cpu"},
    }


def test_rescue_drop_classification_is_deterministic():
    assert classify_case(8, 3) == "rescued"
    assert classify_case(3, None) == "dropped_out_of_top5"
    assert classify_case(3, 4) == "degraded"
    assert classify_case(3, 3) == "unchanged"


@pytest.mark.parametrize(("device", "expected"), [(None, None), ("mps", "mps")])
def test_the_reranker_device_is_configurable(monkeypatch, device, expected):
    # Docker on macOS has no Metal; a host run can put the cross-encoder on
    # the Apple GPU (about 2.7x faster than CPU in a 15-candidate timing).
    import app.wiring as wiring

    captured = {}
    monkeypatch.setattr(
        wiring, "CrossEncoderReranker", lambda *args, **kwargs: captured.update(kwargs)
    )

    wiring.build_reranker(Settings(_env_file=None, reranker_device=device))

    assert captured["device"] == expected


def test_the_reranker_batch_size_reaches_the_model(monkeypatch):
    # Attention memory grows with batch x length^2; all 15 candidates in one
    # batch padded towards max_length 8192 pushed a 16 GB Mac into swap.
    import app.reranker.cross_encoder as cross_encoder
    import app.wiring as wiring
    from app.retrieval.hybrid_search import SearchResult

    calls = []

    class _Model:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs, **kwargs):
            calls.append(kwargs)
            return [0.0] * len(pairs)

    monkeypatch.setattr(cross_encoder, "CrossEncoder", _Model)
    reranker = wiring.build_reranker(Settings(_env_file=None, reranker_batch_size=4))
    reranker.rerank("q", [SearchResult(score=1.0, id="c", payload={"text": "t"})], top_n=1)

    assert calls == [{"batch_size": 4}]


def test_the_default_batch_size_is_two_pairs(monkeypatch):
    # The library sorts pairs by length, then pads each batch to its longest
    # pair. With 15 candidates of very different lengths, batches of 2 halved
    # rerank time on 120 recorded searches with identical rankings
    # (artifacts/reranker-batch-size-20261023/REPORT.md).
    import app.reranker.cross_encoder as cross_encoder
    import app.wiring as wiring
    from app.retrieval.hybrid_search import SearchResult

    calls = []

    class _Model:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs, **kwargs):
            calls.append(kwargs)
            return [0.0] * len(pairs)

    monkeypatch.setattr(cross_encoder, "CrossEncoder", _Model)
    reranker = wiring.build_reranker(Settings(_env_file=None))
    reranker.rerank("q", [SearchResult(score=1.0, id="c", payload={"text": "t"})], top_n=1)

    assert calls == [{"batch_size": 2}]
