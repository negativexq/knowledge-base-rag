"""Cache-first Phase 6C.1 semantic evaluator model smoke benchmark."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.index_validation import validate_evaluation_index
from app.evaluation.semantic_answerability import (
    AMBIGUITY_PROMPT_VERSION,
    SUFFICIENCY_PROMPT_VERSION,
    OllamaSemanticEvaluator,
    chunk_identifier,
)
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.report import RetrievalReport
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET = CORPUS_DIR / "golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
MANIFEST = CORPUS_DIR / "corpus-manifest.json"
INDEX_VALIDATION = ROOT / "artifacts/phase-5-5/index-validation.json"
OUTPUT_DIR = ROOT / "artifacts/phase-6/semantic-model-smoke"
COLLECTION_DEFAULT = "kb_eval_phase55_0175aa4a2f9b"
REFERENCE_CANDIDATE_K = 20
TOP_N = 5
DEFAULT_MODELS = ("qwen3.5:4b", "qwen2.5:3b-instruct", "gemma2:2b")
CRITICAL_CATEGORIES = (
    "standard_answerable",
    "hard_answerable",
    "cross_lingual",
    "multi_document",
    "version_conflict",
    "injection_bearing",
    "acl_negative",
    "unanswerable",
    "ambiguous",
)


def retrieval_config() -> dict[str, Any]:
    return {
        "embedding_model": "qwen3-embedding:4b",
        "embedding_dimension": 1024,
        "retrieval_method": "BM25 + dense + RRF",
        "candidate_k": REFERENCE_CANDIDATE_K,
        "top_n": TOP_N,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "tenant_acl": True,
    }


def retrieval_config_fingerprint() -> str:
    payload = json.dumps(retrieval_config(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def partition_requested_models(
    requested: list[str], available: set[str]
) -> tuple[list[str], dict[str, str]]:
    """Keep model availability handling explicit and deterministic."""
    evaluated = [model for model in requested if model in available]
    skipped = {
        model: "not installed locally" for model in requested if model not in available
    }
    return evaluated, skipped


def select_model(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the smoke benchmark's safety-first recommendation ordering."""
    safe = [
        summary
        for summary in comparisons
        if summary["injection_robustness"]["status"] == "PASS"
        and summary["reliability"]["final_parse_failure_count"] == 0
        and summary["reliability"]["timeout_count"] == 0
        and summary["combined"]["false_answer_count"] == 0
    ]
    if not safe:
        return {"status": "SEMANTIC_QUALITY_INSUFFICIENT", "model": None}
    winner = max(
        safe,
        key=lambda summary: (
            summary["ambiguity"]["f1"],
            summary["sufficiency"]["f1"],
            summary["combined"]["gold_present_answerable_coverage"] or 0.0,
            -float(summary["latency"]["total"]["p95"] or float("inf")),
        ),
    )
    return {"status": "SELECT_MODEL", "model": winner["model"]}


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_development_questions(path: Path = DATASET) -> list[dict]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    selected = [q for q in questions if q["split"] == "development"]
    return sorted(selected, key=lambda q: q["id"])


def select_smoke_questions(questions: list[dict], count: int = 25) -> list[dict]:
    """Select a stable, coverage-oriented set, then fill by stable ID."""
    selected: dict[str, dict] = {}
    preferred_ids = {
        # Prefer records that exercise complete multi-source evidence and the
        # stronger injected-document fixture when both are available.
        "multi_document": "multi-00-1",
        "injection_bearing": "injection-04-0",
    }
    for category in CRITICAL_CATEGORIES:
        candidates = [question for question in questions if question["category"] == category]
        preferred = preferred_ids.get(category)
        question = next((q for q in candidates if q["id"] == preferred), None)
        if question is None and candidates:
            question = candidates[0]
        if question is not None:
            selected[question["id"]] = question
    for pair in ("tr->en", "en->tr"):
        for question in questions:
            if question["language_pair"] == pair:
                selected[question["id"]] = question
                break
    for question in questions:
        if len(selected) >= count:
            break
        selected[question["id"]] = question
    if len(selected) != count:
        raise ValueError(f"expected at least {count} development questions")
    return [selected[key] for key in sorted(selected)][:count]


def _source_ids(chunks: list) -> list[str]:
    return list(
        dict.fromkeys(str(c.payload["source_id"]) for c in chunks if c.payload.get("source_id"))
    )


def _required_sources(question: dict) -> set[str]:
    return set(question.get("required_evidence") or question.get("expected_source_ids") or [])


def _safe_cached_chunk(result) -> dict[str, Any]:
    payload = result.payload
    item = {
        "chunk_id": chunk_identifier(result),
        "source_id": str(payload.get("source_id")) if payload.get("source_id") else None,
        "content": str(payload.get("text") or ""),
    }
    for key in ("title", "authority_role", "authority_scope", "document_version"):
        if payload.get(key):
            item[key] = str(payload[key])
    return item


def _cache_record(question: dict, report: RetrievalReport, chunks: list) -> dict[str, Any]:
    source_ids = set(_source_ids(chunks))
    required = _required_sources(question)
    return {
        "query_id": question["id"],
        "case_family": question["case_family"],
        "category": question["category"],
        "split": question["split"],
        "tenant": question["tenant_id"],
        "ground_truth_label": question["answerability"],
        "query_language": question["query_language"],
        "evidence_language": question["evidence_language"],
        "language_pair": question["language_pair"],
        "query": question["question"],
        "expected_source_ids": question.get("expected_source_ids", []),
        "required_source_ids": sorted(required),
        "gold_present": bool(required) and required.issubset(source_ids),
        "all_required_present": bool(required) and required.issubset(source_ids),
        "authorized_top5": [_safe_cached_chunk(chunk) for chunk in chunks],
        "pre_acl_candidate_count": report.pre_acl_candidate_count,
        "authorized_candidate_count": report.authorized_candidate_count,
        "reranked_count": len(chunks),
        "deterministic_reason": None,
    }


def build_cache_metadata(
    fingerprints: dict, collection: str, query_ids: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": "phase-6c1-evaluator-input-cache-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config": retrieval_config(),
        "retrieval_config_fingerprint": retrieval_config_fingerprint(),
        "prompt_versions": {
            "ambiguity": AMBIGUITY_PROMPT_VERSION,
            "sufficiency": SUFFICIENCY_PROMPT_VERSION,
        },
        "query_count": len(query_ids),
        "query_ids": query_ids,
        "authorized_only": True,
        "generation_invoked": False,
    }


def validate_cache(metadata: dict, fingerprints: dict, collection: str) -> None:
    expected = {
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": collection,
        "retrieval_config_fingerprint": retrieval_config_fingerprint(),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"evaluator cache identity mismatch for {key}")
    if metadata.get("authorized_only") is not True:
        raise ValueError("evaluator cache is not marked authorized-only")


def _cached_chunks(record: dict) -> list:
    from app.retrieval.hybrid_search import SearchResult

    chunks = []
    for item in record["authorized_top5"]:
        if "score" in item or "metadata" in item:
            raise ValueError("evaluator cache contains forbidden retrieval metadata")
        payload = {
            "chunk_id": item["chunk_id"],
            "source_id": item.get("source_id"),
            "text": item["content"],
        }
        for key in ("title", "authority_role", "authority_scope", "document_version"):
            if item.get(key):
                payload[key] = item[key]
        chunks.append(SearchResult(score=0.0, id=item["chunk_id"], payload=payload))
    return chunks


async def build_cache(args: argparse.Namespace) -> dict:
    questions = select_smoke_questions(load_development_questions(Path(args.dataset)))
    fingerprints = json.loads(Path(args.fingerprints).read_text(encoding="utf-8"))
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    embedding = active_embedding_config(settings)
    collection = args.collection or COLLECTION_DEFAULT
    qdrant = QdrantClient(url=args.qdrant_url or settings.qdrant_url)
    validation = validate_evaluation_index(
        qdrant,
        collection,
        Path(args.manifest),
        Path(args.index_validation),
        fingerprints["corpus_fingerprint"],
        expected_dimension=embedding.dimension,
    )
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse = SparseEncoder()
    reranker = CrossEncoderReranker(
        settings.reranker_model, device=args.reranker_device, max_concurrency=1
    )
    records = []
    try:
        for question in questions:
            report = RetrievalReport()
            chunks = await search(
                question["question"],
                ollama,
                sparse,
                qdrant,
                collection,
                embedding.ollama_model,
                RetrievalContext(tenant_id=question["tenant_id"]),
                reranker=reranker,
                top_k=REFERENCE_CANDIDATE_K,
                top_n=TOP_N,
                query_prefix=embedding.query_prefix(),
                dimensions=embedding.output_dimension,
                report=report,
            )
            phase6a = extract_answerability_observation(
                chunks,
                authorized_candidate_count=report.authorized_candidate_count,
                pre_acl_candidate_count=report.pre_acl_candidate_count,
            )
            record = _cache_record(question, report, chunks)
            record["deterministic_reason"] = (
                phase6a.reason if phase6a.reason != "FEATURES_AVAILABLE" else None
            )
            records.append(record)
    finally:
        await ollama.aclose()
        qdrant.close()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "query-set.json").write_text(
        json.dumps([r["query_id"] for r in records], indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "evaluator-inputs.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )
    metadata = build_cache_metadata(fingerprints, collection, [r["query_id"] for r in records])
    metadata["retrieval_calls_during_cache_build"] = len(records)
    metadata["index_validation"] = validation
    (output_dir / "cache-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def load_cache(
    output_dir: Path, fingerprints_path: Path, collection: str
) -> tuple[dict, list[dict]]:
    metadata = json.loads((output_dir / "cache-metadata.json").read_text(encoding="utf-8"))
    fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8"))
    validate_cache(metadata, fingerprints, collection)
    records = [
        json.loads(line)
        for line in (output_dir / "evaluator-inputs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if metadata["query_ids"] != [r["query_id"] for r in records]:
        raise ValueError("evaluator cache query set does not match its metadata")
    for record in records:
        _cached_chunks(record)
    return metadata, records


def _metric(expected: list[str], actual: list[str], positive: str) -> dict[str, Any]:
    tp = sum(e == positive and a == positive for e, a in zip(expected, actual, strict=True))
    fp = sum(e != positive and a == positive for e, a in zip(expected, actual, strict=True))
    fn = sum(e == positive and a != positive for e, a in zip(expected, actual, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(expected),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    values = sorted(values)
    return {
        "n": len(values),
        "p50": median(values),
        "p95": values[round(0.95 * (len(values) - 1))],
        "max": max(values),
    }


def _expected_action(record: dict) -> str:
    if record["ground_truth_label"] == "ambiguous":
        return "CLARIFY"
    if record["ground_truth_label"] == "answerable" and record["all_required_present"]:
        return "ANSWER"
    return "ABSTAIN"


async def evaluate_model(
    model: str,
    records: list[dict],
    client: OllamaClient,
    timeout_seconds: float = 30.0,
    retries: int = 1,
) -> tuple[dict, list[dict]]:
    evaluator = OllamaSemanticEvaluator(client, model, timeout_seconds, retries)
    results = []
    for record in records:
        chunks = _cached_chunks(record)
        observation = await evaluator.evaluate(
            record["query"], chunks, record["deterministic_reason"]
        )
        results.append(
            {
                "query_id": record["query_id"],
                "case_family": record["case_family"],
                "category": record["category"],
                "ground_truth_label": record["ground_truth_label"],
                "query_language": record["query_language"],
                "evidence_language": record["evidence_language"],
                "language_pair": record["language_pair"],
                "gold_present": record["gold_present"],
                "all_required_present": record["all_required_present"],
                "deterministic_reason": record["deterministic_reason"],
                **observation.as_dict(),
            }
        )
    expected_ambiguity = [
        "AMBIGUOUS" if r["ground_truth_label"] == "ambiguous" else "CLEAR" for r in results
    ]
    actual_ambiguity = [r["ambiguity"]["decision"] if r["ambiguity"] else "ERROR" for r in results]
    suff_records = [r for r in results if r["sufficiency"] is not None]
    expected_suff = [
        "SUFFICIENT"
        if r["ground_truth_label"] == "answerable" and r["all_required_present"]
        else "INSUFFICIENT"
        for r in suff_records
    ]
    actual_suff = [r["sufficiency"]["decision"] for r in suff_records]
    expected_actions = [_expected_action(r) for r in results]
    actual_actions = [r["shadow_action"] for r in results]
    unsafe = sum(
        e in {"ABSTAIN", "CLARIFY"} and a == "ANSWER"
        for e, a in zip(expected_actions, actual_actions, strict=True)
    )
    gold_present = [
        r for r in results if r["ground_truth_label"] == "answerable" and r["all_required_present"]
    ]
    injection = [r for r in results if r["category"] == "injection_bearing"]
    reliability = {
        "evaluator_calls": sum(r["evaluator_call_count"] for r in results),
        "ambiguity_calls": sum(
            bool(
                r["ambiguity"] is not None
                or (r["error_code"] and r["error_code"].startswith("AMBIGUITY"))
            )
            for r in results
        ),
        "sufficiency_calls": len(suff_records),
        "first_pass_schema_success": sum(r["first_pass_schema_success"] for r in results),
        "retry_count": sum(r["retry_count"] for r in results),
        "final_parse_failure_count": sum(r["parse_error"] for r in results),
        "timeout_count": sum(r["timeout_count"] for r in results),
        "invalid_enum_count": sum(r["invalid_enum_count"] for r in results),
        "hallucinated_supporting_chunk_id_count": sum(
            r["hallucinated_supporting_chunk_id_count"] for r in results
        ),
    }
    summary = {
        "model": model,
        "query_count": len(results),
        "ambiguity": _metric(expected_ambiguity, actual_ambiguity, "AMBIGUOUS"),
        "sufficiency": _metric(expected_suff, actual_suff, "SUFFICIENT"),
        "combined": {
            "false_answer_count": unsafe,
            "false_answer_rate": unsafe / len(results) if results else 0.0,
            "false_abstain_count": sum(
                e == "ANSWER" and a == "ABSTAIN"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "missed_ambiguity_count": sum(
                e == "CLARIFY" and a != "CLARIFY"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "false_clarify_count": sum(
                e != "CLARIFY" and a == "CLARIFY"
                for e, a in zip(expected_actions, actual_actions, strict=True)
            ),
            "gold_present_answerable_coverage": sum(
                r["shadow_action"] == "ANSWER" for r in gold_present
            )
            / len(gold_present)
            if gold_present
            else None,
            "gold_present_answered": sum(r["shadow_action"] == "ANSWER" for r in gold_present),
            "gold_present_count": len(gold_present),
        },
        "reliability": reliability,
        "injection_robustness": {
            "status": "PASS"
            if injection and all(not r["parse_error"] for r in injection)
            else "INCONCLUSIVE",
            "query_count": len(injection),
            "parse_failures": sum(r["parse_error"] for r in injection),
        },
        "multi_document": {
            "n": sum(r["category"] == "multi_document" for r in results),
            "complete_sufficient": sum(
                r["category"] == "multi_document"
                and r["all_required_present"]
                and (r["sufficiency"] or {}).get("decision") == "SUFFICIENT"
                for r in results
            ),
            "partial_insufficient": sum(
                r["category"] == "multi_document"
                and not r["all_required_present"]
                and (r["sufficiency"] or {}).get("decision") == "INSUFFICIENT"
                for r in results
            ),
        },
        "latency": {
            "ambiguity": _latency(
                [
                    r["ambiguity_latency_ms"]
                    for r in results
                    if r["ambiguity_latency_ms"] is not None
                ]
            ),
            "sufficiency": _latency(
                [
                    r["sufficiency_latency_ms"]
                    for r in results
                    if r["sufficiency_latency_ms"] is not None
                ]
            ),
            "total": _latency([r["latency_ms"] for r in results]),
        },
        "short_circuit_saved_sufficiency_calls": sum(
            (r["ambiguity"] or {}).get("decision") == "AMBIGUOUS" for r in results
        ),
    }
    return summary, results


def write_report(output_dir: Path, comparison: dict[str, Any]) -> None:
    if "selection" not in comparison:
        comparison["selection"] = select_model(comparison.get("models", []))
    report = "# Phase 6C.1 semantic evaluator model smoke\n\n"
    report += f"Evaluated models: {', '.join(comparison['evaluated_models']) or 'none'}\n\n"
    report += f"Skipped models: {json.dumps(comparison['skipped_models'], sort_keys=True)}\n\n"
    report += (
        "Retrieval was cached once; evaluator-only runs performed zero retrieval, "
        "embedding, reranker, and generation calls. The evaluator prompts and schemas "
        "were unchanged across models.\n\n"
    )
    report += "## Results\n\n"
    report += (
        "| model | ambiguity F1 | sufficiency F1 | false answers | false abstains | "
        "gold-present coverage | total p95 ms | parse failures |\n"
    )
    report += "|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for summary in comparison["models"]:
        report += (
            f"| {summary['model']} | {summary['ambiguity']['f1']:.3f} | "
            f"{summary['sufficiency']['f1']:.3f} | "
            f"{summary['combined']['false_answer_count']}/{summary['query_count']} | "
            f"{summary['combined']['false_abstain_count']}/{summary['query_count']} | "
            f"{summary['combined']['gold_present_answered']}/"
            f"{summary['combined']['gold_present_count']} | "
            f"{summary['latency']['total']['p95']:.1f} | "
            f"{summary['reliability']['final_parse_failure_count']} |\n"
        )
    report += "\n## Recommendation\n\n"
    report += f"{json.dumps(comparison['selection'], sort_keys=True)}\n\n"
    report += (
        "The selection is a 25-query smoke recommendation only. It does not establish "
        "production accuracy and does not change ANSWERABILITY_EVAL_MODEL. qwen3:4b "
        "was not available locally and no model was pulled. The 7B/9B candidates were "
        "not evaluated in this first small-model round.\n"
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")


async def evaluate_cached(args: argparse.Namespace) -> dict:
    output_dir = Path(args.output_dir)
    collection = args.collection or COLLECTION_DEFAULT
    metadata, records = load_cache(output_dir, Path(args.fingerprints), collection)
    client = OllamaClient(base_url=args.ollama_url)
    try:
        available = set(await client.list_models())
        requested = list(args.models)
        models, skipped = partition_requested_models(requested, available)
        comparisons = []
        per_model_dir = output_dir / "per-model"
        per_model_dir.mkdir(parents=True, exist_ok=True)
        for model in models:
            summary, results = await evaluate_model(
                model, records, client, args.timeout_seconds, args.retries
            )
            comparisons.append(summary)
            (per_model_dir / f"{model.replace(':', '-')}.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in results)
                + "\n",
                encoding="utf-8",
            )
        comparison = {
            "schema_version": "phase-6c1-semantic-model-smoke-v1",
            "timestamp": datetime.now(UTC).isoformat(),
            "git_sha": _git_sha(),
            "cache_metadata": metadata,
            "available_models": sorted(available),
            "requested_models": requested,
            "evaluated_models": [s["model"] for s in comparisons],
            "skipped_models": skipped,
            "models": comparisons,
            "selection": select_model(comparisons),
            "retrieval_calls_during_model_evaluation": 0,
            "embedding_calls_during_model_evaluation": 0,
            "reranker_calls_during_model_evaluation": 0,
            "generation_invoked": False,
        }
        (output_dir / "model-comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with (output_dir / "model-comparison.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            fields = [
                "model",
                "ambiguity_f1",
                "sufficiency_f1",
                "false_answer_count",
                "false_abstain_count",
                "gold_present_answerable_coverage",
                "total_p95_ms",
                "final_parse_failure_count",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for summary in comparisons:
                writer.writerow(
                    {
                        "model": summary["model"],
                        "ambiguity_f1": summary["ambiguity"]["f1"],
                        "sufficiency_f1": summary["sufficiency"]["f1"],
                        "false_answer_count": summary["combined"]["false_answer_count"],
                        "false_abstain_count": summary["combined"]["false_abstain_count"],
                        "gold_present_answerable_coverage": summary["combined"][
                            "gold_present_answerable_coverage"
                        ],
                        "total_p95_ms": summary["latency"]["total"]["p95"],
                        "final_parse_failure_count": summary["reliability"][
                            "final_parse_failure_count"
                        ],
                    }
                )
        latency = {s["model"]: s["latency"] for s in comparisons}
        (output_dir / "latency.json").write_text(
            json.dumps(latency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_report(output_dir, comparison)
        return comparison
    finally:
        await client.aclose()


async def main_async(args: argparse.Namespace) -> dict:
    if args.report_only:
        output_dir = Path(args.output_dir)
        comparison = json.loads((output_dir / "model-comparison.json").read_text(encoding="utf-8"))
        cache_metadata_path = output_dir / "cache-metadata.json"
        cache_metadata = json.loads(cache_metadata_path.read_text(encoding="utf-8"))
        cache_metadata.setdefault(
            "retrieval_calls_during_cache_build", cache_metadata["query_count"]
        )
        cache_metadata_path.write_text(
            json.dumps(cache_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        comparison["cache_metadata"] = cache_metadata
        comparison.setdefault("selection", select_model(comparison.get("models", [])))
        (output_dir / "model-comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_report(output_dir, comparison)
        return comparison
    if args.build_cache:
        metadata = await build_cache(args)
        if args.build_cache_only:
            return metadata
    return await evaluate_cached(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-cache", action="store_true")
    parser.add_argument("--build-cache-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--fingerprints", type=Path, default=FINGERPRINTS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--index-validation", type=Path, default=INDEX_VALIDATION)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--qdrant-url")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--reranker-device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main_async(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
