"""MMLongBench-Doc pilot over the production RAG path.

Ingests the pinned pilot PDFs with the production connector ingestion into
their own collection and tenant, then asks every pinned question through the
same search, evidence and answer stream POST /chat uses, and reports each
stage separately, sliced by the question's evidence type:

- ingestion: every evidence page produced at least one chunk;
- retrieval: an evidence page of the right document is among the reranked
  top-N, and among the pre-rerank candidates;
- generation: the answer contains the gold answer (lenient, deterministic)
  and cites at least one unit on an evidence page;
- answerability: unanswerable questions are refused, answerable ones are
  answered;
- ACL: the same question asked as another tenant must retrieve nothing.

Run setup_mmlongbench_pilot.py first. Questions run one at a time.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq
from qdrant_client import QdrantClient, models

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.forensic_capture import ForensicCapture
from app.evaluation.mmlongbench import (
    QuestionOutcome,
    answer_matches,
    build_report,
    cited_pages,
    load_manifest,
    page_hit,
    parse_question,
)
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.report import RetrievalReport
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings
from app.shared.slug import slugify
from scripts.benchmarks.setup_mmlongbench_pilot import MANIFEST, data_dir

COLLECTION = "kb_bench_mmlongbench"
TENANT = "bench-mmlongbench"
OTHER_TENANT = "tenant-a"
OUT = ROOT / "artifacts" / "mmlongbench-pilot"


def source_id_for(doc_id: str) -> str:
    return slugify(doc_id, strip_extension=False)


async def ingest(
    settings: Settings, client: QdrantClient, ollama: OllamaClient, root: Path
) -> dict:
    embed_config = active_embedding_config(settings)
    store = QdrantStore(
        client=client, collection_name=COLLECTION, dense_dimension=embed_config.dimension
    )
    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    registry = DocumentRegistry(str(work / "registry.db"))

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    started = time.perf_counter()
    stats = await ingest_connector(
        LocalFilesystemConnector(root / "documents"),
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


def chunked_pages(client: QdrantClient) -> dict[str, dict[int, int]]:
    """Characters of chunk text per (source_id, page) for the bench tenant."""
    pages: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    offset = None
    while True:
        points, offset = client.scroll(
            COLLECTION,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="tenant_id", match=models.MatchValue(value=TENANT))]
            ),
            with_payload=["source_id", "page_number", "text"],
            limit=256,
            offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            pages[payload["source_id"]][int(payload["page_number"])] += len(payload.get("text", ""))
        if offset is None:
            return pages


def locations(client: QdrantClient, ids: list) -> list[tuple[str, int]]:
    if not ids:
        return []
    points = {
        str(point.id): point.payload or {}
        for point in client.retrieve(COLLECTION, ids, with_payload=["source_id", "page_number"])
    }
    return [
        (points[str(i)]["source_id"], int(points[str(i)]["page_number"]))
        for i in ids
        if str(i) in points
    ]


async def ask(deps, client: QdrantClient, question) -> tuple[QuestionOutcome, dict]:
    context = RetrievalContext(tenant_id=TENANT)
    report = RetrievalReport()
    report.forensic_capture = ForensicCapture.create(question.question, raw_text=False)
    started = time.perf_counter()
    results = await deps.search_fn(question.question, context, report)
    stages = report.forensic_capture.record["stages"]
    candidate_ids = stages.get("reranker", {}).get("input_candidate_ids", [])
    candidates = locations(client, candidate_ids)
    top = [(r.payload["source_id"], int(r.payload["page_number"])) for r in results]

    blocks = await deps.evidence_fn(results, context) if deps.evidence_fn else results
    answer, metadata, validation = "", {}, {}
    async for event in deps.stream_fn(question.question, blocks):
        if event["type"] == "token":
            answer += event["content"]
        elif event["type"] == "metadata":
            metadata = event
        elif event["type"] == "security_validation":
            validation = event
    seconds = round(time.perf_counter() - started, 1)

    leaked = await deps.search_fn(
        question.question, RetrievalContext(tenant_id=OTHER_TENANT), RetrievalReport()
    )

    source_id = source_id_for(question.doc_id)
    answered = bool(answer.strip()) and not validation.get("abstain", False)
    cited = cited_pages(answer, metadata.get("support_units") or [])
    if question.answerable:
        retrieved_top = page_hit(top, source_id, question.evidence_pages)
        retrieved_candidates = page_hit(candidates, source_id, question.evidence_pages)
        correct = answered and answer_matches(answer, question.answer, question.answer_format)
        citation = page_hit(cited, source_id, question.evidence_pages) if answered else None
    else:
        retrieved_top = retrieved_candidates = correct = citation = None

    outcome = QuestionOutcome(
        question=question,
        ingested=None,  # filled in from the chunk scan
        retrieved_top_k=retrieved_top,
        retrieved_candidates=retrieved_candidates,
        answered=answered,
        correct=correct,
        citation_on_evidence=citation,
        acl_leaks=len(leaked),
    )
    raw = {
        "row_idx": question.row_idx,
        "doc_id": question.doc_id,
        "evidence_pages": list(question.evidence_pages),
        "evidence_types": list(question.evidence_types),
        "answer_format": question.answer_format,
        "gold": question.answer,
        "answer": answer,
        "abstain": validation.get("abstain"),
        "passed": validation.get("passed"),
        "validator_failure_codes": validation.get("validator_failure_codes"),
        "generation": validation.get("generation"),
        "generation_skipped": metadata.get("generation_skipped"),
        "prompt_fit": metadata.get("prompt_fit"),
        "top_pages": top,
        "candidate_pages": candidates,
        "cited_pages": cited,
        "acl_leaks": len(leaked),
        "seconds": seconds,
    }
    return outcome, raw


def write_markdown(report: dict, meta: dict, path: Path) -> None:
    top_n, candidate_k = meta["top_n"], meta["candidate_k"]

    def cell(metric: dict) -> str:
        if metric["rate"] is None:
            return "–"
        return f"{metric['rate'] * 100:.0f}% ({round(metric['rate'] * metric['n'])}/{metric['n']})"

    rows = [("all", report["overall"])] + list(report["slices"].items())
    lines = [
        "# MMLongBench-Doc pilot",
        "",
        f"{meta['questions']} questions over {meta['documents']} PDFs "
        f"(dataset revision `{meta['revision'][:8]}`), production path, tenant `{TENANT}`, "
        f"model `{meta['model']}`. Rates are over answerable questions; a question with "
        "several evidence types counts in each.",
        "",
        f"| Slice | Questions | Ingestion | Hit@{top_n} | Hit@{candidate_k} | Answer | Citation |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in rows:
        ingestion = cell(metrics["ingestion_evidence_page_coverage"])
        lines.append(
            f"| {name} | {metrics['questions']} | {ingestion} "
            f"| {cell(metrics[f'retrieval_hit_at_{top_n}'])} "
            f"| {cell(metrics[f'retrieval_hit_at_{candidate_k}'])} "
            f"| {cell(metrics['answer_accuracy'])} | {cell(metrics['citation_accuracy'])} |"
        )
    refused = cell(report["answerability"]["unanswerable_correctly_refused"])
    coverage = cell(report["answerability"]["answerable_coverage"])
    ingest = meta["ingest"]
    lines += [
        "",
        f"- Unanswerable correctly refused: {refused}",
        f"- Answerable questions answered (coverage): {coverage}",
        f"- ACL leaks (same questions as `{OTHER_TENANT}`): {report['acl_leaks']}",
        f"- Ingestion: {ingest['chunks_upserted']} chunks in {ingest['seconds']} s; "
        f"questions: median {meta['median_seconds']} s each.",
        "",
        "Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), "
        "not the benchmark's official LLM-extracted score.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    from app.wiring import build_chat_dependencies

    settings = Settings()
    manifest = load_manifest(MANIFEST)
    root = data_dir(manifest.revision)
    table = pq.read_table(root / "data" / "train-00000-of-00001.parquet").to_pylist()
    questions = [parse_question(table[row], row) for row in manifest.question_rows]

    client = QdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    deps, chat_provider = build_chat_dependencies(
        settings, client, ollama, SparseEncoder(), COLLECTION
    )
    try:
        ingest_stats = {"chunks_upserted": "existing", "seconds": 0}
        if not args.skip_ingest:
            ingest_stats = await ingest(settings, client, ollama, root)
            print(f"ingested: {ingest_stats}", flush=True)
        pages = chunked_pages(client)

        outcomes, raws = [], []
        for index, question in enumerate(questions, 1):
            outcome, raw = await ask(deps, client, question)
            covered = pages.get(source_id_for(question.doc_id), {})
            ingested = (
                all(covered.get(page, 0) > 0 for page in question.evidence_pages)
                if question.answerable and question.evidence_pages
                else None
            )
            outcome = QuestionOutcome(**{**outcome.__dict__, "ingested": ingested})
            raw["evidence_page_chars"] = {p: covered.get(p, 0) for p in question.evidence_pages}
            outcomes.append(outcome)
            raws.append(raw)
            print(
                f"[{index}/{len(questions)}] row {question.row_idx} {raw['seconds']}s "
                f"answered={outcome.answered} correct={outcome.correct} "
                f"hit={outcome.retrieved_top_k}",
                flush=True,
            )
    finally:
        await ollama.aclose()
        await chat_provider.aclose()
        client.close()

    top_n, candidate_k = settings.reranker_top_n, settings.reranker_candidate_k
    report = build_report(outcomes, top_k=top_n, candidate_k=candidate_k)
    seconds = sorted(raw["seconds"] for raw in raws)
    meta = {
        "dataset": manifest.dataset,
        "revision": manifest.revision,
        "documents": len({q.doc_id for q in questions}),
        "questions": len(questions),
        "collection": COLLECTION,
        "tenant": TENANT,
        "model": settings.ollama_model,
        "top_n": top_n,
        "candidate_k": candidate_k,
        "ingest": ingest_stats,
        "median_seconds": seconds[len(seconds) // 2],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.jsonl").write_text(
        "".join(json.dumps(raw, ensure_ascii=False) + "\n" for raw in raws), encoding="utf-8"
    )
    per_question = [
        {
            "row_idx": o.question.row_idx,
            "doc_id": o.question.doc_id,
            "evidence_types": list(o.question.evidence_types),
            "answerable": o.question.answerable,
            "ingested": o.ingested,
            "hit_top": o.retrieved_top_k,
            "hit_candidates": o.retrieved_candidates,
            "answered": o.answered,
            "correct": o.correct,
            "citation_on_evidence": o.citation_on_evidence,
            "acl_leaks": o.acl_leaks,
        }
        for o in outcomes
    ]
    (OUT / "report.json").write_text(
        json.dumps({"meta": meta, **report, "per_question": per_question}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, meta, OUT / "report.md")
    print((OUT / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
