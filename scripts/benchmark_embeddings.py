"""Sprint 18/19: real, isolated benchmark comparing embedding model
configurations on multilingual/cross-lingual retrieval quality AND
operational cost — against native Ollama + docker-compose Qdrant, not
mocked.

    python -m scripts.benchmark_embeddings --configs nomic@native qwen3-4b@native

Sprint 19 generalized Sprint 18's baseline-vs-challenger script into a
multi-candidate one: any number of "model@dimension" configs (see
app/llm/embedding_models.py::parse_config_token) can be compared in one
run, each in its own isolated Qdrant collection
(kb_benchmark_{model}_{dimension}) and its own SQLite registry under
--work-dir. Neither touches settings.qdrant_collection_name/
registry_db_path — this script never opens the production collection.

Single variable per comparison: chunking, sparse encoding, RRF fusion,
top_k/top_n, and reranker (off) are IDENTICAL across every config — all
go through the exact same app/retrieval/search.py::search() call, which
is also production's own retrieval path.

A config whose requested output dimension isn't actually honored by the
backend (Ollama silently CLAMPS an out-of-range dimensions request
instead of erroring — see app/llm/ollama_client.py::OllamaClient.embed)
is marked unsupported=True and skipped, never silently substituted.

Writes results.json (full machine-readable data, every config's
quality/language-pair/operational metrics, support state) and report.md
(the human-readable table, Pareto frontier, and production
recommendation) to --output-dir. Any metric this environment can't
reliably measure (see OperationalMetrics.ram_mb) is recorded as
None / "not measured" — never guessed.
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
from app.llm.embedding_models import EmbeddingModelConfig, parse_config_token
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
DEFAULT_WORK_DIR = "artifacts/embedding-benchmark-sprint19/work"
DEFAULT_OUTPUT_DIR = "artifacts/embedding-benchmark-sprint19"
QDRANT_CONTAINER_NAME = "kb-rag-qdrant"

# Sprint 19's exact configuration matrix — every one of these was
# verified with a real /api/embed call before being defaulted here (see
# docs/sprint-19-plan.md): all 6 are genuinely supported by this
# environment's Ollama 0.32.6.
DEFAULT_CONFIGS = [
    "nomic@native",
    "qwen3-0.6b@native",
    "qwen3-4b@native",
    "qwen3-4b@1024",
    "qwen3-0.6b@1024",
    "qwen3-0.6b@768",
]

WARMUP_CALLS = 3
CROSS_LINGUAL_CELLS = ["tr_query_en_content", "en_query_tr_content"]
MONO_LINGUAL_CELLS = ["tr_query_tr_content", "en_query_en_content"]

# The Sprint 18 "quality ceiling" reference every smaller/truncated
# config's acceptance is measured against.
QUALITY_CEILING_LABEL = "qwen3-4b@native"

# Sprint 19's acceptance thresholds (docs/sprint-19-plan.md /
# user-specified) — a smaller/cheaper config is a production CANDIDATE
# over the quality-ceiling model only if it stays within these losses.
# These are not statistically derived (68 questions is too small for
# that — see the report's Statistical caution section); they encode a
# judgment call about how much quality a real deployment could tolerate
# losing for a meaningful cost win, stated explicitly rather than left
# implicit in code.
MAX_CROSS_RECALL_LOSS = 0.05
MAX_CROSS_MRR_LOSS = 0.05
MAX_MONO_RECALL_REGRESSION = 0.02


def _sanitize_label(label: str) -> str:
    return label.replace("@", "_").replace(".", "").replace("-", "_")


def collection_name_for(config: EmbeddingModelConfig) -> str:
    return f"kb_benchmark_{_sanitize_label(config.label())}"


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


def _stop_ollama_model(model: str) -> None:
    """Best-effort model eviction so the first embed call of a phase is a
    genuine cold load, not warm from a previous phase/manual testing.
    Failure here is non-fatal — model_load_seconds just becomes less
    meaningful, not a crash.
    """
    try:
        subprocess.run(["ollama", "stop", model], capture_output=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _measure_real_collection_disk_bytes(collection_name: str) -> int | None:
    """Best-effort REAL disk measurement (Sprint 19 upgrade over Sprint
    18's formula-only estimate) via `docker exec du` on the Qdrant
    container's own storage volume. Returns None (not an exception) if
    docker/the container/the path isn't available — the caller falls
    back to the formula estimate and labels it as such. Never raises.

    Uses `-sk` (block-based KB), NOT `-sb`/--apparent-size — verified for
    real against this environment's actual collections: Qdrant
    preallocates its dense-vector storage and WAL as large, mostly-empty
    SPARSE mmap files (e.g. a 32MB logical WAL segment for a 32-chunk
    collection), and `-sb` reports that full logical/apparent size,
    which was nearly IDENTICAL (~211MB) across every config regardless
    of real dimension — not a real per-config storage signal. `-sk`
    reports actual disk blocks consumed, which genuinely differed by
    config when checked directly (nomic@native 2444KB vs
    qwen3-4b@native 2944KB) — see docs/sprint-19-plan.md.
    """
    try:
        result = subprocess.run(
            [
                "docker", "exec", QDRANT_CONTAINER_NAME,
                "du", "-sk", f"/qdrant/storage/collections/{collection_name}",
            ],
            capture_output=True, timeout=15, check=False, text=True,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.split()[0]) * 1024
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


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
    query_sample_count: int
    storage_bytes: int
    storage_measurement: str  # "real" (docker exec du) or "estimate"
    ram_mb: None = None  # not measured — see module docstring
    vram_mb: None = None  # not measured — see module docstring

    def as_dict(self) -> dict:
        d = asdict(self)
        d["ram_mb"] = "not measured"
        d["vram_mb"] = "not measured"
        if self.model_load_seconds is None:
            d["model_load_seconds"] = "not measured"
        return d


async def probe_dimension_support(
    ollama: OllamaClient, config: EmbeddingModelConfig
) -> tuple[bool, int]:
    """A REAL call, not an assumption — Ollama silently clamps an
    out-of-range `dimensions` request to the model's native size instead
    of erroring, so the only honest way to know whether a config is
    supported is to make the call and check what actually came back.
    """
    vector = await ollama.embed("dimension probe", model=config.ollama_model, prefix="")
    if config.output_dimension is None:
        return True, len(vector)
    vector = await ollama.embed(
        "dimension probe", model=config.ollama_model, dimensions=config.output_dimension
    )
    return len(vector) == config.output_dimension, len(vector)


async def run_config_benchmark(
    config: EmbeddingModelConfig,
    settings_obj,
    golden_questions: list[dict],
    work_dir: Path,
) -> dict:
    label = config.label()
    collection_name = collection_name_for(config)
    registry_path = work_dir / f"registry_{_sanitize_label(label)}.db"
    docs_dir = work_dir / "corpus"
    if not docs_dir.exists():
        build_corpus(docs_dir)

    _stop_ollama_model(config.ollama_model)
    probe_ollama = OllamaClient(base_url=settings_obj.ollama_base_url)
    supported, actual_dimension = await probe_dimension_support(probe_ollama, config)
    await probe_ollama.aclose()

    if not supported:
        return {
            "label": label,
            "model_key": config.key,
            "ollama_model": config.ollama_model,
            "requested_dimension": config.dimension,
            "actual_dimension_returned": actual_dimension,
            "supported": False,
        }

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
        return await ollama.embed(
            text,
            model=config.ollama_model,
            prefix=config.document_prefix(),
            dimensions=config.output_dimension,
        )

    connector = LocalFilesystemConnector(str(docs_dir))

    load_start = time.perf_counter()
    first_embed_at = {"t": None}

    async def timed_embed_fn(text: str) -> list[float]:
        vector = await embed_fn(text)
        if first_embed_at["t"] is None:
            first_embed_at["t"] = time.perf_counter() - load_start
        return vector

    index_start = time.perf_counter()
    stats = await ingest_connector(
        connector, store, registry, timed_embed_fn, sparse_encoder,
        pipeline_fingerprint=fingerprint,
    )
    indexing_seconds = time.perf_counter() - index_start
    chunks_per_second = stats.chunks_upserted / indexing_seconds if indexing_seconds > 0 else 0.0

    real_storage_bytes = _measure_real_collection_disk_bytes(collection_name)
    if real_storage_bytes is not None:
        storage_bytes, storage_measurement = real_storage_bytes, "real"
    else:
        collection_info = qdrant_client.get_collection(collection_name)
        point_count = collection_info.points_count or 0
        storage_bytes = point_count * (config.dimension * 4 + 2048)
        storage_measurement = "estimate"

    # Deterministic warmup — discarded, never mixed into the timed
    # samples below, so a cold-start outlier can't skew p50/p95.
    for _ in range(WARMUP_CALLS):
        await ollama.embed("warmup query", model=config.ollama_model,
                            prefix=config.query_prefix(), dimensions=config.output_dimension)

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
        await ollama.embed(query, model=config.ollama_model, prefix=config.query_prefix(),
                            dimensions=config.output_dimension)
        query_embed_ms.append((time.perf_counter() - embed_start) * 1000)

        retrieval_start = time.perf_counter()
        results = await search(
            query, ollama, sparse_encoder, qdrant_client, collection_name, config.ollama_model,
            reranker=None,  # rule: reranker OFF for this benchmark
            query_prefix=config.query_prefix(),
            dimensions=config.output_dimension,
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

    by_cell = {
        f"{query_lang}_query_{content_lang}_content": aggregate_rank_metrics(metrics)
        | {"question_count": len(metrics)}
        for (query_lang, content_lang), metrics in sorted(per_cell_metrics.items())
    }

    def cell_mean(cells: list[str], key: str) -> float | None:
        values = [by_cell[c][key] for c in cells if c in by_cell]
        return sum(values) / len(values) if values else None

    op_metrics = OperationalMetrics(
        embedding_dimension=config.dimension,
        indexing_seconds=indexing_seconds,
        chunks_indexed=stats.chunks_upserted,
        chunks_per_second=chunks_per_second,
        model_load_seconds=first_embed_at["t"],
        query_embed_p50_ms=_percentile(query_embed_ms, 50),
        query_embed_p95_ms=_percentile(query_embed_ms, 95),
        total_retrieval_p50_ms=_percentile(retrieval_ms, 50),
        total_retrieval_p95_ms=_percentile(retrieval_ms, 95),
        query_sample_count=len(query_embed_ms),
        storage_bytes=storage_bytes,
        storage_measurement=storage_measurement,
    )

    return {
        "label": label,
        "model_key": config.key,
        "ollama_model": config.ollama_model,
        "requested_dimension": config.dimension,
        "actual_dimension_returned": actual_dimension,
        "supported": True,
        "fingerprint_digest": fingerprint.digest(),
        "overall": aggregate_rank_metrics(all_metrics),
        "by_cell": by_cell,
        "cross_lingual": {
            "recall_at_5": cell_mean(CROSS_LINGUAL_CELLS, "recall_at_5"),
            "mrr": cell_mean(CROSS_LINGUAL_CELLS, "mrr"),
            "ndcg_at_5": cell_mean(CROSS_LINGUAL_CELLS, "ndcg_at_5"),
        },
        "mono_lingual": {
            "recall_at_5": cell_mean(MONO_LINGUAL_CELLS, "recall_at_5"),
            "mrr": cell_mean(MONO_LINGUAL_CELLS, "mrr"),
            "ndcg_at_5": cell_mean(MONO_LINGUAL_CELLS, "ndcg_at_5"),
        },
        "not_found_accuracy": not_found_hits / not_found_total if not_found_total else None,
        "not_found_question_count": not_found_total,
        "operational": op_metrics.as_dict(),
    }


def pareto_dominated(candidate: dict, others: list[dict]) -> str | None:
    """A config is Pareto-dominated if some OTHER supported config is at
    least as good on every objective (higher cross-lingual Recall@5,
    higher cross-lingual MRR, lower query p95, lower dimension) and
    strictly better on at least one. Returns the dominating config's
    label, or None if not dominated.
    """
    c_recall = candidate["cross_lingual"]["recall_at_5"]
    c_mrr = candidate["cross_lingual"]["mrr"]
    c_p95 = candidate["operational"]["query_embed_p95_ms"]
    c_dim = candidate["requested_dimension"]

    for other in others:
        if other["label"] == candidate["label"]:
            continue
        o_recall = other["cross_lingual"]["recall_at_5"]
        o_mrr = other["cross_lingual"]["mrr"]
        o_p95 = other["operational"]["query_embed_p95_ms"]
        o_dim = other["requested_dimension"]

        at_least_as_good = (
            o_recall >= c_recall and o_mrr >= c_mrr and o_p95 <= c_p95 and o_dim <= c_dim
        )
        strictly_better = (
            o_recall > c_recall or o_mrr > c_mrr or o_p95 < c_p95 or o_dim < c_dim
        )
        if at_least_as_good and strictly_better:
            return other["label"]
    return None


def score(result: dict) -> dict:
    supported = [r for r in result if r.get("supported")]
    if not supported:
        return {
            "quality_winner": None,
            "efficiency_winner": None,
            "production_recommendation": (
                "No configuration was supported — cannot make a recommendation."
            ),
            "pareto_dominated": {},
        }

    # Quality score: weighted combination, weights explicit — Sprint
    # 17.7/18 already established cross-lingual retrieval as the
    # motivating weakness, so it's weighted higher than overall nDCG.
    def quality_score(r: dict) -> float:
        cross_recall = r["cross_lingual"]["recall_at_5"] or 0.0
        cross_mrr = r["cross_lingual"]["mrr"] or 0.0
        ndcg = r["overall"]["ndcg_at_5"]
        return 0.4 * cross_recall + 0.3 * cross_mrr + 0.3 * ndcg

    quality_winner = max(supported, key=quality_score)

    ceiling = next((r for r in supported if r["label"] == QUALITY_CEILING_LABEL), None)

    efficiency_candidates = []
    if ceiling is not None:
        ceiling_cross_recall = ceiling["cross_lingual"]["recall_at_5"] or 0.0
        ceiling_cross_mrr = ceiling["cross_lingual"]["mrr"] or 0.0
        ceiling_mono_recall = ceiling["mono_lingual"]["recall_at_5"] or 0.0
        for r in supported:
            cross_recall_loss = ceiling_cross_recall - (r["cross_lingual"]["recall_at_5"] or 0.0)
            cross_mrr_loss = ceiling_cross_mrr - (r["cross_lingual"]["mrr"] or 0.0)
            mono_regression = ceiling_mono_recall - (r["mono_lingual"]["recall_at_5"] or 0.0)
            if (
                cross_recall_loss <= MAX_CROSS_RECALL_LOSS
                and cross_mrr_loss <= MAX_CROSS_MRR_LOSS
                and mono_regression <= MAX_MONO_RECALL_REGRESSION
            ):
                efficiency_candidates.append(r)

    # Among acceptance-passing candidates, prefer smaller dimension
    # first (dominates storage/index cost most directly), tie-break by
    # lower query p95 — deterministic, stated explicitly rather than a
    # single opaque score.
    efficiency_winner = None
    if efficiency_candidates:
        efficiency_winner = min(
            efficiency_candidates,
            key=lambda r: (r["requested_dimension"], r["operational"]["query_embed_p95_ms"]),
        )

    dominated = {}
    for r in supported:
        dominator = pareto_dominated(r, supported)
        if dominator:
            dominated[r["label"]] = dominator

    if efficiency_winner and efficiency_winner["label"] != QUALITY_CEILING_LABEL:
        recommendation = (
            f"Recommended next migration candidate: {efficiency_winner['label']} — stays within "
            f"acceptance thresholds of {QUALITY_CEILING_LABEL} (cross-lingual Recall@5/MRR loss "
            f"<= {MAX_CROSS_RECALL_LOSS}, mono-lingual regression <= {MAX_MONO_RECALL_REGRESSION}) "
            "at a real dimension/latency cost saving. nomic remains the current production "
            "default — this is a candidate for the next migration decision, not an applied "
            "change."
        )
    elif efficiency_winner:
        recommendation = (
            f"{QUALITY_CEILING_LABEL} is both the quality winner and the efficiency winner among "
            "tested configs — no smaller/cheaper config met the acceptance thresholds. nomic "
            "remains the current production default."
        )
    else:
        recommendation = (
            "No configuration met the acceptance thresholds relative to the quality ceiling "
            f"({QUALITY_CEILING_LABEL}) — NEED MORE DATA / no smaller-config recommendation. "
            "nomic remains the current production default."
        )

    return {
        "quality_winner": quality_winner["label"],
        "efficiency_winner": efficiency_winner["label"] if efficiency_winner else None,
        "efficiency_candidates": [c["label"] for c in efficiency_candidates],
        "production_recommendation": recommendation,
        "pareto_dominated": dominated,
        "acceptance_thresholds": {
            "max_cross_recall_at_5_loss": MAX_CROSS_RECALL_LOSS,
            "max_cross_mrr_loss": MAX_CROSS_MRR_LOSS,
            "max_mono_recall_at_5_regression": MAX_MONO_RECALL_REGRESSION,
            "quality_ceiling": QUALITY_CEILING_LABEL,
        },
    }


def render_markdown_report(results: list[dict], decision: dict, golden_set_path: str) -> str:
    lines = [
        "# Embedding Benchmark Sprint 19: Qwen3 Size & Dimension Trade-off",
        "",
        "Multi-candidate, single-variable comparison — chunking, sparse encoding, RRF "
        "fusion, top_k/top_n, and reranker (off) identical across every config below. "
        f"Same 68-question golden set as Sprint 18 ({golden_set_path}), apples-to-apples. "
        "See results.json for full per-config, per-question data.",
        "",
        "## Configurations tested",
        "",
        "| Config | Supported | Dimension (requested/actual) |",
        "|---|---|---|",
    ]
    for r in results:
        supported = "yes" if r["supported"] else "**NO — unsupported**"
        dims = f"{r['requested_dimension']} / {r['actual_dimension_returned']}"
        lines.append(f"| {r['label']} | {supported} | {dims} |")

    supported_results = [r for r in results if r["supported"]]

    lines += [
        "",
        "## Quality summary",
        "",
        "| Config | TR→TR R@5 | EN→EN R@5 | TR→EN R@5 | EN→TR R@5 | Cross R@5 | "
        "Cross MRR | Mono R@5 | nDCG@5 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in supported_results:
        bc = r["by_cell"]

        def g(cell, key="recall_at_5"):
            return f"{bc[cell][key]:.3f}" if cell in bc else "n/a"

        cross_r5 = r["cross_lingual"]["recall_at_5"]
        cross_mrr = r["cross_lingual"]["mrr"]
        mono_r5 = r["mono_lingual"]["recall_at_5"]
        lines.append(
            f"| {r['label']} | {g('tr_query_tr_content')} | {g('en_query_en_content')} | "
            f"{g('en_query_tr_content')} | {g('tr_query_en_content')} | "
            f"{cross_r5:.3f} | {cross_mrr:.3f} | {mono_r5:.3f} | {r['overall']['ndcg_at_5']:.3f} |"
        )

    lines += [
        "",
        "(TR→EN = Turkish query, English content. EN→TR = English query, Turkish content. "
        "Both cross-lingual. Cross R@5/MRR = mean of the two cross-lingual cells. "
        "Mono R@5 = mean of TR→TR and EN→EN.)",
        "",
        "## Operational results",
        "",
        "| Config | Dim | Index chunks/s | Index total (s) | Query p50/p95 (ms) | "
        "Retrieval p50/p95 (ms) | Load (s) | Storage (bytes, real/estimate) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in supported_results:
        op = r["operational"]
        lines.append(
            f"| {r['label']} | {op['embedding_dimension']} | {op['chunks_per_second']:.2f} | "
            f"{op['indexing_seconds']:.2f} | {op['query_embed_p50_ms']:.1f}/"
            f"{op['query_embed_p95_ms']:.1f} | {op['total_retrieval_p50_ms']:.1f}/"
            f"{op['total_retrieval_p95_ms']:.1f} | {op['model_load_seconds']} | "
            f"{op['storage_bytes']} ({op['storage_measurement']}) |"
        )
    lines.append("")
    lines.append("RAM/VRAM: not measured for any configuration (see module docstring).")

    lines += [
        "",
        "## Pareto frontier",
        "",
        "A config is Pareto-dominated if another tested config is at least as good on "
        "cross-lingual Recall@5, cross-lingual MRR, query p95, AND dimension, and "
        "strictly better on at least one.",
        "",
        "| Config | Dominated by |",
        "|---|---|",
    ]
    for r in supported_results:
        dominator = decision["pareto_dominated"].get(r["label"])
        lines.append(f"| {r['label']} | {dominator or '— (on the frontier)'} |")

    lines += [
        "",
        "## Statistical caution",
        "",
        "68 questions is a small sample — per-cell cells are 16-17 questions. No "
        "bootstrap confidence intervals were computed this sprint (documented as a "
        "limitation, not attempted under time pressure with a small deterministic "
        "n — see docs/PLANNING.md's Sprint 19 closing note). Treat deltas smaller than "
        "roughly 1 question's worth of a cell (~6%) as noise, not signal.",
        "",
        "## Decision",
        "",
        f"**QUALITY WINNER: {decision['quality_winner']}**",
        "",
        "**EFFICIENCY WINNER: "
        f"{decision['efficiency_winner'] or 'none met acceptance thresholds'}**",
        "",
        f"Acceptance thresholds (vs. {decision['acceptance_thresholds']['quality_ceiling']}): "
        "cross-lingual Recall@5 loss <= "
        f"{decision['acceptance_thresholds']['max_cross_recall_at_5_loss']}, "
        "cross-lingual MRR loss <= "
        f"{decision['acceptance_thresholds']['max_cross_mrr_loss']}, "
        "mono-lingual Recall@5 regression <= "
        f"{decision['acceptance_thresholds']['max_mono_recall_at_5_regression']}.",
        "",
        f"Configs meeting acceptance thresholds: {decision.get('efficiency_candidates', [])}",
        "",
        f"**PRODUCTION RECOMMENDATION:** {decision['production_recommendation']}",
        "",
        "`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the "
        "actual production default regardless of the recommendation above; switching "
        "it is a separate decision outside this sprint's scope.",
        "",
    ]
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> None:
    golden_questions = load_golden_questions(args.golden_set)
    work_dir = Path(args.work_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for token in args.configs:
        config = parse_config_token(token, settings)
        print(f"Running config: {config.label()}")
        result = await run_config_benchmark(config, settings, golden_questions, work_dir)
        if not result["supported"]:
            print(f"  UNSUPPORTED (requested {result['requested_dimension']}, "
                  f"got {result['actual_dimension_returned']})")
        results.append(result)

    decision = score(results)

    output = {
        "results": results,
        "decision": decision,
        "golden_set_path": args.golden_set,
        "question_count": len(golden_questions),
    }

    (output_dir / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    report = render_markdown_report(results, decision, args.golden_set)
    (output_dir / "report.md").write_text(report)

    print(report)
    print(f"\nWritten to {output_dir}/results.json and {output_dir}/report.md")

    if args.cleanup_work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark multiple embedding model/dimension configurations"
    )
    parser.add_argument(
        "--configs", nargs="+", default=DEFAULT_CONFIGS,
        help='"model@dimension" tokens, e.g. qwen3-4b@native qwen3-4b@1024',
    )
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cleanup-work-dir", action="store_true")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
