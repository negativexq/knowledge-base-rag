"""Sprint 22: retrieval quality validation for a migration target
collection — structural validation alone (right dimension, right counts)
proves the index was BUILT correctly, not that it actually RETRIEVES
well. This reuses the exact Sprint 18-21 golden-set benchmark machinery
(app/evaluation/rank_metrics.py, the frozen 220-question
tests/fixtures/embedding_benchmark_golden_v2.json dataset) against the
already-indexed migration target collection — it does NOT re-index
anything itself.

Two distinct gates, matching the Sprint 22 spec:
  - run_quality_gate(): the full 220-question benchmark, required once
    before activation (expensive, ~minutes).
  - run_smoke(): a small (~15-20 question) stratified sample covering
    every language-pair cell plus not-found, cheap enough to run again
    AFTER the alias switch as a fast operational sanity check.
"""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient

from app.evaluation.dataset_fingerprint import golden_set_fingerprint
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.llm.citation_location import location_for
from app.llm.embedding_models import EmbeddingModelConfig
from app.llm.ollama_client import OllamaClient
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder

CROSS_LINGUAL_CELLS = ["tr_query_en_content", "en_query_tr_content"]
MONO_LINGUAL_CELLS = ["tr_query_tr_content", "en_query_en_content"]

# Sprint 22: how far a real post-migration measurement of the SAME
# config (qwen3-4b@1024) against the SAME frozen golden set may drift
# from Sprint 21's own accepted numbers before it's treated as a real
# regression rather than ordinary run-to-run noise. Sprint 21 measured
# run-to-run stddev of 0.0000 across 10 live runs for both configs
# (artifacts/embedding-benchmark-sprint21/report.md) — this tolerance is
# deliberately small and pre-committed, not tuned after seeing this
# sprint's result.
DEFAULT_TOLERANCE = 0.03


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    cross_recall_at_5: float
    cross_mrr: float
    mono_recall_at_5: float
    ndcg_at_5: float
    baseline_cross_recall_at_5: float | None
    baseline_cross_mrr: float | None
    baseline_mono_recall_at_5: float | None
    tolerance: float
    question_count: int
    dataset_fingerprint: str
    failure_reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "cross_recall_at_5": self.cross_recall_at_5,
            "cross_mrr": self.cross_mrr,
            "mono_recall_at_5": self.mono_recall_at_5,
            "ndcg_at_5": self.ndcg_at_5,
            "baseline_cross_recall_at_5": self.baseline_cross_recall_at_5,
            "baseline_cross_mrr": self.baseline_cross_mrr,
            "baseline_mono_recall_at_5": self.baseline_mono_recall_at_5,
            "tolerance": self.tolerance,
            "question_count": self.question_count,
            "dataset_fingerprint": self.dataset_fingerprint,
            "failure_reasons": self.failure_reasons,
        }


async def _run_questions(
    questions: list[dict],
    ollama: OllamaClient,
    sparse_encoder: SparseEncoder,
    qdrant_client: QdrantClient,
    collection_name: str,
    config: EmbeddingModelConfig,
) -> dict:
    per_cell: dict[tuple[str, str], list] = {}
    all_metrics = []
    not_found_hits = 0
    not_found_total = 0

    for question in questions:
        query = question["query"]
        expected_locations: list[Location] = [tuple(loc) for loc in question["expected_locations"]]
        is_not_found = question.get("expect_not_found", False)

        results = await search(
            query, ollama, sparse_encoder, qdrant_client, collection_name, config.ollama_model,
            reranker=None,
            query_prefix=config.query_prefix(),
            dimensions=config.output_dimension,
        )

        if is_not_found:
            not_found_total += 1
            if not results:
                not_found_hits += 1
            continue

        ranked_locations = [
            (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
            for r in results
        ]
        metrics = compute_rank_metrics(ranked_locations, expected_locations)
        all_metrics.append(metrics)
        cell = (question["query_lang"], question["content_lang"])
        per_cell.setdefault(cell, []).append(metrics)

    by_cell = {
        f"{q}_query_{c}_content": aggregate_rank_metrics(m) for (q, c), m in per_cell.items()
    }

    def cell_mean(cells: list[str], key: str) -> float:
        values = [by_cell[c][key] for c in cells if c in by_cell]
        return sum(values) / len(values) if values else 0.0

    return {
        "overall": aggregate_rank_metrics(all_metrics),
        "cross_recall_at_5": cell_mean(CROSS_LINGUAL_CELLS, "recall_at_5"),
        "cross_mrr": cell_mean(CROSS_LINGUAL_CELLS, "mrr"),
        "mono_recall_at_5": cell_mean(MONO_LINGUAL_CELLS, "recall_at_5"),
        "not_found_accuracy": not_found_hits / not_found_total if not_found_total else None,
    }


async def run_quality_gate(
    golden_questions: list[dict],
    ollama: OllamaClient,
    sparse_encoder: SparseEncoder,
    qdrant_client: QdrantClient,
    collection_name: str,
    config: EmbeddingModelConfig,
    baseline: dict | None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> QualityGateResult:
    """baseline is Sprint 21's accepted production-candidate numbers for
    this exact config (e.g. artifacts/embedding-benchmark-sprint21/
    results.json's qwen3-4b@1024 entry) — None means "no baseline
    available," in which case the gate can only report numbers, not
    compare them (still recorded as passed=True, but callers should treat
    a missing baseline as a real limitation, not silent success — see
    docs/embedding-migration.md).
    """
    result = await _run_questions(
        golden_questions, ollama, sparse_encoder, qdrant_client, collection_name, config
    )

    failure_reasons: list[str] = []
    baseline_cross = baseline.get("cross_lingual", {}) if baseline else {}
    baseline_mono = baseline.get("mono_lingual", {}) if baseline else {}
    baseline_cross_recall = baseline_cross.get("recall_at_5") if baseline else None
    baseline_cross_mrr = baseline_cross.get("mrr") if baseline else None
    baseline_mono_recall = baseline_mono.get("recall_at_5") if baseline else None

    if baseline_cross_recall is not None:
        floor = baseline_cross_recall - tolerance
        if result["cross_recall_at_5"] < floor:
            failure_reasons.append(
                f"cross-lingual recall@5 {result['cross_recall_at_5']:.4f} is below baseline "
                f"{baseline_cross_recall:.4f} - tolerance {tolerance}"
            )
    if baseline_cross_mrr is not None:
        floor = baseline_cross_mrr - tolerance
        if result["cross_mrr"] < floor:
            failure_reasons.append(
                f"cross-lingual MRR {result['cross_mrr']:.4f} is below baseline "
                f"{baseline_cross_mrr:.4f} - tolerance {tolerance}"
            )
    if baseline_mono_recall is not None:
        floor = baseline_mono_recall - tolerance
        if result["mono_recall_at_5"] < floor:
            failure_reasons.append(
                f"mono-lingual recall@5 {result['mono_recall_at_5']:.4f} is below baseline "
                f"{baseline_mono_recall:.4f} - tolerance {tolerance}"
            )

    return QualityGateResult(
        passed=not failure_reasons,
        cross_recall_at_5=result["cross_recall_at_5"],
        cross_mrr=result["cross_mrr"],
        mono_recall_at_5=result["mono_recall_at_5"],
        ndcg_at_5=result["overall"]["ndcg_at_5"],
        baseline_cross_recall_at_5=baseline_cross_recall,
        baseline_cross_mrr=baseline_cross_mrr,
        baseline_mono_recall_at_5=baseline_mono_recall,
        tolerance=tolerance,
        question_count=len(golden_questions),
        dataset_fingerprint=golden_set_fingerprint(golden_questions),
        failure_reasons=failure_reasons,
    )


@dataclass(frozen=True)
class SmokeResult:
    passed: bool
    question_count: int
    hit_count: int
    hit_rate: float
    min_hit_rate: float
    errors: list[str]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "question_count": self.question_count,
            "hit_count": self.hit_count,
            "hit_rate": self.hit_rate,
            "min_hit_rate": self.min_hit_rate,
            "errors": self.errors,
        }


async def run_smoke(
    smoke_questions: list[dict],
    ollama: OllamaClient,
    sparse_encoder: SparseEncoder,
    qdrant_client: QdrantClient,
    collection_name: str,
    config: EmbeddingModelConfig,
    min_hit_rate: float = 0.6,
) -> SmokeResult:
    """Fast operational sanity check — NOT a replacement for the full
    quality gate (see module docstring). A "hit" is: for a normal
    question, at least one expected location appears in the top 5; for a
    not-found question, the top 5 is empty or doesn't spuriously match.
    Cheap enough to run again immediately after the alias switch
    (post-switch verification, Sprint 22 section 17) as well as before
    activation.
    """
    hits = 0
    errors: list[str] = []
    for question in smoke_questions:
        try:
            results = await search(
                question["query"], ollama, sparse_encoder, qdrant_client, collection_name,
                config.ollama_model, reranker=None, query_prefix=config.query_prefix(),
                dimensions=config.output_dimension,
            )
        except Exception as exc:  # noqa: BLE001 - any failure here is a real smoke failure
            errors.append(f"{question['id']}: {exc}")
            continue

        if question.get("expect_not_found", False):
            if not results:
                hits += 1
            continue

        expected = {tuple(loc) for loc in question["expected_locations"]}
        ranked = {
            (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
            for r in results
        }
        if expected & ranked:
            hits += 1

    hit_rate = hits / len(smoke_questions) if smoke_questions else 0.0
    return SmokeResult(
        passed=not errors and hit_rate >= min_hit_rate,
        question_count=len(smoke_questions),
        hit_count=hits,
        hit_rate=hit_rate,
        min_hit_rate=min_hit_rate,
        errors=errors,
    )
