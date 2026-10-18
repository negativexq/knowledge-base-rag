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

It also records where a wrong answer lost the gold answer: whether the gold
answer appears in the evidence pages' chunk text and in the evidence the
model was given. With --evidence gold_page the model gets the evidence pages'
chunks instead of the retrieved evidence (same generation and validation),
which separates retrieval and assembly losses from generation losses.

Run setup_mmlongbench_pilot.py first. Questions run one at a time.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
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
from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.evaluation.mmlongbench import (
    QuestionOutcome,
    build_report,
    cited_pages,
    corrected_rows,
    gold_visible,
    load_manifest,
    outcome_from_result,
    parse_question,
    payload_pages,
    response_kind,
)
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
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


def collection_for(manifest_path: Path, chunking_mode: str = "baseline") -> str:
    """The pilot keeps its collection; another manifest gets its own,
    named after its folder (artifacts/mmlongbench-v2 → kb_bench_mmlongbench_v2).
    A chunking challenger gets its own index next to the baseline's."""
    if Path(manifest_path).resolve() == MANIFEST.resolve():
        name = "kb_bench_mmlongbench"
    else:
        name = "kb_bench_" + Path(manifest_path).parent.name.replace("-", "_")
    return name if chunking_mode == "baseline" else f"{name}_{chunking_mode}"


def manifest_documents(root: Path, manifest, collection: str) -> Path:
    """A documents folder for one index holding only the manifest's PDFs, as
    relative links into the shared download folder (so it also works through
    a container bind mount)."""
    folder = root / "work" / collection / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {
        Path(f.path).name: root / f.path for f in manifest.files if f.path.startswith("documents/")
    }
    for link in folder.iterdir():
        if link.name not in wanted:
            link.unlink()
    for name, target in wanted.items():
        link = folder / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(os.path.relpath(target, folder))
    return folder


def disable_generation(provider) -> None:
    """Answer every question with an abstention instead of calling the model,
    for a run that measures retrieval and evidence assembly only (no key, no
    model variance). Answer metrics of such a run are not meaningful."""

    async def abstain(messages, **kwargs) -> str:
        return json.dumps({"answer_parts": [], "abstain": True})

    provider.chat_json = abstain


def save_checkpoint(path: Path, raw: dict) -> None:
    """Append one finished question so a killed run can resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(raw, ensure_ascii=False) + "\n")


def load_checkpoint(path: Path) -> dict[int, dict]:
    """Finished questions by row; a line cut off by the kill is dropped."""
    if not path.exists():
        return {}
    done = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        done[raw["row_idx"]] = raw
    return done


def free_accelerator_memory() -> None:
    """Return the MPS allocator's cache between questions. Reranker inputs
    vary in length up to max_length, and the cache otherwise grows until a
    16 GB Mac swaps (13 GB after 70 questions)."""
    import torch

    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


OUT_BY_EVIDENCE = {
    "retrieved": OUT,
    "gold_page": ROOT / "artifacts" / "mmlongbench-pilot-gold-page",
}


def generation_model(settings: Settings) -> str:
    return {
        "ollama": settings.ollama_model,
        "claude": settings.claude_model,
        "openai": settings.openai_model,
    }[settings.generation_provider]


def source_id_for(doc_id: str) -> str:
    return slugify(doc_id, strip_extension=False)


async def ingest(
    settings: Settings, client: QdrantClient, ollama: OllamaClient, root: Path, manifest
) -> dict:
    embed_config = active_embedding_config(settings)
    store = QdrantStore(
        client=client, collection_name=COLLECTION, dense_dimension=embed_config.dimension
    )
    documents = manifest_documents(root, manifest, COLLECTION)
    registry = DocumentRegistry(str(documents.parent / "registry.db"))

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    started = time.perf_counter()
    stats = await ingest_connector(
        LocalFilesystemConnector(documents),
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
            with_payload=["source_id", "page_number", "page_end", "text"],
            limit=256,
            offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            for page in payload_pages(payload):
                pages[payload["source_id"]][page] += len(payload.get("text", ""))
        if offset is None:
            return pages


def gold_page_chunks(client: QdrantClient, question) -> list[SearchResult]:
    """The question's evidence pages as indexed chunks, in page order."""
    pages = set(question.evidence_pages)
    must = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=TENANT)),
        models.FieldCondition(
            key="source_id", match=models.MatchValue(value=source_id_for(question.doc_id))
        ),
    ]
    chunks, offset = [], None
    while True:
        points, offset = client.scroll(
            COLLECTION,
            scroll_filter=models.Filter(must=must),
            with_payload=True,
            limit=256,
            offset=offset,
        )
        chunks += [
            SearchResult(score=1.0, id=str(point.id), payload=dict(point.payload or {}))
            for point in points
            if pages & set(payload_pages(point.payload or {}))
        ]
        if offset is None:
            break
    return sorted(
        chunks,
        key=lambda c: (c.payload["page_number"], (c.payload.get("char_range") or [0])[0]),
    )


def locations(client: QdrantClient, ids: list) -> list[tuple[str, int]]:
    if not ids:
        return []
    points = {
        str(point.id): point.payload or {}
        for point in client.retrieve(
            COLLECTION, ids, with_payload=["source_id", "page_number", "page_end"]
        )
    }
    return [
        (points[str(i)]["source_id"], page)
        for i in ids
        if str(i) in points
        for page in payload_pages(points[str(i)])
    ]


def validation_trace(stages: dict) -> dict:
    """What the model returned, the units it cited, what the critical-value
    validator decided about it and what the operand resolver and the visual
    path tried, from the forensic capture's stages."""
    validation = stages.get("support_id_validation", {})
    return {
        "raw_model_output": stages.get("generation", {}).get("raw_model_output"),
        "critical_validator": validation.get("critical_validator"),
        "cited_units": validation.get("cited_units"),
        "operand_resolver": stages.get("operand_resolver"),
        **({"agentic": stages["agentic"]} if "agentic" in stages else {}),
        **({"escalation": stages["escalation"]} if "escalation" in stages else {}),
        "visual_answer": stages.get("visual_answer"),
    }


def select_rows(questions, rows: str | None):
    """The questions named by --rows ("210,212"), or all of them."""
    if not rows:
        return questions
    wanted = {int(row) for row in rows.split(",")}
    return [question for question in questions if question.row_idx in wanted]


def retrieval_scope(doc_id: str, open_corpus: bool) -> list[str] | None:
    """MMLongBench is single-document QA: a question comes with its PDF and
    says "the document". The protocol scopes retrieval to that PDF, as a
    user asking about one document would; --open-corpus searches every
    indexed PDF instead (the harder, non-protocol setting)."""
    return None if open_corpus else [source_id_for(doc_id)]


async def ask(
    deps, client: QdrantClient, question, evidence: str = "retrieved", open_corpus: bool = False
) -> dict:
    context = RetrievalContext(tenant_id=TENANT)
    report = RetrievalReport()
    # Benchmark text, not user data: the capture keeps the model's raw output
    # so a blocked answer can be told apart from a wrong one.
    report.forensic_capture = ForensicCapture.create(question.question, raw_text=True)
    started = time.perf_counter()
    scope = retrieval_scope(question.doc_id, open_corpus)
    results = await deps.search_fn(
        question.question, context, report, **({"source_ids": scope} if scope else {})
    )
    stages = report.forensic_capture.record["stages"]
    candidate_ids = stages.get("reranker", {}).get("input_candidate_ids", [])
    candidates = locations(client, candidate_ids)
    top = [(r.payload["source_id"], page) for r in results for page in payload_pages(r.payload)]

    gold_chunks = gold_page_chunks(client, question) if question.answerable else []
    if evidence == "gold_page" and question.answerable:
        blocks = gold_chunks
    else:
        # An unanswerable question has no evidence page; with nothing to
        # read, a refusal would be free. It gets what retrieval found.
        evidence = "retrieved"
        blocks = await deps.evidence_fn(results, context) if deps.evidence_fn else results
    answer, metadata, validation = "", {}, {}
    clarification = None
    comparison = []
    token = set_current_capture(report.forensic_capture)
    try:

        from app.api.chat import _scoped_retrieve

        retrieve = _scoped_retrieve(deps, context, {"source_ids": scope} if scope else {})

        extra = (
            {"retrieve": retrieve}
            if (deps.operand_resolver_enabled or deps.agentic_rag_enabled)
            else {}
        )
        if deps.agentic_rag_enabled and deps.documents_factory:
            extra["documents"] = deps.documents_factory(context, scope or None)
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
    seconds = round(time.perf_counter() - started, 1)

    leaked = await deps.search_fn(
        question.question, RetrievalContext(tenant_id=OTHER_TENANT), RetrievalReport()
    )

    units = metadata.get("support_units") or []
    cited = cited_pages(answer, units)
    seen = cited_pages(" ".join(f"[{unit['support_id']}]" for unit in units), units)
    raw = {
        "row_idx": question.row_idx,
        "doc_id": question.doc_id,
        "evidence_pages": list(question.evidence_pages),
        "evidence_types": list(question.evidence_types),
        "answer_format": question.answer_format,
        "gold": question.answer,
        "answer": answer,
        "clarification": clarification,
        "comparison": comparison,
        "abstain": validation.get("abstain"),
        "application_forced_abstention": validation.get("application_forced_abstention"),
        "passed": validation.get("passed"),
        "validator_failure_codes": validation.get("validator_failure_codes"),
        "generation": validation.get("generation"),
        "generation_skipped": metadata.get("generation_skipped"),
        "prompt_fit": metadata.get("prompt_fit"),
        "top_pages": top,
        "candidate_pages": candidates,
        "cited_pages": cited,
        "seen_pages": seen,
        "evidence": evidence,
        "gold_in_page_text": gold_visible(
            question, (c.payload.get("text", "") for c in gold_chunks)
        ),
        "gold_in_evidence": gold_visible(question, (b.payload.get("text", "") for b in blocks)),
        "acl_leaks": len(leaked),
        "seconds": seconds,
        "trace": validation_trace(report.forensic_capture.record.get("stages", {})),
    }
    return raw


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
        f"- Evidence given to the model: {meta.get('evidence', 'retrieved')}",
        f"- Retrieval scope: {meta.get('retrieval_scope', 'open_corpus')}",
        f"- Labels: {meta.get('labels', 'v1')}",
        f"- Gold answer in the evidence pages' text: "
        f"{cell(report['overall']['gold_in_page_text'])}; in the evidence the model saw: "
        f"{cell(report['overall']['gold_in_evidence'])}",
        f"- An evidence page among the pages the model was shown: "
        f"{cell(report['overall']['evidence_page_seen'])}",
        "- Wrong answers by the stage that lost the gold answer: "
        + (", ".join(f"{stage} {n}" for stage, n in report["loss_stages"].items()) or "none"),
        "- Response kinds: "
        + ", ".join(f"{kind} {count}" for kind, count in sorted(report["response_kinds"].items())),
        f"- Ingestion: {ingest['chunks_upserted']} chunks in {ingest['seconds']} s; "
        f"questions: median {meta['median_seconds']} s each.",
        "",
        "Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), "
        "not the benchmark's official LLM-extracted score. Gold visibility uses the same "
        "match, so an answer that has to be computed counts as not in the text.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def score(questions, raws: list[dict]) -> list[QuestionOutcome]:
    by_row = {raw["row_idx"]: raw for raw in raws}
    return [
        outcome_from_result(q, by_row[q.row_idx], source_id=source_id_for(q.doc_id))
        for q in questions
    ]


async def run_questions(
    settings: Settings,
    root: Path,
    manifest,
    questions,
    skip_ingest: bool,
    evidence: str = "retrieved",
    generate: bool = True,
    checkpoint: Path | None = None,
    open_corpus: bool = False,
):
    from app.wiring import build_chat_dependencies

    client = QdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    # Page images for visual answers come from the manifest's own PDFs.
    settings = settings.model_copy(
        update={
            "filesystem_root_path": str(manifest_documents(root, manifest, COLLECTION)),
            "filesystem_tenant_id": TENANT,
            "agentic_rag_enabled": settings.agentic_rag_enabled and generate,
        }
    )
    deps, chat_provider = build_chat_dependencies(
        settings, client, ollama, SparseEncoder(), COLLECTION
    )
    if not generate:
        disable_generation(chat_provider)
    try:
        ingest_stats = {"chunks_upserted": "existing", "seconds": 0}
        if not skip_ingest:
            ingest_stats = await ingest(settings, client, ollama, root, manifest)
            print(f"ingested: {ingest_stats}", flush=True)
        pages = chunked_pages(client)
        done = load_checkpoint(checkpoint) if checkpoint else {}
        raws = []
        for index, question in enumerate(questions, 1):
            if question.row_idx in done:
                raws.append(done[question.row_idx])
                continue
            raw = await ask(deps, client, question, evidence, open_corpus)
            covered = pages.get(source_id_for(question.doc_id), {})
            raw["evidence_page_chars"] = {p: covered.get(p, 0) for p in question.evidence_pages}
            raws.append(raw)
            if checkpoint:
                save_checkpoint(checkpoint, raw)
            free_accelerator_memory()
            print(
                f"[{index}/{len(questions)}] row {question.row_idx} {raw['seconds']}s "
                f"kind={response_kind(raw)}",
                flush=True,
            )
    finally:
        await ollama.aclose()
        await chat_provider.aclose()
        client.close()
    return raws, ingest_stats


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument(
        "--from-results",
        action="store_true",
        help="re-score the saved results.jsonl without asking the model again",
    )
    parser.add_argument(
        "--evidence",
        choices=sorted(OUT_BY_EVIDENCE),
        default="retrieved",
        help="give the model the retrieved evidence, or the evidence pages' chunks",
    )
    parser.add_argument("--out", type=Path, help="write results here instead of the default")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST,
        help="question set; a manifest other than the pilot gets its own collection",
    )
    parser.add_argument("--rows", help="run only these dataset rows, e.g. 210,212")
    parser.add_argument(
        "--open-corpus",
        action="store_true",
        help="search every indexed PDF instead of the question's own (not the protocol)",
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="index the manifest's PDFs and stop (run it where OCR is installed)",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="corrected questions and gold answers (MMLongBench-Doc-V2 samples.json)",
    )
    parser.add_argument(
        "--no-generation",
        action="store_true",
        help="measure retrieval and evidence only; every answer is an abstention",
    )
    args = parser.parse_args()
    global COLLECTION
    COLLECTION = collection_for(args.manifest, Settings().chunking_mode)
    if args.out:
        out = args.out
    elif Path(args.manifest).resolve() == MANIFEST.resolve():
        out = OUT_BY_EVIDENCE[args.evidence]
    else:
        out = Path(args.manifest).parent / f"results-{args.evidence.replace('_', '-')}"

    settings = Settings()
    manifest = load_manifest(args.manifest)
    root = data_dir(manifest.revision)
    table = pq.read_table(root / "data" / "train-00000-of-00001.parquet").to_pylist()
    if args.labels:
        corrected = corrected_rows(table, json.loads(args.labels.read_text(encoding="utf-8")))
        dropped = [row for row in manifest.question_rows if corrected[row] is None]
        if dropped:
            raise SystemExit(f"rows dropped by the corrected labels: {dropped}")
        table = corrected
    questions = select_rows(
        [parse_question(table[row], row) for row in manifest.question_rows], args.rows
    )

    if args.ingest_only:
        client = QdrantClient(url=settings.qdrant_url)
        ollama = OllamaClient(base_url=settings.ollama_base_url)
        try:
            print(COLLECTION, await ingest(settings, client, ollama, root, manifest), flush=True)
        finally:
            await ollama.aclose()
            client.close()
        return

    if args.from_results:
        raws = [
            json.loads(line)
            for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        meta = json.loads((out / "report.json").read_text(encoding="utf-8"))["meta"]
    else:
        raws, ingest_stats = await run_questions(
            settings,
            root,
            manifest,
            questions,
            args.skip_ingest,
            args.evidence,
            generate=not args.no_generation,
            checkpoint=out / "results.partial.jsonl",
            open_corpus=args.open_corpus,
        )
        seconds = sorted(raw["seconds"] for raw in raws)
        meta = {
            "dataset": manifest.dataset,
            "revision": manifest.revision,
            "documents": len({q.doc_id for q in questions}),
            "questions": len(questions),
            "collection": COLLECTION,
            "tenant": TENANT,
            "model": generation_model(settings) if not args.no_generation else "none",
            "top_n": settings.reranker_top_n,
            "candidate_k": settings.reranker_candidate_k,
            "ingest": ingest_stats,
            "median_seconds": seconds[len(seconds) // 2],
            "ocr_available": shutil.which("tesseract") is not None,
            "evidence": args.evidence,
            "retrieval_scope": "open_corpus" if args.open_corpus else "question_document",
            "labels": str(args.labels) if args.labels else "v1",
            "agentic": {
                "enabled": settings.agentic_rag_enabled and not args.no_generation,
                "mode": settings.agentic_mode,
                "max_requests": settings.agentic_max_requests,
                "max_tool_calls": settings.agentic_max_tool_calls,
                "max_tokens": settings.agentic_max_tokens,
                "timeout_seconds": settings.agentic_timeout_seconds,
            },
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.jsonl").write_text(
            "".join(json.dumps(raw, ensure_ascii=False) + "\n" for raw in raws), encoding="utf-8"
        )
        (out / "results.partial.jsonl").unlink(missing_ok=True)

    outcomes = score(questions, raws)
    report = build_report(outcomes, top_k=meta["top_n"], candidate_k=meta["candidate_k"])
    per_question = [
        {
            "row_idx": o.question.row_idx,
            "doc_id": o.question.doc_id,
            "evidence_types": list(o.question.evidence_types),
            "answerable": o.question.answerable,
            "response_kind": o.kind,
            "ingested": o.ingested,
            "hit_top": o.retrieved_top_k,
            "hit_candidates": o.retrieved_candidates,
            "answered": o.answered,
            "correct": o.correct,
            "citation_on_evidence": o.citation_on_evidence,
            "gold_in_page_text": o.gold_in_page_text,
            "gold_in_evidence": o.gold_in_evidence,
            "evidence_page_seen": o.evidence_page_seen,
            "loss_stage": o.loss_stage,
            "acl_leaks": o.acl_leaks,
        }
        for o in outcomes
    ]
    (out / "report.json").write_text(
        json.dumps({"meta": meta, **report, "per_question": per_question}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, meta, out / "report.md")
    print((out / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
