"""Sprint 18: real, isolated benchmark comparing two embedding models
(baseline vs. challenger) on multilingual/cross-lingual retrieval quality
AND operational cost — against native Ollama + docker-compose Qdrant, not
mocked.

    python -m scripts.benchmark_embeddings --baseline nomic --challenger qwen3-4b

Single variable: the embedding model. Chunking, sparse encoding, RRF
fusion, and top_k/top_n are IDENTICAL between baseline and challenger —
both go through the exact same app/retrieval/search.py::search() call,
which is also production's own retrieval path (reranker explicitly
disabled here — see app/wiring.py for where it's enabled in production).
Each model gets its own isolated Qdrant collection
(kb_benchmark_{model_key}) and its own SQLite registry file under
--work-dir, both re-indexed independently from the same real corpus
fixtures. Neither touches settings.qdrant_collection_name/
registry_db_path — this script never opens the production collection.

Writes artifacts/embedding-benchmark/results.json (full machine-readable
data) and report.md (the human-readable table). Any metric this
environment can't reliably measure (see OperationalMetrics.ram_mb) is
recorded as None / "not measured" — never guessed.
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics
from app.evaluation.retrieval_metrics import Location
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.citation_location import location_for
from app.llm.embedding_models import EmbeddingModelConfig, get_embedding_model_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from tests.fixtures.golden_api_reference_en import build_golden_api_reference_en
from tests.fixtures.golden_enterprise_faq_tr import build_golden_enterprise_faq_tr
from tests.fixtures.golden_markdown_source import build_golden_markdown_source
from tests.fixtures.golden_source import build_golden_source_pdf

DEFAULT_GOLDEN_SET = "tests/fixtures/embedding_benchmark_golden.json"
DEFAULT_WORK_DIR = "artifacts/embedding-benchmark/work"
DEFAULT_OUTPUT_DIR = "artifacts/embedding-benchmark"


def build_corpus(docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    build_golden_source_pdf(str(docs_dir / "nimbus_handbook.pdf"))
    build_golden_markdown_source(str(docs_dir / "nimbus_cli.md"))
    build_golden_api_reference_en(str(docs_dir / "nimbus_api_reference.md"))
    build_golden_enterprise_faq_tr(str(docs_dir / "nimbus_kurumsal_sss.md"))


def load_golden_questions(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def _stop_ollama_model(base_url: str, model: str) -> None:
    """Best-effort model eviction so the first embed call of a phase is a
    genuine cold load, not warm from a previous phase/manual testing.
    Uses the `ollama` CLI (already required to run this benchmark at
    all); failure here is non-fatal — model_load_seconds just becomes
    less meaningful, not a crash.
    """
    try:
        subprocess.run(
            ["ollama", "stop", model], capture_output=True, timeout=30, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


@dataclass
class OperationalMetrics:
    embedding_dimension: int
    indexing_seconds: float
    chunks_indexed: int
    chunks_per_second: float
    model_load_seconds: float | None
    query_embed_p50_ms: float
    query_embed_p95_ms: float
    total_retrieval_p50_ms: float
    total_retrieval_p95_ms: float
    qdrant_storage_bytes_estimate: int
    ram_mb: None = None  # not measured — see module docstring

    def as_dict(self) -> dict:
        d = asdict(self)
        d["ram_mb"] = "not measured"
        if self.model_load_seconds is None:
            d["model_load_seconds"] = "not measured"
        return d


async def run_model_benchmark(
    model_key: str,
    settings_obj,
    golden_questions: list[dict],
    work_dir: Path,
) -> tuple[dict, OperationalMetrics]:
    config: EmbeddingModelConfig = get_embedding_model_config(model_key, settings_obj)
    collection_name = f"kb_benchmark_{model_key}"
    registry_path = work_dir / f"registry_{model_key}.db"
    docs_dir = work_dir / "corpus"
    if not docs_dir.exists():
        build_corpus(docs_dir)

    _stop_ollama_model(settings_obj.ollama_base_url, config.ollama_model)

    qdrant_client = QdrantClient(url=settings_obj.qdrant_url)
    if qdrant_client.collection_exists(collection_name):
        qdrant_client.delete_collection(collection_name)
    store = QdrantStore(
        client=qdrant_client, collection_name=collection_name, dense_dimension=config.dimension
    )
    if registry_path.exists():
        registry_path.unlink()
    registry = DocumentRegistry(registry_path)
    ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    sparse_encoder = SparseEncoder()
    fingerprint = build_pipeline_fingerprint(config)

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(text, model=config.ollama_model, prefix=config.document_prefix())

    connector = LocalFilesystemConnector(str(docs_dir))

    load_start = time.perf_counter()
    first_embed_done = {"t": None}
    real_embed_fn = embed_fn

    async def timed_embed_fn(text: str) -> list[float]:
        vector = await real_embed_fn(text)
        if first_embed_done["t"] is None:
            first_embed_done["t"] = time.perf_counter() - load_start
        return vector

    index_start = time.perf_counter()
    stats = await ingest_connector(
        connector, store, registry, timed_embed_fn, sparse_encoder,
        pipeline_fingerprint=fingerprint,
    )
    indexing_seconds = time.perf_counter() - index_start
    chunks_per_second = (
        stats.chunks_upserted / indexing_seconds if indexing_seconds > 0 else 0.0
    )

    collection_info = qdrant_client.get_collection(collection_name)
    point_count = collection_info.points_count or 0
    # 4 bytes/float (Qdrant's default f32 storage) x dense dim, plus a
    # generous flat estimate for the sparse vector and payload — an
    # estimate, explicitly labeled as such in the report, not a real
    # measurement of Qdrant's on-disk footprint (which includes index
    # overhead this doesn't account for).
    storage_estimate = point_count * (config.dimension * 4 + 2048)

    query_embed_ms: list[float] = []
    retrieval_ms: list[float] = []
    per_cell_metrics: dict[tuple[str, str], list] = defaultdict(list)
    all_metrics = []
    not_found_hits = 0
    not_found_total = 0

    for question in golden_questions:
        query = question["query"]
        expected_locations: list[Location] = [tuple(loc) for loc in question["expected_locations"]]
        is_not_found = question.get("expect_not_found", False)

        embed_start = time.perf_counter()
        # search() embeds internally; to also isolate PURE query-embed
        # latency (not blended with retrieval), embed once here for
        # timing, then let search() re-embed (a second, real call) for
        # the actual retrieval — accepted double cost, this is a
        # benchmark script, not the hot path.
        await ollama.embed(query, model=config.ollama_model, prefix=config.query_prefix())
        query_embed_ms.append((time.perf_counter() - embed_start) * 1000)

        retrieval_start = time.perf_counter()
        results = await search(
            query,
            ollama,
            sparse_encoder,
            qdrant_client,
            collection_name,
            config.ollama_model,
            reranker=None,  # Sprint 18 rule: reranker OFF for this benchmark
            query_prefix=config.query_prefix(),
        )
        retrieval_ms.append((time.perf_counter() - retrieval_start) * 1000)

        ranked_locations = [
            (r.payload["source_type"], r.payload["source_id"], location_for(r.payload))
            for r in results
        ]

        if is_not_found:
            not_found_total += 1
            if not results or not ranked_locations:
                not_found_hits += 1
            continue

        metrics = compute_rank_metrics(ranked_locations, expected_locations)
        all_metrics.append(metrics)
        cell = (question["query_lang"], question["content_lang"])
        per_cell_metrics[cell].append(metrics)

    await ollama.aclose()

    op_metrics = OperationalMetrics(
        embedding_dimension=config.dimension,
        indexing_seconds=indexing_seconds,
        chunks_indexed=stats.chunks_upserted,
        chunks_per_second=chunks_per_second,
        model_load_seconds=first_embed_done["t"],
        query_embed_p50_ms=_percentile(query_embed_ms, 50),
        query_embed_p95_ms=_percentile(query_embed_ms, 95),
        total_retrieval_p50_ms=_percentile(retrieval_ms, 50),
        total_retrieval_p95_ms=_percentile(retrieval_ms, 95),
        qdrant_storage_bytes_estimate=storage_estimate,
    )

    result = {
        "model_key": model_key,
        "ollama_model": config.ollama_model,
        "fingerprint_digest": fingerprint.digest(),
        "overall": aggregate_rank_metrics(all_metrics),
        "by_cell": {
            f"{query_lang}_query_{content_lang}_content": aggregate_rank_metrics(metrics)
            | {"question_count": len(metrics)}
            for (query_lang, content_lang), metrics in sorted(per_cell_metrics.items())
        },
        "not_found_accuracy": (
            not_found_hits / not_found_total if not_found_total else None
        ),
        "not_found_question_count": not_found_total,
    }
    return result, op_metrics


def decide(baseline_result: dict, challenger_result: dict) -> dict:
    """Sprint 18's decision rule: the challenger is NOT automatically the
    winner just because its average score is higher. Cross-lingual cells
    (tr_query_en_content, en_query_tr_content) are the priority signal;
    same-language cells (tr_query_tr_content, en_query_en_content) must
    not regress materially for an ADOPT recommendation.
    """
    def cell(result, name, key):
        c = result["by_cell"].get(name)
        return c[key] if c else None

    cross_cells = ["tr_query_en_content", "en_query_tr_content"]
    mono_cells = ["tr_query_tr_content", "en_query_en_content"]

    cross_deltas = {}
    for c in cross_cells:
        b, ch = cell(baseline_result, c, "recall_at_5"), cell(challenger_result, c, "recall_at_5")
        cross_deltas[c] = None if (b is None or ch is None) else ch - b

    mono_deltas = {}
    for c in mono_cells:
        b, ch = cell(baseline_result, c, "recall_at_5"), cell(challenger_result, c, "recall_at_5")
        mono_deltas[c] = None if (b is None or ch is None) else ch - b

    cross_mrr_deltas = {}
    for c in cross_cells:
        b, ch = cell(baseline_result, c, "mrr"), cell(challenger_result, c, "mrr")
        cross_mrr_deltas[c] = None if (b is None or ch is None) else ch - b

    valid_cross = [d for d in cross_deltas.values() if d is not None]
    valid_mono = [d for d in mono_deltas.values() if d is not None]
    valid_cross_mrr = [d for d in cross_mrr_deltas.values() if d is not None]

    # A "material regression" threshold on mono-lingual cells — not
    # tuned/validated against anything beyond common sense (a few
    # percentage points of recall on a small golden set is within
    # plausible noise); stated explicitly rather than left implicit.
    MONO_REGRESSION_THRESHOLD = -0.10

    cross_improved = bool(valid_cross) and all(d > 0 for d in valid_cross)
    cross_mrr_improved = bool(valid_cross_mrr) and all(d > 0 for d in valid_cross_mrr)
    mono_held = bool(valid_mono) and all(d >= MONO_REGRESSION_THRESHOLD for d in valid_mono)

    if not valid_cross or not valid_mono:
        recommendation = "NEED_MORE_DATA"
        reason = "One or more cells had no questions/results to compare."
    elif cross_improved and cross_mrr_improved and mono_held:
        recommendation = "ADOPT_QWEN3"
        reason = (
            "Both cross-lingual Recall@5 cells improved, cross-lingual MRR improved, "
            "and mono-lingual cells did not regress materially."
        )
    else:
        recommendation = "KEEP_NOMIC"
        reason = (
            "Cross-lingual improvement was not consistent across both cells and MRR, "
            "or a mono-lingual cell regressed materially — decision rule requires all "
            "three conditions."
        )

    return {
        "recommendation": recommendation,
        "reason": reason,
        "cross_lingual_recall_at_5_deltas": cross_deltas,
        "cross_lingual_mrr_deltas": cross_mrr_deltas,
        "mono_lingual_recall_at_5_deltas": mono_deltas,
    }


def render_markdown_report(
    baseline_key: str,
    challenger_key: str,
    baseline: dict,
    challenger: dict,
    baseline_ops: OperationalMetrics,
    challenger_ops: OperationalMetrics,
    decision: dict,
) -> str:
    def r5(result, cell):
        c = result["by_cell"].get(cell)
        return f"{c['recall_at_5']:.3f}" if c else "n/a"

    def mrr(result):
        return f"{result['overall']['mrr']:.3f}" if result["overall"] else "n/a"

    def ndcg(result):
        return f"{result['overall']['ndcg_at_5']:.3f}" if result["overall"] else "n/a"

    lines = [
        "# Embedding Benchmark: Nomic vs Qwen3-Embedding-4B",
        "",
        "Single-variable comparison — chunking, sparse encoding, RRF fusion, "
        "top_k/top_n, and reranker (off) identical between rows. See "
        "results.json for full per-question data.",
        "",
        "## Summary table",
        "",
        "| Model | TR→TR Recall@5 | EN→EN Recall@5 | TR→EN Recall@5 | EN→TR Recall@5 "
        "| MRR | nDCG@5 | Retrieval p95 (ms) |",
        "|---|---|---|---|---|---|---|---|",
        f"| {baseline_key} | {r5(baseline, 'tr_query_tr_content')} | "
        f"{r5(baseline, 'en_query_en_content')} | {r5(baseline, 'en_query_tr_content')} | "
        f"{r5(baseline, 'tr_query_en_content')} | {mrr(baseline)} | {ndcg(baseline)} | "
        f"{baseline_ops.total_retrieval_p95_ms:.1f} |",
        f"| {challenger_key} | {r5(challenger, 'tr_query_tr_content')} | "
        f"{r5(challenger, 'en_query_en_content')} | {r5(challenger, 'en_query_tr_content')} | "
        f"{r5(challenger, 'tr_query_en_content')} | {mrr(challenger)} | {ndcg(challenger)} | "
        f"{challenger_ops.total_retrieval_p95_ms:.1f} |",
        "",
        "(TR→EN = Turkish query, English content — cross-lingual. "
        "EN→TR = English query, Turkish content — cross-lingual. "
        "TR→TR and EN→EN are mono-lingual.)",
        "",
        "## Per-language-pair detail",
        "",
        "| Model | Cell | Recall@1 | Recall@3 | Recall@5 | MRR | nDCG@5 | n |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, result in ((baseline_key, baseline), (challenger_key, challenger)):
        for cell_name in [
            "tr_query_tr_content",
            "en_query_en_content",
            "en_query_tr_content",
            "tr_query_en_content",
        ]:
            c = result["by_cell"].get(cell_name)
            if not c:
                continue
            lines.append(
                f"| {key} | {cell_name} | {c['recall_at_1']:.3f} | {c['recall_at_3']:.3f} | "
                f"{c['recall_at_5']:.3f} | {c['mrr']:.3f} | {c['ndcg_at_5']:.3f} | "
                f"{c['question_count']} |"
            )

    def op_row(label: str, base_val, chal_val) -> str:
        return f"| {label} | {base_val} | {chal_val} |"

    lines += [
        "",
        "## Operational metrics",
        "",
        "| Metric | " + baseline_key + " | " + challenger_key + " |",
        "|---|---|---|",
        op_row(
            "Embedding dimension",
            baseline_ops.embedding_dimension,
            challenger_ops.embedding_dimension,
        ),
        op_row(
            "Indexing throughput (chunks/sec)",
            f"{baseline_ops.chunks_per_second:.2f}",
            f"{challenger_ops.chunks_per_second:.2f}",
        ),
        op_row("Chunks indexed", baseline_ops.chunks_indexed, challenger_ops.chunks_indexed),
        op_row(
            "Query embed p50 (ms)",
            f"{baseline_ops.query_embed_p50_ms:.1f}",
            f"{challenger_ops.query_embed_p50_ms:.1f}",
        ),
        op_row(
            "Query embed p95 (ms)",
            f"{baseline_ops.query_embed_p95_ms:.1f}",
            f"{challenger_ops.query_embed_p95_ms:.1f}",
        ),
        op_row(
            "Total retrieval p50 (ms)",
            f"{baseline_ops.total_retrieval_p50_ms:.1f}",
            f"{challenger_ops.total_retrieval_p50_ms:.1f}",
        ),
        op_row(
            "Total retrieval p95 (ms)",
            f"{baseline_ops.total_retrieval_p95_ms:.1f}",
            f"{challenger_ops.total_retrieval_p95_ms:.1f}",
        ),
        op_row(
            "Model load/warmup (s)",
            baseline_ops.model_load_seconds or "not measured",
            challenger_ops.model_load_seconds or "not measured",
        ),
        op_row(
            "Qdrant storage estimate (bytes)",
            baseline_ops.qdrant_storage_bytes_estimate,
            challenger_ops.qdrant_storage_bytes_estimate,
        ),
        op_row("RAM/VRAM usage", "not measured", "not measured"),
        "",
        "## Decision",
        "",
        f"**Recommendation: {decision['recommendation']}**",
        "",
        decision["reason"],
        "",
        "Cross-lingual Recall@5 deltas (challenger - baseline): "
        f"{decision['cross_lingual_recall_at_5_deltas']}",
        "",
        f"Cross-lingual MRR deltas: {decision['cross_lingual_mrr_deltas']}",
        "",
        f"Mono-lingual Recall@5 deltas: {decision['mono_lingual_recall_at_5_deltas']}",
        "",
    ]
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> None:
    golden_questions = load_golden_questions(args.golden_set)
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running baseline: {args.baseline}")
    baseline_result, baseline_ops = await run_model_benchmark(
        args.baseline, settings, golden_questions, work_dir
    )
    print(f"Running challenger: {args.challenger}")
    challenger_result, challenger_ops = await run_model_benchmark(
        args.challenger, settings, golden_questions, work_dir
    )

    decision = decide(baseline_result, challenger_result)

    output = {
        "baseline": baseline_result | {"operational": baseline_ops.as_dict()},
        "challenger": challenger_result | {"operational": challenger_ops.as_dict()},
        "decision": decision,
        "golden_set_path": args.golden_set,
        "question_count": len(golden_questions),
    }

    (output_dir / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    report = render_markdown_report(
        args.baseline, args.challenger, baseline_result, challenger_result,
        baseline_ops, challenger_ops, decision,
    )
    (output_dir / "report.md").write_text(report)

    print(report)
    print(f"\nWritten to {output_dir}/results.json and {output_dir}/report.md")

    if args.cleanup_work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark two embedding models on retrieval quality"
    )
    parser.add_argument("--baseline", default="nomic", choices=["nomic", "qwen3-4b"])
    parser.add_argument("--challenger", default="qwen3-4b", choices=["nomic", "qwen3-4b"])
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cleanup-work-dir", action="store_true")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
