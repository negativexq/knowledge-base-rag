"""RAGBench TechQA HOLDOUT50 over the production RAG path.

The canonical TechQA holdout ran a frozen copy of the 2026-08 pipeline
(RRF Top20 -> BGE Top5 -> SectionAware -> Luna -> validators). This asks the
same 50 frozen questions over the same 769-document corpus through what
POST /chat runs today (production ingestion and chunking, search, evidence,
answer stream, validators, derived answers and the operand resolver when
enabled), so the old and the current system can be compared.

Retrieval searches the whole TechQA corpus, as the canonical run did. The
report covers response kinds, whether a relevant document reached the
reranked top-N and the candidates, whether answers cite a relevant document,
and ACL leaks. Semantic quality is graded afterwards against the reference
answer (--scores, a CSV of qid,label) with the canonical rubric.

  python scripts/benchmarks/run_techqa_production.py --parquet PATH [--rows Q1,Q2]

--questions-from takes the frozen questions from an earlier results.jsonl
instead of the parquet (the corpus must already be ingested, --skip-ingest).
--adaptive runs the adaptive research pipeline with the settings the
MMLongBench traces use (scripts/experiments/run_adaptive_trace.py), the
evidence plan starting alongside retrieval as POST /chat does. Each question
then records its model usage, prints every span as it ends, and keeps its
spans and full forensic capture under OUT/<qid>/.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.api.chat import _scoped_retrieve
from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.evaluation.mmlongbench import response_kind
from app.evaluation.techqa import (
    all_documents,
    build_report,
    cited_sources,
    doc_file_name,
    holdout_questions,
    recorded_questions,
)
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.agent_observability import RequestUsage, load_prices, usage_scope
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.llm.research_budget import ResearchPolicy
from app.llm.research_needs import offer_plan
from app.registry.store import DocumentRegistry
from app.retrieval.report import RetrievalReport
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings
from app.shared.tracing import get_tracer, setup_tracing
from scripts.benchmarks.run_mmlongbench_pilot import (
    free_accelerator_memory,
    generation_model,
    load_checkpoint,
    save_checkpoint,
    validation_trace,
)

COLLECTION = "kb_bench_techqa"
TENANT = "bench-techqa"
OTHER_TENANT = "tenant-a"
CANONICAL = ROOT / "artifacts/ragbench/canonical"
HOLDOUT = CANONICAL / "techqa-holdout50-frozen/sample-identities.json"
CORPUS = CANONICAL / "techqa-reranker-corrected-holdout-execution-v2/01-corpus"
DATA = ROOT / "data/benchmarks/techqa-holdout50"
OUT = ROOT / "artifacts/ragbench/techqa-production-v1"
PARQUET_SHA256 = "426f360d12b5d3589b66293c3417d3686a9d69eba3e82938e93d3e1545681264"


# Span attributes worth a glance while a question runs.
STEP_ATTRIBUTES = {
    "research.model_role": "role",
    "gen_ai.usage.input_tokens": "in",
    "gen_ai.usage.output_tokens": "out",
    "research.action": "action",
    "research.route_reason": "route",
    "research.finalization": "final",
    "research.stop_reason": "stop",
    "validator.failure_codes": "fail",
    "validator.objection_count": "objections",
    "retrieve.candidate_count": "candidates",
    "rerank.top_n": "top_n",
}


class StepPrinter(SpanProcessor):
    """Print each span when it ends, offset from the question's start."""

    def __init__(self) -> None:
        self.started_ns = 0

    def on_end(self, span: ReadableSpan) -> None:
        if not self.started_ns or span.start_time is None or span.end_time is None:
            return
        attributes = span.attributes or {}
        details = " ".join(
            f"{label}={attributes[key]}"
            for key, label in STEP_ATTRIBUTES.items()
            if key in attributes and attributes[key] not in ("", [], ())
        )
        offset = (span.start_time - self.started_ns) / 1e9
        seconds = (span.end_time - span.start_time) / 1e9
        print(f"  {offset:7.1f}s +{seconds:5.1f}s  {span.name} {details}".rstrip(), flush=True)


def canonical_corpus() -> dict[str, str]:
    """The canonical holdout corpus (769 documents) by file name."""
    texts = [
        json.loads(line)["text"]
        for line in (CORPUS / "source-documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {doc_file_name(text): text for text in texts}


def write_documents(corpus: dict[str, str]) -> Path:
    folder = DATA / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in corpus.items():
        path = folder / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    for path in folder.iterdir():
        if path.name not in corpus:
            path.unlink()
    return folder


async def ingest(settings: Settings, client: QdrantClient, ollama: OllamaClient, folder: Path):
    embed_config = active_embedding_config(settings)
    store = QdrantStore(
        client=client, collection_name=COLLECTION, dense_dimension=embed_config.dimension
    )
    registry = DocumentRegistry(str(DATA / "registry.db"))

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    started = time.perf_counter()
    stats = await ingest_connector(
        LocalFilesystemConnector(folder),
        store,
        registry,
        embed_fn,
        SparseEncoder(),
        embedding_concurrency=settings.embedding_concurrency,
        pipeline_fingerprint=build_pipeline_fingerprint(embed_config, settings.chunking_config()),
        tenant_id=TENANT,
        chunking_config=settings.chunking_config(),
    )
    return {**asdict(stats), "seconds": round(time.perf_counter() - started, 1)}


def sources_of(client: QdrantClient, ids: list) -> list[str]:
    if not ids:
        return []
    found = {
        str(point.id): str((point.payload or {}).get("source_id"))
        for point in client.retrieve(COLLECTION, ids, with_payload=["source_id"])
    }
    sources: list[str] = []
    for point_id in ids:
        source = found.get(str(point_id))
        if source and source not in sources:
            sources.append(source)
    return sources


async def ask(deps, client: QdrantClient, question, usage: RequestUsage | None = None) -> dict:
    usage = usage or RequestUsage()
    with get_tracer(__name__).start_as_current_span("chat_request"), usage_scope(usage):
        raw, capture = await _ask(deps, client, question)
    raw["usage"] = usage.snapshot()
    raw["capture"] = capture
    return raw


async def _ask(deps, client: QdrantClient, question) -> tuple[dict, ForensicCapture]:
    context = RetrievalContext(tenant_id=TENANT)
    report = RetrievalReport()
    # Benchmark text, not user data: keep the raw output so a blocked answer
    # can be told apart from a wrong one.
    report.forensic_capture = ForensicCapture.create(question.question, raw_text=True)
    started = time.perf_counter()
    offer = None
    if deps.agentic_rag_enabled and deps.plan_prefetch_fn is not None:
        # As POST /chat does: the evidence plan runs alongside retrieval.
        offer = offer_plan(
            question.question, asyncio.create_task(deps.plan_prefetch_fn(question.question))
        )
    results = await deps.search_fn(question.question, context, report)
    stages = report.forensic_capture.record["stages"]
    candidate_ids = stages.get("reranker", {}).get("input_candidate_ids", [])
    blocks = await deps.evidence_fn(results, context) if deps.evidence_fn else results
    answer, metadata, validation = "", {}, {}
    clarification = None
    comparison = []
    token = set_current_capture(report.forensic_capture)
    try:
        # The request's own retriever (ACL, evidence assembly and the
        # anchored/literal search modes research tools use), as in the API.
        retrieve = _scoped_retrieve(deps, context, {})
        extra = (
            {"retrieve": retrieve}
            if (deps.operand_resolver_enabled or deps.agentic_rag_enabled)
            else {}
        )
        if deps.agentic_rag_enabled and deps.documents_factory:
            extra["documents"] = deps.documents_factory(context, None)
        async for event in deps.stream_fn(question.question, blocks, **extra):
            if event["type"] == "token":
                answer += event["content"]
            elif event["type"] == "clarification":
                clarification = {k: v for k, v in event.items() if k != "type"}
                validation = {
                    "abstain": True,
                    "passed": True,
                    "application_forced_abstention": False,
                }
            elif event["type"] == "comparison":
                comparison = event["rows"]
            elif event["type"] == "evidence_update":
                blocks = event["blocks"]
            elif event["type"] == "metadata":
                metadata = event
            elif event["type"] == "security_validation":
                validation = event
    finally:
        reset_current_capture(token)
        if offer is not None:
            await offer.close()
    seconds = round(time.perf_counter() - started, 1)
    leaked = await deps.search_fn(
        question.question, RetrievalContext(tenant_id=OTHER_TENANT), RetrievalReport()
    )
    units = metadata.get("support_units") or []
    top: list[str] = []
    for result in results:
        if result.payload["source_id"] not in top:
            top.append(result.payload["source_id"])
    return {
        "qid": question.qid,
        "row_idx": question.row_idx,
        "question": question.question,
        "reference": question.reference,
        "relevant_sources": list(question.relevant_sources),
        "answer": answer,
        "clarification": clarification,
        "comparison": comparison,
        "abstain": validation.get("abstain"),
        "application_forced_abstention": validation.get("application_forced_abstention"),
        "passed": validation.get("passed"),
        "validator_failure_codes": validation.get("validator_failure_codes"),
        "top_sources": top,
        "candidate_sources": sources_of(client, candidate_ids),
        "cited_sources": cited_sources(answer, units),
        "acl_leaks": len(leaked),
        "seconds": seconds,
        "trace": validation_trace(report.forensic_capture.record.get("stages", {})),
    }, report.forensic_capture


def read_scores(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8") as handle:
        return {row["qid"]: row["label"].strip().upper() for row in csv.DictReader(handle)}


def pct(metric: dict) -> str:
    if metric["rate"] is None:
        return "–"
    return f"{metric['rate'] * 100:.0f}% ({round(metric['rate'] * metric['n'])}/{metric['n']})"


def write_markdown(report: dict, meta: dict, path: Path) -> None:
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(report["response_kinds"].items()))
    lines = [
        "# TechQA HOLDOUT50 over the production path",
        "",
        f"{report['questions']} frozen holdout questions over the canonical "
        f"{meta['documents']}-document TechQA corpus, production ingestion and chat path, "
        f"tenant `{TENANT}`, model `{meta['model']}`, reranker "
        f"{report['candidate_k']}/{report['top_n']}, whole-corpus retrieval. Flags: "
        + ", ".join(f"{k}={v}" for k, v in meta["flags"].items())
        + ".",
        "",
    ]
    semantic = report["semantic"]
    if semantic:
        counts = semantic["counts"]
        lines += [
            "| Outcome | Result |",
            "| --- | ---: |",
            f"| Useful (correct + partial) | {semantic['useful_rate'] * 100:.0f}% "
            f"({counts.get('CORRECT', 0) + counts.get('PARTIAL', 0)}/{report['questions']}) |",
            f"| Correct | {counts.get('CORRECT', 0)} |",
            f"| Partial | {counts.get('PARTIAL', 0)} |",
            f"| Materially incorrect | {semantic['incorrect_rate'] * 100:.0f}% "
            f"({counts.get('INCORRECT', 0)}) |",
            f"| Unavailable | {semantic['unavailable_rate'] * 100:.0f}% "
            f"({counts.get('UNAVAILABLE', 0)}) |",
            "",
        ]
    lines += [
        f"- Relevant document in the reranked top-{report['top_n']}: "
        f"{pct(report['retrieval_hit_top'])}; in the {report['candidate_k']} candidates: "
        f"{pct(report['retrieval_hit_candidates'])} (questions RAGBench marks with a "
        "relevant document)",
        f"- Answers citing a relevant document: {pct(report['citation_on_relevant'])}",
        f"- Response kinds: {kinds}",
        f"- ACL leaks (same questions as `{OTHER_TENANT}`): {report['acl_leaks']}",
        f"- Ingestion: {meta['ingest']['chunks_upserted']} chunks in "
        f"{meta['ingest']['seconds']} s; questions: median {report['median_seconds']} s each.",
        "",
        "Semantic labels follow the canonical blind-review rubric against RAGBench's "
        "reference response; they were assigned by one reviewer after the run"
        + (f" ({meta['scores']})." if meta.get("scores") else " (not yet graded)."),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def adaptive_settings(base: Settings) -> Settings:
    """The adaptive pipeline as run_adaptive_trace.py configures it."""
    return Settings(
        **{
            **base.model_dump(),
            "generation_provider": "openai",
            "adaptive_rag_enabled": True,
            "adaptive_fast_path_enabled": True,
            "adaptive_evidence_needs_enabled": True,
            "adaptive_plan_prefetch_enabled": True,
            "agentic_rag_enabled": False,
            "derived_answers_enabled": True,
            "operand_resolver_enabled": True,
            "visual_answers_enabled": True,
            "agentic_reasoning": "low",
            "adaptive_final_reasoning": "medium",
            "adaptive_extraction_reasoning": "low",
            "agentic_max_requests": 10,
            "agentic_max_tokens": 120000,
            "agentic_timeout_seconds": 240,
            "agentic_research_policy": ResearchPolicy(
                max_research_requests=6,
                max_tool_attempts=6,
                max_no_progress=2,
                model_timeout_seconds=60,
                tool_timeout_seconds=60,
                finalize_reserve_seconds=60,
            ),
        }
    )


async def run(settings: Settings, questions, skip_ingest: bool, checkpoint: Path):
    from app.wiring import build_chat_dependencies

    provider = setup_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    spans = InMemorySpanExporter()
    printer = StepPrinter()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    provider.add_span_processor(printer)
    client = QdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    deps, chat_provider = build_chat_dependencies(
        settings, client, ollama, SparseEncoder(), COLLECTION
    )
    try:
        corpus = canonical_corpus()
        ingest_stats = {"chunks_upserted": "existing", "seconds": 0}
        if not skip_ingest:
            ingest_stats = await ingest(settings, client, ollama, write_documents(corpus))
            print(f"ingested: {ingest_stats}", flush=True)
        done = load_checkpoint(checkpoint)
        raws = []
        for index, question in enumerate(questions, 1):
            if question.row_idx in done:
                raws.append(done[question.row_idx])
                continue
            print(f"[{index}/{len(questions)}] {question.qid} started", flush=True)
            spans.clear()
            printer.started_ns = time.time_ns()
            raw = await ask(
                deps, client, question, RequestUsage(load_prices(settings.model_pricing_json))
            )
            printer.started_ns = 0
            folder = checkpoint.parent / question.qid
            folder.mkdir(parents=True, exist_ok=True)
            raw.pop("capture").write(str(folder / "03-captures/records"))
            finished = [json.loads(span.to_json()) for span in spans.get_finished_spans()]
            (folder / "spans.json").write_text(json.dumps(finished, indent=2) + "\n")
            raws.append(raw)
            save_checkpoint(checkpoint, raw)
            free_accelerator_memory()
            print(
                f"[{index}/{len(questions)}] {question.qid} {raw['seconds']}s "
                f"kind={response_kind(raw)}",
                flush=True,
            )
    finally:
        await ollama.aclose()
        await chat_provider.aclose()
        client.close()
    return raws, ingest_stats, len(corpus)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--parquet", type=Path, help="RAGBench techqa test parquet")
    source.add_argument(
        "--questions-from", type=Path, help="an earlier results.jsonl with the frozen questions"
    )
    parser.add_argument("--adaptive", action="store_true", help="adaptive research pipeline")
    parser.add_argument("--rows", help="run only these question ids, e.g. techqa_DEV_Q252")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--from-results", action="store_true", help="re-score results.jsonl")
    parser.add_argument("--scores", type=Path, help="CSV qid,label with the semantic grades")
    args = parser.parse_args()

    ids = json.loads(HOLDOUT.read_text(encoding="utf-8"))["selected_dataset_ids"]
    if args.rows:
        wanted = set(args.rows.split(","))
        ids = [qid for qid in ids if qid in wanted]
    digest = None
    if args.questions_from:
        if not args.skip_ingest:
            raise SystemExit("--questions-from has no documents to ingest; pass --skip-ingest")
        recorded = [
            json.loads(line)
            for line in args.questions_from.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        questions = recorded_questions(recorded, ids)
    else:
        digest = hashlib.sha256(args.parquet.read_bytes()).hexdigest()
        if digest != PARQUET_SHA256:
            raise SystemExit(f"parquet sha256 {digest} is not the pinned {PARQUET_SHA256}")
        rows = pq.read_table(args.parquet).to_pylist()
        questions = holdout_questions(rows, ids)
        corpus = canonical_corpus()
        missing = [
            q.qid
            for q in questions
            for name in all_documents([rows[q.row_idx]])
            if name not in corpus
        ]
        if missing:
            raise SystemExit(f"questions with documents outside the canonical corpus: {missing}")

    settings = adaptive_settings(Settings()) if args.adaptive else Settings()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if args.from_results:
        raws = [
            json.loads(line)
            for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        meta = json.loads((out / "report.json").read_text(encoding="utf-8"))["meta"]
    else:
        raws, ingest_stats, documents = await run(
            settings, questions, args.skip_ingest, out / "results.partial.jsonl"
        )
        meta = {
            "dataset": "RAGBench TechQA HOLDOUT50",
            "parquet_sha256": digest,
            "questions_from": str(args.questions_from) if args.questions_from else None,
            "documents": documents,
            "collection": COLLECTION,
            "tenant": TENANT,
            "model": generation_model(settings),
            "ingest": ingest_stats,
            "retrieval_scope": "open_corpus",
            "top_n": settings.reranker_top_n,
            "candidate_k": settings.reranker_candidate_k,
            "flags": {
                "AGENTIC_RAG_ENABLED": settings.agentic_rag_enabled,
                "AGENTIC_MODE": settings.agentic_mode,
                "ADAPTIVE_RAG_ENABLED": settings.adaptive_rag_enabled,
                "DERIVED_ANSWERS_ENABLED": settings.derived_answers_enabled,
                "OPERAND_RESOLVER_ENABLED": settings.operand_resolver_enabled,
                "VISUAL_ANSWERS_ENABLED": settings.visual_answers_enabled,
            },
        }
        (out / "results.jsonl").write_text(
            "".join(json.dumps(raw, ensure_ascii=False) + "\n" for raw in raws), encoding="utf-8"
        )
        (out / "results.partial.jsonl").unlink(missing_ok=True)

    scores = read_scores(args.scores)
    if args.scores:
        meta["scores"] = args.scores.name
    report = build_report(
        questions,
        raws,
        top_n=meta["top_n"],
        candidate_k=meta["candidate_k"],
        scores=scores,
    )
    per_question = [
        {
            "qid": raw["qid"],
            "response_kind": response_kind(raw),
            "relevant_in_top": bool(set(raw["relevant_sources"]) & set(raw["top_sources"])),
            "cited_relevant": bool(set(raw["relevant_sources"]) & set(raw["cited_sources"])),
            "semantic": (scores or {}).get(raw["qid"]),
        }
        for raw in raws
    ]
    (out / "report.json").write_text(
        json.dumps({"meta": meta, **report, "per_question": per_question}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, meta, out / "report.md")
    print((out / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
