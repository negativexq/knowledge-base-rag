"""Sprint 26: controlled multilingual reranker benchmark.

The script keeps the Sprint 22 production embedding, BM25, RRF, corpus,
filters, and candidate/output sizes fixed. Only reranker configuration
changes. It uses a dedicated Qdrant collection and never mutates the
production collection.

Example:
    python -m scripts.benchmark_rerankers --output artifacts/reranker-benchmark-sprint26
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.bootstrap import paired_bootstrap_ci
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.citation_location import location_for
from app.llm.embedding_models import qwen3_4b_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.reranker.config import RERANKER_CANDIDATE_K, RERANKER_TOP_N, benchmark_config
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import settings
from scripts.benchmark_embeddings import SPRINT20_GOLDEN_SET, build_corpus

DEFAULT_DATASET = SPRINT20_GOLDEN_SET
DEFAULT_OUTPUT = "artifacts/reranker-benchmark-sprint26"
DEFAULT_WORK_DIR = "artifacts/reranker-benchmark-sprint26/work"
DEFAULT_COLLECTION = "kb_reranker_benchmark_qwen3_4b_1024"
CONFIG_NAMES = ("off", "existing", "multilingual")
BOOTSTRAP_SEED = 2601
BOOTSTRAP_ITERATIONS = 5000
MAX_ACCEPTABLE_TOTAL_RETRIEVAL_P95_MS = 3000
PAIR_NAMES = ("off_vs_existing", "off_vs_multilingual", "existing_vs_multilingual")
CELLS = (
    "tr_query_tr_content",
    "en_query_en_content",
    "tr_query_en_content",
    "en_query_tr_content",
)
CROSS_CELLS = ("tr_query_en_content", "en_query_tr_content")
MONO_CELLS = ("tr_query_tr_content", "en_query_en_content")


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, round((pct / 100) * (len(values) - 1)))
    return round(values[index], 3)


def locations(results) -> list[Location]:
    return [
        (result.payload["source_type"], result.payload["source_id"], location_for(result.payload))
        for result in results
    ]


def expected_rank(ranked: list[Location], expected: list[Location]) -> int | None:
    expected_set = set(expected)
    for rank, location in enumerate(ranked, start=1):
        if location in expected_set:
            return rank
    return None


def classify_case(before: int | None, after: int | None) -> str:
    if after is None:
        return "dropped_out_of_top5"
    if before is None or before > 5:
        return "rescued"
    if after < before:
        return "rescued"
    if after > before:
        return "degraded"
    return "unchanged"


def metric_dict(metrics) -> dict[str, float]:
    return {
        "recall_at_1": metrics.recall_at_1,
        "recall_at_3": metrics.recall_at_3,
        "recall_at_5": metrics.recall_at_5,
        "mrr": metrics.reciprocal_rank,
        "ndcg_at_5": metrics.ndcg_at_5,
    }


def aggregate_per_question(records: list[dict]) -> tuple[dict, dict[str, dict]]:
    per_cell: dict[str, list] = defaultdict(list)
    all_metrics = []
    per_question: dict[str, dict] = {}
    for record in records:
        if record["expect_not_found"]:
            continue
        metrics = compute_rank_metrics(record["ranked_locations"], record["expected_locations"])
        all_metrics.append(metrics)
        per_cell[record["cell"]].append(metrics)
        per_question[record["query_id"]] = metric_dict(metrics)
    by_cell = {
        cell: aggregate_rank_metrics(per_cell[cell]) | {"question_count": len(per_cell[cell])}
        for cell in CELLS
    }
    return (
        aggregate_rank_metrics(all_metrics) | {"question_count": len(all_metrics)},
        by_cell,
        per_question,
    )


async def ensure_index(
    qdrant: QdrantClient, collection: str, work_dir: Path, rebuild: bool
) -> dict:
    config = qwen3_4b_config(settings)
    docs_dir = work_dir / "corpus"
    build_corpus(docs_dir)
    if qdrant.collection_exists(collection) and not rebuild:
        info = qdrant.get_collection(collection)
        if info.points_count == 51:
            return {"collection": collection, "reused": True, "points": info.points_count}
        raise RuntimeError(
            f"benchmark collection {collection!r} has {info.points_count} points; "
            "use --rebuild-index to replace it"
        )
    if qdrant.collection_exists(collection):
        qdrant.delete_collection(collection)
    registry_path = work_dir / "registry.db"
    if registry_path.exists():
        registry_path.unlink()
    store = QdrantStore(qdrant, collection, dense_dimension=config.dimension)
    registry = DocumentRegistry(registry_path)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()

    async def embed(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=config.ollama_model,
            prefix=config.document_prefix(),
            dimensions=config.output_dimension,
        )

    started = time.perf_counter()
    stats = await ingest_connector(
        LocalFilesystemConnector(str(docs_dir)),
        store,
        registry,
        embed,
        sparse,
        pipeline_fingerprint=build_pipeline_fingerprint(config),
    )
    await ollama.aclose()
    return {
        "collection": collection,
        "reused": False,
        "points": stats.chunks_upserted,
        "index_seconds": round(time.perf_counter() - started, 3),
    }


async def run_config(
    name: str, questions: list[dict], qdrant: QdrantClient, collection: str
) -> tuple[dict, list[dict]]:
    config = benchmark_config(name)
    embed_config = qwen3_4b_config(settings)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()
    reranker = None
    load_start = time.perf_counter()
    if config.enabled:
        reranker = CrossEncoderReranker(
            config.model,
            trust_remote_code=config.trust_remote_code,
            device="cpu",
        )
    load_seconds = time.perf_counter() - load_start if config.enabled else None
    for _ in range(2):
        await ollama.embed(
            "warmup query",
            model=embed_config.ollama_model,
            prefix=embed_config.query_prefix(),
            dimensions=embed_config.output_dimension,
        )
    records: list[dict] = []
    rerank_times: list[float] = []
    total_times: list[float] = []
    query_embed_times: list[float] = []
    for question in questions:
        expected = [tuple(location) for location in question["expected_locations"]]
        query_started = time.perf_counter()
        embed_started = time.perf_counter()
        # search() performs the production Qwen + BM25 + Qdrant RRF path.
        # Asking for top_k=20/top_n=20 exposes the same pre-rerank candidate
        # set without changing production behavior.
        candidates = await search(
            question["query"],
            ollama,
            sparse,
            qdrant,
            collection,
            embed_config.ollama_model,
            RetrievalContext.system(),
            reranker=None,
            top_k=RERANKER_CANDIDATE_K,
            top_n=RERANKER_CANDIDATE_K,
            query_prefix=embed_config.query_prefix(),
            dimensions=embed_config.output_dimension,
        )
        query_embed_times.append((time.perf_counter() - embed_started) * 1000)
        before_locations = locations(candidates)
        rerank_started = time.perf_counter()
        if reranker is None:
            results = candidates[:RERANKER_TOP_N]
        else:
            results = reranker.rerank(question["query"], candidates, top_n=RERANKER_TOP_N)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
        if config.enabled:
            rerank_times.append(rerank_ms)
        total_times.append((time.perf_counter() - query_started) * 1000)
        after_locations = locations(results)
        before_rank = expected_rank(before_locations, expected)
        after_rank = expected_rank(after_locations, expected)
        records.append(
            {
                "query_id": question["id"],
                "pair": question.get("content_lang"),
                "cell": f"{question['query_lang']}_query_{question['content_lang']}_content",
                "expected": expected,
                "expected_rank_before": before_rank,
                "expected_rank_after": after_rank,
                "classification": (
                    classify_case(before_rank, after_rank) if config.enabled else "baseline"
                ),
                "candidate_count_before": len(candidates),
                "ranked_locations": after_locations,
                "expected_locations": expected,
                "expect_not_found": question.get("expect_not_found", False),
                "query_embed_ms": round(query_embed_times[-1], 3),
                "rerank_ms": round(rerank_ms, 3) if config.enabled else None,
                "total_retrieval_ms": round(total_times[-1], 3),
            }
        )
    await ollama.aclose()
    overall, by_cell, per_question = aggregate_per_question(records)

    def mean_cells(keys: tuple[str, ...], metric: str) -> float | None:
        values = [by_cell[k][metric] for k in keys if by_cell[k]["question_count"]]
        return sum(values) / len(values) if values else None

    classified = [
        r["classification"] for r in records if config.enabled and not r["expect_not_found"]
    ]
    pre_top5 = [
        r
        for r in records
        if config.enabled
        and not r["expect_not_found"]
        and r["expected_rank_before"]
        and r["expected_rank_before"] <= 5
    ]
    rescue_pool = [
        r
        for r in records
        if config.enabled
        and not r["expect_not_found"]
        and r["expected_rank_before"]
        and r["expected_rank_before"] > 5
    ]
    drops = sum(1 for r in pre_top5 if r["expected_rank_after"] is None)
    result = {
        "config": name,
        "model": config.model,
        "backend": config.backend,
        "candidate_k": config.candidate_k,
        "top_n": config.top_n,
        "embedding_control": "qwen3-4b@1024 + BM25 sparse + RRF",
        "overall": overall,
        "by_cell": by_cell,
        "cross_lingual": {
            "recall_at_5": mean_cells(CROSS_CELLS, "recall_at_5"),
            "mrr": mean_cells(CROSS_CELLS, "mrr"),
            "ndcg_at_5": mean_cells(CROSS_CELLS, "ndcg_at_5"),
        },
        "mono_lingual": {
            "recall_at_5": mean_cells(MONO_CELLS, "recall_at_5"),
            "mrr": mean_cells(MONO_CELLS, "mrr"),
            "ndcg_at_5": mean_cells(MONO_CELLS, "ndcg_at_5"),
        },
        "rescue_drop": {
            "definition": (
                "rescue = expected rank improves or enters top-5; "
                "rescue_rate specifically counts entries from pre-rank >5; "
                "drop = <=5 before and absent after"
            ),
            "rescued_count": sum(1 for c in classified if c == "rescued"),
            "drop_count": drops,
            "reranker_rescue_rate": (
                sum(
                    1
                    for r in rescue_pool
                    if r["expected_rank_after"] and r["expected_rank_after"] <= 5
                )
                / len(rescue_pool)
                if rescue_pool
                else None
            ),
            "reranker_drop_rate": drops / len(pre_top5) if pre_top5 else None,
            "classification_counts": {
                label: classified.count(label)
                for label in ("rescued", "unchanged", "degraded", "dropped_out_of_top5")
            },
        },
        "latency": {
            "rerank_p50_ms": percentile(rerank_times, 50) if config.enabled else "not measured",
            "rerank_p95_ms": percentile(rerank_times, 95) if config.enabled else "not measured",
            "total_retrieval_p50_ms": percentile(total_times, 50),
            "total_retrieval_p95_ms": percentile(total_times, 95),
            "query_throughput_qps": round(1000 / (sum(total_times) / len(total_times)), 3)
            if total_times
            else None,
            "model_load_seconds": round(load_seconds, 3)
            if load_seconds is not None
            else "not measured",
            "serving": "local Python sentence-transformers",
            "device": "cpu" if reranker else "not applicable",
            "memory_mb": "not measured",
            "query_sample_count": len(total_times),
        },
        "per_question": per_question,
    }
    return result, records


def paired_comparison(results: dict[str, dict], seed: int, iterations: int) -> dict:
    comparisons = {}
    metric_names = ("recall_at_1", "recall_at_3", "recall_at_5", "mrr", "ndcg_at_5")
    for left, right in (("off", "existing"), ("off", "multilingual"), ("existing", "multilingual")):
        key = f"{left}_vs_{right}"
        comparisons[key] = {}
        left_q = results[left]["per_question"]
        right_q = results[right]["per_question"]
        ids = sorted(set(left_q) & set(right_q))
        for subset, allowed in [
            ("overall", None),
            ("cross_lingual", CROSS_CELLS),
            ("mono_lingual", MONO_CELLS),
            *[(cell, (cell,)) for cell in CELLS],
        ]:
            subset_ids = (
                ids
                if allowed is None
                else [
                    r["query_id"]
                    for r in results[left]["cases"]
                    if r["cell"] in allowed and not r["expect_not_found"]
                ]
            )
            subset_ids = [i for i in subset_ids if i in left_q and i in right_q]
            if not subset_ids:
                continue
            comparisons[key][subset] = {}
            for metric in metric_names:
                ci = paired_bootstrap_ci(
                    [left_q[i][metric] for i in subset_ids],
                    [right_q[i][metric] for i in subset_ids],
                    metric,
                    subset,
                    seed,
                    iterations=iterations,
                )
                comparisons[key][subset][metric] = {
                    "delta_left_minus_right": ci.observed_delta,
                    "lower": ci.lower,
                    "upper": ci.upper,
                    "seed": seed,
                    "iterations": iterations,
                    "question_count": len(subset_ids),
                }
    return comparisons


def report_markdown(payload: dict) -> str:
    lines = [
        "# Sprint 26 — Reranker benchmark",
        "",
        (
            "Decision rule was pre-committed before the run: a multilingual reranker may "
            "replace OFF only when cross-lingual Recall@5 and MRR are at least OFF, "
            "mono-lingual Recall@5 regression is <= 0.01, and latency cost is documented "
            "and acceptable. Existing English reranking is not a winner by default."
        ),
        "",
        (
            f"Dataset: `{payload['dataset']}` · questions: {payload['question_count']} · "
            f"fingerprint: `{payload['dataset_fingerprint']}`"
        ),
        (
            "Controls: Qwen3-Embedding-4B@1024 + BM25 sparse + Qdrant RRF · "
            f"candidate k={RERANKER_CANDIDATE_K} · output n={RERANKER_TOP_N}"
        ),
        "",
        f"Production recommendation: **{payload['production_decision']['recommendation']}** · "
        f"latency gate: total retrieval p95 <= {MAX_ACCEPTABLE_TOTAL_RETRIEVAL_P95_MS}ms",
        "",
        "## Cross-lingual results",
        "",
        "| Config | TR→EN R@5 | EN→TR R@5 | Cross MRR | Cross nDCG@5 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in CONFIG_NAMES:
        r = payload["results"][name]
        c = r["by_cell"]
        lines.append(
            f"| {name} | {c['tr_query_en_content']['recall_at_5']:.4f} | "
            f"{c['en_query_tr_content']['recall_at_5']:.4f} | "
            f"{r['cross_lingual']['mrr']:.4f} | {r['cross_lingual']['ndcg_at_5']:.4f} |"
        )
    lines += [
        "",
        "## Rescue / drop",
        "",
        "| Config | rescued | dropped from top-5 | rescue rate | drop rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in CONFIG_NAMES:
        r = payload["results"][name]["rescue_drop"]
        lines.append(
            f"| {name} | {r['rescued_count']} | {r['drop_count']} | "
            f"{r['reranker_rescue_rate']} | {r['reranker_drop_rate']} |"
        )
    lines += [
        "",
        "## Operational notes",
        "",
        (
            "Reranker inference uses the local Python sentence-transformers backend. "
            "The production call is isolated in a worker thread from the async retrieval "
            "function; this benchmark measures model cost without changing ranking semantics."
        ),
        "",
        "Memory/VRAM was not measured. A benchmark result is not a universal security "
        "or quality guarantee.",
    ]
    return "\n".join(lines) + "\n"


async def main_async(args) -> None:
    dataset_path = Path(args.dataset)
    questions = json.loads(dataset_path.read_text(encoding="utf-8"))
    if args.max_questions:
        questions = questions[: args.max_questions]
    output = Path(args.output)
    work_dir = Path(args.work_dir)
    output.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    qdrant = QdrantClient(url=settings.qdrant_url)
    index = await ensure_index(qdrant, args.collection, work_dir, args.rebuild_index)
    configs = args.configs
    results: dict[str, dict] = {}
    all_cases: dict[str, list[dict]] = {}
    for name in configs:
        result, cases = await run_config(name, questions, qdrant, args.collection)
        result["cases"] = cases
        results[name] = result
        all_cases[name] = cases
        (output / f"{name}.partial.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    dataset_fingerprint = "55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691"
    payload = {
        "sprint": 26,
        "dataset": str(dataset_path),
        "dataset_fingerprint": dataset_fingerprint,
        "question_count": len(questions),
        "controls": {
            "embedding": "qwen3-4b@1024",
            "sparse": "BM25",
            "fusion": "RRF",
            "candidate_k": RERANKER_CANDIDATE_K,
            "top_n": RERANKER_TOP_N,
        },
        "index": index,
        "results": results,
    }
    off = results.get("off")
    multilingual = results.get("multilingual")
    decision = "NEED_MORE_DATA"
    decision_reasons = []
    if off and multilingual:
        cross_ok = (
            multilingual["cross_lingual"]["recall_at_5"] >= off["cross_lingual"]["recall_at_5"]
            and multilingual["cross_lingual"]["mrr"] >= off["cross_lingual"]["mrr"]
        )
        mono_regression = (
            off["mono_lingual"]["recall_at_5"] - multilingual["mono_lingual"]["recall_at_5"]
        )
        mono_ok = mono_regression <= 0.01
        latency_ok = (
            multilingual["latency"]["total_retrieval_p95_ms"]
            <= MAX_ACCEPTABLE_TOTAL_RETRIEVAL_P95_MS
        )
        if cross_ok and mono_ok and latency_ok:
            decision = "ADOPT_MULTILINGUAL"
        else:
            decision = "DISABLE_RERANKER"
        decision_reasons = {
            "cross_lingual_quality_ok": cross_ok,
            "mono_recall_regression": mono_regression,
            "mono_recall_regression_ok": mono_ok,
            "multilingual_total_retrieval_p95_ms": multilingual["latency"][
                "total_retrieval_p95_ms"
            ],
            "latency_threshold_ms": MAX_ACCEPTABLE_TOTAL_RETRIEVAL_P95_MS,
            "latency_ok": latency_ok,
        }
    payload["production_decision"] = {
        "recommendation": decision,
        "reasons": decision_reasons,
        "rule": (
            "Adopt multilingual when cross-lingual Recall@5 and MRR are >= OFF, "
            "mono Recall@5 regression <= 0.01, and total retrieval p95 <= 3000ms."
        ),
    }
    (output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # `paired_comparison` needs case membership for cell subsets; retain it
    # only while calculating, then the public result stays compact.
    for name in results:
        results[name]["cases"] = all_cases[name]
    comparison = paired_comparison(results, args.bootstrap_seed, args.bootstrap_iterations)
    (output / "paired-comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )
    cases_payload = [
        {"config": name, **case} for name, cases in all_cases.items() for case in cases
    ]
    (output / "cases.json").write_text(
        json.dumps(cases_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "report.md").write_text(report_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "index": index,
                "configs": list(configs),
                "question_count": len(questions),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark OFF, existing, and multilingual reranking"
    )
    parser.add_argument("--configs", nargs="+", choices=CONFIG_NAMES, default=list(CONFIG_NAMES))
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="diagnostic subset only; omit for the full 220-query run",
    )
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
