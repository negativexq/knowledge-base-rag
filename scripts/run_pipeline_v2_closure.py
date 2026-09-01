# ruff: noqa: E501
"""Pipeline v2 engineering closure gate.

The script is intentionally explicit about the expensive boundary: it
validates cached identity, authored fact annotations, section serialization,
ACL-safe source expansion, and checkpoint serialization before making any
provider call.  ``--smoke36`` and ``--development200`` are opt-in follow-on
steps and are never allowed to touch calibration or frozen artifacts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.evaluation.generation_baseline import chunks_from_cache
from app.evaluation.generation_refinement import score_required_facts
from app.evidence.section_aware import SectionAwareEvidenceBuilder, serialize_section_aware_context
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.llm.observability import GenerationObservation, normalize_validator_failure_codes
from app.llm.ollama_client import OllamaClient
from app.llm.output_policy import check_output_policy
from app.llm.prompt import load_system_prompt
from app.llm.structured_output import (
    EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
    EVIDENCE_BACKED_PIPELINE_VERSION,
    parse_evidence_backed_answer,
    render_evidence_backed_answer,
    stream_evidence_backed_answer,
    validate_evidence_backed_answer,
)
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/evaluation-corpus-v2"
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
OLD_GT = ROOT / "artifacts/phase-7/structure-aware-chunking-diagnostic/fact-ground-truth.json"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-closure"
RUN_TAG = "budgeted-v1"
EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
    "generator": "qwen3.5:4b",
    "prompt": "v3",
    "think": False,
    "num_ctx": 4096,
}
MULTIDOC = ("multi-00-1", "multi-00-3", "multi-03-0")
SELECTED = (
    *MULTIDOC,
    "hard-annual-cancel",
    "hard-api-version",
    "hard-policy-language",
    "version-01-0",
    "version-01-1",
    "cross-00-0",
    "cross-06-0",
)

PIPELINE_VERSION = EVIDENCE_BACKED_PIPELINE_VERSION
OUTPUT_CONTRACT_VERSION = EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def source_path(source_id: str) -> Path | None:
    for candidate in (DATA / f"{source_id}.md", DATA / "pdf-sources" / f"{source_id}.md"):
        if candidate.exists():
            return candidate
    return None


def query_manifest() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in read_json(DATA / "golden-dataset-v2.json")}


def cache_records() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}


def historical_records() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(SMOKE / "generation-results.jsonl")}


def identity() -> dict[str, Any]:
    full = read_json(ROOT / "artifacts/phase-7/context-builder-full-validation/experiment-config.json")
    identity = dict(full.get("identity", {}))
    identity.update({key: EXPECTED[key] for key in ("generator", "prompt", "think", "num_ctx")})
    if identity.get("git_sha") != EXPECTED["git_sha"]:
        raise RuntimeError("ARTIFACT_IDENTITY_MISMATCH: git_sha")
    for key in ("corpus_fingerprint", "dataset_fingerprint", "collection", "candidate_k", "top_n"):
        if identity.get(key) != EXPECTED[key]:
            raise RuntimeError(f"ARTIFACT_IDENTITY_MISMATCH: {key}")
    return identity


def _fact(
    fact_id: str,
    component_id: str,
    source_id: str,
    span: str,
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    path = source_file or str(source_path(source_id).relative_to(ROOT))
    return {
        "required_fact_id": fact_id,
        "required_component_id": component_id,
        "authoritative_source_id": source_id,
        "source_path": path,
        "supporting_text_anchor": span[:80],
        "supporting_text_span": span,
    }


def build_fact_annotations() -> dict[str, Any]:
    """Build the ten-query authored-span manifest without using model output."""
    old = read_json(OLD_GT)
    old_facts = {item["required_fact_id"]: item for item in old["facts"]}
    facts: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for query_id in MULTIDOC:
        old_query = next(row for row in old["queries"] if row["query_id"] == query_id)
        queries.append(old_query)
        ids = {fact_id for component in old_query["required_components"] for fact_id in component["required_fact_ids"]}
        facts.extend(old_facts[fact_id] | {"required_component_id": next(
            component["required_component_id"] for component in old_query["required_components"]
            if fact_id in component["required_fact_ids"]
        )} for fact_id in ids)

    additions = {
        "hard-annual-cancel": [
            _fact("annual_cancel_48_hours", "renewal_prevention", "subscription-billing", "Bir sonraki yenileme ücretinin oluşmaması için iptal talebi yenilemeden en az 48 saat önce kayda alınmalıdır."),
            _fact("paid_period_not_shortened", "paid_period", "subscription-billing", "İptal, hâlihazırda ödenmiş dönemi kısaltmaz; erişim dönem sonuna kadar devam eder."),
        ],
        "hard-api-version": [
            _fact("api_v3_current", "api_version", "product-guide-en", "API v3 is current. API v2 remains available for compatibility while clients migrate, but it is deprecated and should not be selected for new integrations."),
        ],
        "hard-policy-language": [
            _fact("turkish_regional_context", "regional_policy_context", "regional-returns-tr", "Bu kurmaca belge Türkiye kapsamındaki siparişlerin operasyonel değerlendirmesini anlatır; hukuki görüş değildir."),
            _fact("turkish_order_context", "order_contract_context", "regional-returns-tr", "Vaka açılırken müşteri konumu, sipariş kanalı, ürün türü ve ilgili olay tarihi kaydedilir."),
        ],
        "version-01-0": [
            _fact("version_2026_return_window", "canonical_return_rule", "refund-policy-2026", "deliveries governed by the new policy use 14 calendar days from delivery."),
        ],
        "version-01-1": [
            _fact("version_2026_return_window_2", "canonical_return_rule", "refund-policy-2026", "deliveries governed by the new policy use 14 calendar days from delivery."),
        ],
        "cross-00-0": [
            _fact("cross_standard_return_window", "standard_return_window", "standard-returns-2026", "Standard-plan customers may request a refund within 14 calendar days of delivery."),
        ],
        "cross-06-0": [
            _fact("cross_renewal_cancellation", "renewal_prevention", "subscription-billing", "Bir sonraki yenileme ücretinin oluşmaması için iptal talebi yenilemeden en az 48 saat önce kayda alınmalıdır."),
        ],
    }
    for query_id in SELECTED[3:]:
        queries.append(
            {
                "query_id": query_id,
                "required_components": [
                    {
                        "required_component_id": (
                            additions[query_id][0]["required_component_id"]
                        ),
                        "required_fact_ids": [
                            fact["required_fact_id"] for fact in additions[query_id]
                        ],
                    }
                ],
            }
        )
        facts.extend(additions[query_id])
    checks = []
    for fact in facts:
        path = ROOT / fact["source_path"]
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        span = fact["supporting_text_span"]
        checks.append({"required_fact_id": fact["required_fact_id"], "source_exists": path.exists(), "span_exists": span in text})
    if not all(item["source_exists"] and item["span_exists"] for item in checks):
        raise RuntimeError("FACT_GROUND_TRUTH_INCOMPLETE")
    return {"schema_version": "pipeline-v2-authored-facts-v1", "queries": queries, "facts": facts, "checks": checks}


def source_chunks(anchor: SearchResult) -> list[SearchResult]:
    path = source_path(str(anchor.payload["source_id"]))
    if path is None:
        return [anchor]
    metadata = anchor.payload
    chunks = chunk_markdown_document(
        str(path),
        str(metadata["source_id"]),
        source_type=str(metadata.get("source_type", "filesystem")),
        doc_id=str(metadata.get("document_version") or ""),
    )
    output: list[SearchResult] = []
    for chunk in chunks:
        tenant_chunk = replace(chunk, tenant_id=str(metadata.get("tenant_id", "tenant-a")))
        payload = {
            "source_type": tenant_chunk.source_type,
            "source_id": tenant_chunk.source_id,
            "document_version": metadata.get("document_version"),
            "tenant_id": tenant_chunk.tenant_id,
            "page_number": tenant_chunk.page_number,
            "paragraph_index": tenant_chunk.paragraph_index,
            "char_range": list(tenant_chunk.char_range),
            "heading_path": list(tenant_chunk.heading_path),
            "heading_occurrence": tenant_chunk.heading_occurrence,
            "text": tenant_chunk.text,
            "chunk_id": tenant_chunk.doc_id,
        }
        from app.ingestion.qdrant_store import QdrantStore

        output.append(SearchResult(score=anchor.score, id=QdrantStore.point_id_for(tenant_chunk), payload=payload))
    return output


def build_offline_context(cache_row: dict[str, Any]) -> tuple[list[SearchResult], dict[str, Any]]:
    anchors = chunks_from_cache(cache_row)
    for anchor in anchors:
        anchor.payload.setdefault("tenant_id", "tenant-a")
    blocks: list[SearchResult] = []
    seen: set[tuple[str, str]] = set()
    selector = SectionAwareEvidenceBuilder(None, "offline", token_budget=1200)
    for anchor in anchors:
        key = (str(anchor.payload.get("source_id")), str(anchor.payload.get("document_version")))
        if key in seen:
            continue
        seen.add(key)
        all_source_chunks = source_chunks(anchor)
        source_anchors = [
            item for item in anchors
            if item.payload.get("source_id") == anchor.payload.get("source_id")
            and item.payload.get("document_version") == anchor.payload.get("document_version")
        ]
        selected: list[SearchResult] = []
        selected_ids: set[str] = set()
        for source_anchor in source_anchors:
            for item in selector._select_source_sections(source_anchor, all_source_chunks):
                if item.id not in selected_ids:
                    selected.append(item)
                    selected_ids.add(item.id)
        selected.sort(key=lambda item: (item.payload.get("page_number", 0), item.payload.get("paragraph_index", 0), item.id))
        block = SectionAwareEvidenceBuilder._block(anchor, selected)
        blocks.append(block)
    context = serialize_section_aware_context(blocks)
    if len(context.split()) > 1200:
        compact_blocks: list[SearchResult] = []
        for anchor in anchors:
            key = (str(anchor.payload.get("source_id")), str(anchor.payload.get("document_version")))
            if any(str(block.payload.get("source_id")) == key[0] for block in compact_blocks):
                continue
            all_source = source_chunks(anchor)
            compact = [
                item for item in all_source
                if item.id in {candidate.id for candidate in anchors if candidate.payload.get("source_id") == anchor.payload.get("source_id")}
            ] or [anchor]
            compact_blocks.append(SectionAwareEvidenceBuilder._block(anchor, compact))
        blocks = compact_blocks
        context = serialize_section_aware_context(blocks)
    if len(context.split()) > 1200:
        raise RuntimeError("PIPELINE_V2_CONTEXT_BUDGET_PREFLIGHT_FAILED")
    return blocks, {"input_chunk_ids": [item.id for item in anchors], "output_block_ids": [item.id for item in blocks], "context_tokens": len(context.split()), "context_chars": len(context), "expanded": any(len(b.payload.get("contributing_chunk_ids", [])) > 1 for b in blocks)}


def validate_preflight(ids: dict[str, dict[str, Any]], facts: dict[str, Any]) -> dict[str, Any]:
    if tuple(SELECTED) != tuple(dict.fromkeys(SELECTED)):
        raise RuntimeError("duplicate closure query")
    for query_id in SELECTED:
        if query_id not in ids:
            raise RuntimeError(f"missing cached query {query_id}")
    for query in facts["queries"]:
        if query["query_id"] not in SELECTED:
            raise RuntimeError("fact annotation outside closure manifest")
    # Exercise every serializable output shape before a model call.
    blocks, metrics = build_offline_context(ids[MULTIDOC[0]])
    dummy = {"query_id": MULTIDOC[0], "context": metrics, "blocks": [block.payload for block in blocks], "observation": GenerationObservation().as_dict()}
    json.dumps(dummy, ensure_ascii=False)
    write_json(OUT / "serialization-preflight.json", {"status": "PASS", "dummy_record": dummy})
    return {"status": "PASS", "query_count": len(SELECTED), "fact_count": len(facts["facts"]), "authorized_expansion": "same tenant/source/version only"}


def fact_score(question: dict[str, Any], answer: str, observable: bool = True) -> dict[str, Any]:
    if question.get("answerability") != "answerable":
        return {
            "status": "NOT_APPLICABLE", "required_fact_ids": [],
            "required_fact_count": 0, "matched_fact_ids": [], "missing_fact_ids": [],
            "fact_coverage": None, "matches": [], "expected_components": [],
        }
    return score_required_facts(question.get("expected_answer"), answer, observable=observable)


def render_candidate(candidate: dict[str, Any] | None) -> str:
    if not candidate or candidate.get("abstain"):
        return ""
    return "\n\n".join(
        str(part.get("text", "")).strip()
        for part in candidate.get("answer_parts", [])
        if isinstance(part, dict) and part.get("text")
    )


def rescore_validator_record(
    row: dict[str, Any], blocks: list[SearchResult]
) -> dict[str, Any]:
    """Re-evaluate stored candidates without crossing the inference boundary."""
    raw = row.get("raw_candidate") or ""
    try:
        parsed = parse_evidence_backed_answer(raw)
        validation = validate_evidence_backed_answer(parsed, blocks)
        rendered = render_evidence_backed_answer(
            validation.valid_parts,
            abstain=validation.application_abstain,
        )
        top_level_valid = True
    except (ValueError, json.JSONDecodeError):
        parsed = None
        validation = None
        rendered = ""
        top_level_valid = False
    policy = check_output_policy(rendered, blocks, load_system_prompt("v3"))
    codes = sorted(
        set(validation.failure_codes if validation else ["OUTPUT_SCHEMA_FAILURE"])
        | set(normalize_validator_failure_codes(policy.violations))
    )
    user_visible = (
        top_level_valid
        and bool(rendered)
        and policy.passed
        and "UNAUTHORIZED_CITATION_ID" not in codes
    )
    row["validator_pass"] = bool(
        policy.passed and not (validation and validation.failure_codes) and top_level_valid
    )
    row["validator_failure_codes"] = codes
    row["validated_output"] = rendered if user_visible else None
    row["user_visible_output"] = rendered if user_visible else ""
    row["user_visible_output_available"] = user_visible
    row["structured_candidate"] = (
        {
            "answer_parts": [
                {
                    "text": part.text,
                    "evidence": [
                        {"evidence_id": item.evidence_id, "quote": item.quote}
                        for item in part.evidence
                    ],
                }
                for part in parsed.answer_parts
            ],
            "abstain": parsed.abstain,
        }
        if parsed is not None else None
    )
    return row


async def run_closure(cache: dict[str, dict[str, Any]], historical: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    settings = Settings(_env_file=None, ollama_base_url=base_url, ollama_model="qwen3.5:4b", ollama_thinking=False, ollama_num_ctx=4096)
    client = OllamaClient(base_url=base_url, think=False, num_ctx=4096)
    models = await client.list_models()
    if "qwen3.5:4b" not in models:
        raise RuntimeError("GENERATOR_UNAVAILABLE: qwen3.5:4b")
    rows: list[dict[str, Any]] = []
    output_path = OUT / f"closure-gate-results-{RUN_TAG}.jsonl"
    existing = {row["query_id"]: row for row in read_jsonl(output_path)} if output_path.exists() else {}
    for query_id, row in existing.items():
        raw = row.get("raw_candidate", "")
        content_text = raw
        if row.get("structured_candidate"):
            content_text = render_candidate(row["structured_candidate"])
        row["fact_score"] = fact_score(
            questions[query_id], content_text, row.get("raw_candidate_available", False)
        )
    for query_id in SELECTED:
        if query_id in existing:
            rows.append(existing[query_id])
            continue
        blocks, context_metrics = build_offline_context(cache[query_id])
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        started = time.perf_counter()
        async for event in stream_evidence_backed_answer(
            questions[query_id]["question"], blocks, client, model=settings.ollama_model,
            prompt_version="v3", validation_mode="strict", context_serializer=serialize_section_aware_context,
            evaluation_observation=observation,
        ):
            events.append(event)
        latency = (time.perf_counter() - started) * 1000
        raw = observation.raw_candidate_output or ""
        visible = observation.validated_output or ""
        # Raw JSON is evaluated as content, while visibility is separately
        # determined by the strict claim validator.
        content_text = raw
        if observation.structured_candidate:
            content_text = render_candidate(observation.structured_candidate)
        score = fact_score(questions[query_id], content_text, observation.raw_candidate_available)
        rows.append({
            "query_id": query_id, "category": questions[query_id]["category"], "question": questions[query_id]["question"],
            "pipeline_version": PIPELINE_VERSION, "output_contract_version": OUTPUT_CONTRACT_VERSION,
            "generation_calls": 1, "provider_status": "COMPLETED" if observation.raw_candidate_available else "FAILED",
            "generation_latency_ms": round(latency, 3), "context": context_metrics,
            "raw_candidate": raw, "raw_candidate_available": observation.raw_candidate_available,
            "structured_candidate": observation.structured_candidate, "fact_score": score,
            "validator_pass": observation.validator_pass, "validator_failure_codes": observation.validator_failure_codes,
            "validated_output": observation.validated_output, "user_visible_output": visible,
            "user_visible_output_available": observation.user_visible_output_available,
            "events": [event for event in events if event.get("type") != "token"],
        })
        write_jsonl(output_path, rows)
    await client.aclose()
    return rows


def closure_summary(rows: list[dict[str, Any]], facts: dict[str, Any]) -> dict[str, Any]:
    full = sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in rows)
    visible = sum(row["user_visible_output_available"] and row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in rows)
    multi = [row for row in rows if row["query_id"] in MULTIDOC]
    coverages = [row["fact_score"].get("fact_coverage") for row in rows if row["fact_score"].get("fact_coverage") is not None]
    return {
        "status": "CLOSURE_GATE_COMPLETED", "query_count": len(rows), "annotated_fact_count": len(facts["facts"]),
        "fact_evidence_completeness": {"annotated_queries": len(rows), "note": "representation preflight is source/span based"},
        "raw_fully_correct_complete": full, "user_visible_full_success": visible,
        "multi_document": {"n": len(multi), "fully_correct_complete": sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in multi), "fact_coverages": [row["fact_score"].get("fact_coverage") for row in multi]},
        "mean_fact_coverage": statistics.mean(coverages) if coverages else None,
        "raw_observable": sum(row["raw_candidate_available"] for row in rows),
        "validator_pass": sum(bool(row["validator_pass"]) for row in rows),
        "generation_latency_ms": {"p50": statistics.median(row["generation_latency_ms"] for row in rows), "max": max(row["generation_latency_ms"] for row in rows)},
        "calls": {"generation": len(rows), "retrieval": 0, "embedding": 0, "reranker": 0, "semantic_evaluator": 0},
    }


async def run_smoke36(cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Run the post-gate full smoke once, using the same cached inputs."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    client = OllamaClient(base_url=base_url, think=False, num_ctx=4096)
    if "qwen3.5:4b" not in await client.list_models():
        raise RuntimeError("GENERATOR_UNAVAILABLE: qwen3.5:4b")
    query_ids = list(cache)
    output_path = OUT / "smoke36-results.jsonl"
    existing = {row["query_id"]: row for row in read_jsonl(output_path)} if output_path.exists() else {}
    rows = [existing[query_id] for query_id in query_ids if query_id in existing]
    for query_id in query_ids:
        if query_id in existing:
            continue
        blocks, context_metrics = build_offline_context(cache[query_id])
        observation = GenerationObservation()
        events: list[dict[str, Any]] = []
        started = time.perf_counter()
        async for event in stream_evidence_backed_answer(
            questions[query_id]["question"], blocks, client,
            model="qwen3.5:4b", prompt_version="v3", validation_mode="strict",
            context_serializer=serialize_section_aware_context,
            evaluation_observation=observation, think=False, num_ctx=4096,
        ):
            events.append(event)
        raw = observation.raw_candidate_output or ""
        content_text = raw
        if observation.structured_candidate:
            content_text = render_candidate(observation.structured_candidate)
        score = fact_score(questions[query_id], content_text, observation.raw_candidate_available)
        row = {
            "query_id": query_id, "category": questions[query_id]["category"],
            "language_pair": questions[query_id]["language_pair"],
            "generation_calls": 1, "provider_status": "COMPLETED" if observation.raw_candidate_available else "FAILED",
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "context": context_metrics, "raw_candidate": raw,
            "raw_candidate_available": observation.raw_candidate_available,
            "structured_candidate": observation.structured_candidate, "fact_score": score,
            "validator_pass": observation.validator_pass,
            "validator_failure_codes": observation.validator_failure_codes,
            "validated_output": observation.validated_output,
            "user_visible_output_available": observation.user_visible_output_available,
            "user_visible_output": observation.validated_output or "",
            "events": [event for event in events if event.get("type") != "token"],
        }
        rows.append(row)
        existing[query_id] = row
        ordered = [existing[item] for item in query_ids if item in existing]
        write_jsonl(output_path, ordered)
    write_jsonl(output_path, [existing[item] for item in query_ids])
    await client.aclose()
    return [existing[query_id] for query_id in query_ids]


def smoke_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({row["category"] for row in rows}):
        subset = [row for row in rows if row["category"] == category]
        by_category[category] = {
            "n": len(subset),
            "fully_correct_complete": sum(
                row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE"
                for row in subset
                if row["category"] not in {"unanswerable", "acl_negative", "ambiguous"}
            ),
            "validator_pass": sum(bool(row["validator_pass"]) for row in subset),
            "raw_observable": sum(row["raw_candidate_available"] for row in subset),
        }
    latencies = [row["generation_latency_ms"] for row in rows]
    return {
        "status": "SMOKE36_COMPLETED", "query_count": len(rows), "generation_calls": len(rows),
        "retrieval_calls": 0, "embedding_calls": 0, "reranker_calls": 0,
        "semantic_evaluator_calls": 0, "categories": by_category,
        "fully_correct_complete": sum(
            row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE"
            for row in rows
            if row["category"] not in {"unanswerable", "acl_negative", "ambiguous"}
        ),
        "validator_pass": sum(bool(row["validator_pass"]) for row in rows),
        "raw_observable": sum(row["raw_candidate_available"] for row in rows),
        "latency_ms": {"p50": statistics.median(latencies), "max": max(latencies)},
    }


def rescore_existing_artifacts(
    cache: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Refresh validator/content fields from stored candidates only.

    This is deliberately separate from the provider runners: changing the
    deterministic validator must never trigger another expensive generation.
    """
    def refresh(path: Path, query_ids: list[str]) -> list[dict[str, Any]]:
        rows_by_id = {row["query_id"]: row for row in read_jsonl(path)}
        for query_id in query_ids:
            if query_id not in rows_by_id:
                continue
            blocks, _ = build_offline_context(cache[query_id])
            row = rescore_validator_record(rows_by_id[query_id], blocks)
            content_text = row.get("raw_candidate") or ""
            if row.get("structured_candidate"):
                content_text = render_candidate(row["structured_candidate"])
            row["fact_score"] = fact_score(
                questions[query_id], content_text, row.get("raw_candidate_available", False)
            )
        ordered = [rows_by_id[item] for item in query_ids if item in rows_by_id]
        write_jsonl(path, ordered)
        return ordered

    closure_path = OUT / f"closure-gate-results-{RUN_TAG}.jsonl"
    smoke_path = OUT / "smoke36-results.jsonl"
    closure_rows = refresh(closure_path, list(SELECTED)) if closure_path.exists() else []
    smoke_rows = refresh(smoke_path, list(cache)) if smoke_path.exists() else []
    return {
        "status": "RESCORED_OFFLINE",
        "generation_calls": 0,
        "retrieval_calls": 0,
        "closure_rows": len(closure_rows),
        "smoke_rows": len(smoke_rows),
        "closure_summary": closure_summary(
            closure_rows, build_fact_annotations()
        ) if closure_rows else None,
        "smoke_summary": smoke_summary(smoke_rows) if smoke_rows else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-closure", action="store_true")
    parser.add_argument("--run-smoke36", action="store_true")
    parser.add_argument("--rescore-existing", action="store_true")
    args = parser.parse_args()
    if not args.run_closure and not args.run_smoke36 and not args.rescore_existing:
        parser.error("use --run-closure, --run-smoke36, or --rescore-existing")
    OUT.mkdir(parents=True, exist_ok=True)
    ident = identity()
    facts = build_fact_annotations()
    cache = cache_records()
    historical = historical_records()
    questions = query_manifest()
    preflight = validate_preflight(cache, facts)
    if args.rescore_existing:
        print(json.dumps(rescore_existing_artifacts(cache, questions), ensure_ascii=False, indent=2))
        return
    write_json(OUT / "pipeline-version.json", {"pipeline_version": PIPELINE_VERSION, "output_contract_version": OUTPUT_CONTRACT_VERSION, "default_enabled": False})
    write_json(OUT / "implementation-config.json", {**EXPECTED, "pipeline_version": PIPELINE_VERSION, "output_contract_version": OUTPUT_CONTRACT_VERSION, "rag_pipeline_v2": False, "context_builder": "section_aware", "validator": "claim_level_strict"})
    write_json(OUT / "fact-annotation-manifest.json", {"query_ids": list(SELECTED), "counts": {"queries": len(SELECTED), "facts": len(facts["facts"])}})
    write_json(OUT / "fact-ground-truth-expanded.json", facts)
    write_json(OUT / "closure-gate-manifest.json", {"query_ids": list(SELECTED), "composition": {"multi_document": 3, "hard": 3, "version": 2, "cross_lingual": 2}, "historical_a_generation_calls": 0, "preflight": preflight, "run_tag": RUN_TAG})
    write_json(OUT / "section-aware-builder-config.json", {"strategy": "same source/version tenant structured sections", "token_budget": 1200, "expansion": "deterministic", "neighbor_fetch": False})
    if args.run_closure:
        rows = asyncio.run(run_closure(cache, historical, questions))
        summary = closure_summary(rows, facts)
    else:
        previous = read_json(OUT / "summary.json")
        if previous.get("status") != "CLOSURE_GATE_COMPLETED":
            raise RuntimeError("CLOSURE_GATE_REQUIRED_BEFORE_SMOKE36")
        summary = previous
    decision = {
        "gate": "PIPELINE_V2_GATE_PASS" if summary["raw_fully_correct_complete"] >= 6 else "PIPELINE_V2_GATE_FAIL_MIXED",
        "reason": "engineering gate uses fact-preserving evidence, structured claims, and strict user-visible validation",
        "smoke36_authorized": summary["raw_fully_correct_complete"] >= 6,
    }
    if args.run_closure:
        write_json(OUT / "closure-gate-comparison.json", summary)
    if args.run_smoke36:
        # Build and serialize every model-visible context before the first
        # full-smoke call; a late serialization failure must not waste a
        # local generation call.
        for query_id in cache:
            build_offline_context(cache[query_id])
        smoke_rows = asyncio.run(run_smoke36(cache, questions))
        smoke = smoke_summary(smoke_rows)
        write_json(OUT / "smoke36-comparison.json", smoke)
        write_json(OUT / "smoke36-slice-metrics.json", smoke["categories"])
        write_json(OUT / "smoke36-summary.json", smoke)
    write_json(OUT / "closure-gate-citation-analysis.json", {"identity": "see per-query validator events", "claim_level": True})
    write_json(OUT / "closure-gate-safety-analysis.json", {"acl": "expansion is tenant-scoped", "phase6_semantic_gate": "OFF"})
    write_json(OUT / "closure-gate-latency.json", summary["generation_latency_ms"])
    write_json(OUT / "decision.json", decision)
    write_json(OUT / "summary.json", summary)
    write_json(OUT / "report.md", "# Pipeline v2 Closure Gate\n\n" + json.dumps({"identity": ident, "summary": summary, "decision": decision}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": summary, "decision": decision}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
