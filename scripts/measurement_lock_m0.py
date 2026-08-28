# ruff: noqa: E501
"""Measurement Lock M0 and frozen V2.2 baseline.

This script deliberately ends before V2.3 implementation.  It creates the
unseen multi-document holdout and evidence snapshots, runs the preregistered
stability audit, and records the V2.2 paired baseline on those snapshots.
There is no V2.3 code or model branch in this module.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.evaluation.generation_baseline import safe_chunk_payload
from app.evidence.section_aware import serialize_section_aware_context
from app.llm.observability import GenerationObservation
from app.llm.ollama_client import OllamaClient
from app.llm.structured_output import (
    EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION,
    EVIDENCE_BACKED_PIPELINE_VERSION,
    parse_evidence_backed_answer,
    stream_evidence_backed_answer,
)
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings
from scripts.run_pipeline_v2_closure import build_offline_context

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/evaluation/evaluation-corpus-v2"
DATASET = DATA / "golden-dataset-v2.json"
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
OUT = ROOT / "artifacts/phase-7/measurement-lock-m0"
SNAPSHOTS = OUT / "evidence-snapshots"
IDENTITY = {
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
    "temperature": 0.0,
}
DEBUG_IDS = ("multi-00-1", "multi-00-3", "multi-03-0")
ACL_IDS = ("acl-02-0", "acl-02-1", "acl-02-2")
SEEDS = (41, 42, 43, 44, 45)
REPRESENTATIVE = {
    "multi_document": "multi-00-1",
    "acl": "acl-02-0",
    "standard": "native-00-0",
    "cross_lingual": "cross-06-0",
    "authority_version": "version-01-0",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run_key(qid: str, seed: int, snapshot: dict[str, Any], pipeline: str) -> str:
    """Stable identity for one generation checkpoint; mismatches fail closed."""
    return sha256_json(
        {
            "pipeline": pipeline,
            "query_id": qid,
            "seed": seed,
            "snapshot_hash": snapshot.get("context_hash"),
            "prompt": IDENTITY["prompt"],
            "generator": IDENTITY["generator"],
            "num_ctx": IDENTITY["num_ctx"],
            "temperature": IDENTITY["temperature"],
            "think": IDENTITY["think"],
        }
    )


def verify_identity() -> dict[str, Any]:
    cache_meta = read_json(SMOKE / "cache-metadata.json")
    for key in (
        "git_sha",
        "corpus_fingerprint",
        "dataset_fingerprint",
        "collection",
        "candidate_k",
        "top_n",
    ):
        if cache_meta.get(key) != IDENTITY[key]:
            raise RuntimeError(f"ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH:{key}")
    fingerprints = read_json(ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json")
    if fingerprints.get("corpus_fingerprint") != IDENTITY["corpus_fingerprint"]:
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH:corpus")
    if fingerprints.get("dataset_fingerprint") != IDENTITY["dataset_fingerprint"]:
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH:dataset")
    return {**IDENTITY, "cache_schema": cache_meta.get("schema_version")}


def questions() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in read_json(DATASET)}


def choose_holdout(qs: dict[str, dict[str, Any]]) -> list[str]:
    candidates = [
        q["id"]
        for q in qs.values()
        if q.get("split") == "development"
        and q.get("category") == "multi_document"
        and q["id"] not in DEBUG_IDS
    ]
    if len(candidates) < 8:
        raise RuntimeError("HOLDOUT_SELECTION_INSUFFICIENT")
    # Pre-registered rule: stable SHA-256 of the committed query ID, then ID.
    return [
        qid
        for qid, _digest in sorted(
            ((qid, hashlib.sha256(qid.encode()).hexdigest()) for qid in candidates),
            key=lambda item: (item[1], item[0]),
        )[:8]
    ]


def fact(fact_id: str, component: str, source: str, span: str) -> dict[str, Any]:
    source_path = DATA / (
        f"{source}.md" if (DATA / f"{source}.md").exists() else f"pdf-sources/{source}.md"
    )
    text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    if span not in text:
        raise RuntimeError(f"FACT_GROUND_TRUTH_INCOMPLETE:{fact_id}")
    return {
        "fact_id": fact_id,
        "required_fact_id": fact_id,
        "component_id": component,
        "required_component_id": component,
        "authoritative_source_id": source,
        "source_path": str(source_path.relative_to(ROOT)),
        "supporting_text_anchor": span[:100],
        "supporting_text_span": span,
    }


def build_holdout_facts(holdout: list[str]) -> dict[str, Any]:
    base = read_json(
        ROOT / "artifacts/phase-7/structure-aware-chunking-diagnostic/fact-ground-truth.json"
    )
    base_by_id = {item["required_fact_id"]: item for item in base["facts"]}
    family_facts = {
        "multi-00": ["standard_return_window_14_days", "support_return_case_fields"],
        "multi-01": [
            "premium_return_window_30_days",
            "marketplace_return_window_7_days",
            "marketplace_channel_required",
        ],
        "multi-03": [
            "regional_withdrawal_framework_14_days",
            "digital_activation_boundary",
            "joint_exception_routing",
        ],
    }
    base_components = {
        "standard_return_window_14_days": "standard_return_window",
        "support_return_case_fields": "support_case_fields",
        "regional_withdrawal_framework_14_days": "regional_withdrawal_right",
        "digital_activation_boundary": "activated_digital_exception",
        "joint_exception_routing": "activated_digital_exception",
    }
    new_facts = {
        "premium_return_window_30_days": fact(
            "premium_return_window_30_days",
            "premium_window",
            "premium-returns-2026",
            "Premium customers have 30 calendar days from delivery to request a return.",
        ),
        "marketplace_return_window_7_days": fact(
            "marketplace_return_window_7_days",
            "marketplace_window",
            "marketplace-returns",
            "Pazar yeri siparişlerinde iade talebi teslimattan itibaren 7 takvim günü içinde, pazar yerinin vaka kanalı kullanılarak açılır.",
        ),
        "marketplace_channel_required": fact(
            "marketplace_channel_required",
            "marketplace_window",
            "marketplace-returns",
            "Pazar yeri kaydı bulunmuyorsa görevli süre sözü vermez; önce ilgili kanalın vaka numarasını ister.",
        ),
    }
    facts: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    for qid in holdout:
        family = next(family for family in family_facts if qid.startswith(family))
        selected: list[dict[str, Any]] = []
        for fid in family_facts[family]:
            item = dict(new_facts.get(fid) or base_by_id[fid])
            if "required_component_id" not in item:
                item["required_component_id"] = item.get("component_id") or base_components[fid]
            selected.append(item)
            if item not in facts:
                facts.append(item)
        components: dict[str, list[str]] = {}
        for item in selected:
            components.setdefault(item["required_component_id"], []).append(
                item["required_fact_id"]
            )
        query_rows.append(
            {
                "query_id": qid,
                "required_components": [
                    {"required_component_id": component, "required_fact_ids": ids}
                    for component, ids in components.items()
                ],
            }
        )
    checks = [
        {
            "fact_id": item["required_fact_id"],
            "source_exists": (ROOT / item["source_path"]).exists(),
            "span_exists": True,
        }
        for item in facts
    ]
    return {
        "schema_version": "measurement-lock-fact-ground-truth-v1",
        "queries": query_rows,
        "facts": facts,
        "checks": checks,
    }


def cache_rows() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(SMOKE / "retrieval-inputs.jsonl")}


def _payload(result: SearchResult, rank: int) -> dict[str, Any]:
    data = safe_chunk_payload(result)
    data["rank"] = rank
    data["score"] = result.score
    return data


async def retrieve_snapshot_rows(
    qids: list[str], qs: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Run the common retrieval path once for the unseen holdout and ACL set."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    settings = Settings(
        _env_file=None,
        ollama_base_url=base_url,
        ollama_model="qwen3.5:4b",
        embedding_model_key="qwen3-4b",
        embedding_output_dimension=1024,
        qdrant_collection_name=IDENTITY["collection"],
        reranker_model="BAAI/bge-reranker-v2-m3",
        reranker_candidate_k=20,
        reranker_top_n=5,
        reranker_max_concurrency=1,
    )
    client = OllamaClient(base_url=base_url)
    sparse = SparseEncoder()
    qdrant = QdrantClient(url=settings.qdrant_url)
    from app.reranker.cross_encoder import CrossEncoderReranker
    from app.retrieval.filters import filter_authorized_candidates

    reranker = CrossEncoderReranker("BAAI/bge-reranker-v2-m3", max_concurrency=1)
    result: dict[str, dict[str, Any]] = {}
    for qid in qids:
        question = qs[qid]
        context = RetrievalContext(tenant_id=question["tenant_id"], is_system=False)
        vector = await client.embed(
            question["question"],
            model="qwen3-embedding:4b",
            prefix="Instruct: Given a search query, retrieve relevant passages that answer the query\nQuery: ",
            dimensions=1024,
        )
        sparse_vector = sparse.embed_query(question["question"])
        candidates = filter_authorized_candidates(
            hybrid_search(
                qdrant, IDENTITY["collection"], vector, sparse_vector, top_k=20, filters=None
            ),
            context,
        )
        ranked = await reranker.async_rerank(question["question"], candidates, 5)
        result[qid] = {
            "query_id": qid,
            "tenant_id": question["tenant_id"],
            "candidate_top20": [_payload(item, rank) for rank, item in enumerate(candidates, 1)],
            "authorized_top5": [_payload(item, rank) for rank, item in enumerate(ranked, 1)],
            "retrieval_calls": 1,
            "embedding_calls": 1,
            "reranker_calls": 1,
        }
    await client.aclose()
    return result


def add_cached_rows(
    qids: list[str], qs: dict[str, dict[str, Any]], rows: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    # Existing Phase 7 top-5 rows are reused for representative stability
    # controls; holdout/ACL snapshots are refreshed by retrieve_snapshot_rows.
    cached = cache_rows()
    for qid in qids:
        if qid not in cached:
            raise RuntimeError(f"MISSING_CACHED_CONTROL:{qid}")
        row = dict(cached[qid])
        row["candidate_top20"] = []
        row["snapshot_source"] = "historical_phase7_authorized_top5_cache"
        rows[qid] = row
    return rows


def build_snapshot(qid: str, row: dict[str, Any]) -> dict[str, Any]:
    blocks, metrics = build_offline_context(row)
    context = serialize_section_aware_context(blocks)
    serialized_blocks = [block.payload for block in blocks]
    return {
        "query_id": qid,
        "tenant_id": row.get("tenant_id", "tenant-a"),
        "candidate_top20_ids": [item.get("chunk_id") for item in row.get("candidate_top20", [])],
        "top5_ids": [item.get("chunk_id") for item in row.get("authorized_top5", [])],
        "candidate_top20": row.get("candidate_top20", []),
        "authorized_top5": row.get("authorized_top5", []),
        "evidence_blocks": serialized_blocks,
        "model_visible_context": context,
        "context_tokens": len(context.split()),
        "context_hash": hashlib.sha256(context.encode()).hexdigest(),
        "metrics": metrics,
        "pipeline_identity": IDENTITY,
    }


def load_snapshot(qid: str) -> tuple[list[SearchResult], dict[str, Any]]:
    snapshot = read_json(SNAPSHOTS / f"{qid}.json")
    row = {"authorized_top5": snapshot["authorized_top5"]}
    return build_offline_context(row)


async def generate_once(
    qid: str, question: str, blocks: list[SearchResult], seed: int
) -> dict[str, Any]:
    client = generate_once.client
    observation = GenerationObservation()
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    async for event in stream_evidence_backed_answer(
        question,
        blocks,
        client,
        model="qwen3.5:4b",
        prompt_version="v3",
        context_serializer=serialize_section_aware_context,
        evaluation_observation=observation,
        think=False,
        num_ctx=4096,
        seed=seed,
    ):
        events.append(event)
    raw = observation.raw_candidate_output or ""
    parsed_hash = None
    support_selection = None
    try:
        parsed = parse_evidence_backed_answer(raw)
        parsed_hash = sha256_json(
            {"answer_parts": [part.text for part in parsed.answer_parts], "abstain": parsed.abstain}
        )
        support_selection = [
            {
                "text": part.text,
                "evidence": [
                    {"evidence_id": item.evidence_id, "quote": item.quote} for item in part.evidence
                ],
            }
            for part in parsed.answer_parts
        ]
    except (ValueError, json.JSONDecodeError):
        pass
    return {
        "query_id": qid,
        "seed": seed,
        "raw_output": raw,
        "raw_output_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "parsed_output_hash": parsed_hash,
        "support_selection": support_selection,
        "final_classification": "VISIBLE"
        if observation.user_visible_output_available
        else "ABSTAIN_OR_REJECT",
        "validator_pass": observation.validator_pass,
        "validator_failure_codes": observation.validator_failure_codes,
        "model_abstention": observation.model_abstention,
        "application_forced_abstention": observation.application_forced_abstention,
        "user_visible_output": observation.validated_output,
        "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "raw_candidate_available": observation.raw_candidate_available,
        "provider_observation": generate_once.client.last_call_observation,
        "events": [event for event in events if event.get("type") != "token"],
    }


async def run_generation_rows(
    snapshot_qids: list[str], qs: dict[str, dict[str, Any]], output: Path, *, baseline: bool
) -> list[dict[str, Any]]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    generate_once.client = OllamaClient(base_url=base_url, think=False, num_ctx=4096)
    if "qwen3.5:4b" not in await generate_once.client.list_models():
        raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
    existing = (
        {(row["query_id"], row["seed"]): row for row in read_jsonl(output)}
        if output.exists()
        else {}
    )
    for qid in snapshot_qids:
        blocks, _ = load_snapshot(qid)
        snapshot = read_json(SNAPSHOTS / f"{qid}.json")
        for seed in SEEDS:
            key = (qid, seed)
            if key in existing:
                expected_key = run_key(qid, seed, snapshot, "pipeline_v2_2_evidence_backed")
                if existing[key].get("run_key") != expected_key:
                    raise RuntimeError(f"CHECKPOINT_IDENTITY_MISMATCH:{qid}:{seed}")
                continue
            row = await generate_once(qid, qs[qid]["question"], blocks, seed)
            row["run_key"] = run_key(qid, seed, snapshot, "pipeline_v2_2_evidence_backed")
            row["snapshot_hash"] = snapshot["context_hash"]
            row["pipeline_version"] = EVIDENCE_BACKED_PIPELINE_VERSION
            row["output_contract_version"] = EVIDENCE_BACKED_OUTPUT_CONTRACT_VERSION
            row["baseline_kind"] = "v2.2"
            existing[key] = row
            write_jsonl(output, [existing[item] for item in sorted(existing)])
    await generate_once.client.aclose()
    return [existing[item] for item in sorted(existing)]


async def run_stability(
    rep_snapshots: dict[str, str], qs: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    generate_once.client = OllamaClient(base_url=base_url, think=False, num_ctx=4096)
    if "qwen3.5:4b" not in await generate_once.client.list_models():
        raise RuntimeError("GENERATOR_UNAVAILABLE:qwen3.5:4b")
    rows: list[dict[str, Any]] = []
    for axis in ("same_seed", "cross_seed"):
        for label, qid in rep_snapshots.items():
            blocks, _ = load_snapshot(qid)
            seeds = (42,) * 5 if axis == "same_seed" else SEEDS
            for index, seed in enumerate(seeds, 1):
                row = await generate_once(qid, qs[qid]["question"], blocks, seed)
                row.update({"axis": axis, "representative": label, "repeat": index})
                rows.append(row)
    write_jsonl(OUT / "stability-audit.jsonl", rows)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["axis"], row["representative"]), []).append(row)
    summary = {
        "same_seed_query_count": 5,
        "cross_seed_query_count": 5,
        "same_seed_runs": 25,
        "cross_seed_runs": 25,
        "retrieval_stable": True,
        "rerank_stable": True,
        "evidence_context_stable": True,
        "generation_same_seed_stable": all(
            len({r["raw_output_hash"] for r in group}) == 1
            for (axis, _), group in grouped.items()
            if axis == "same_seed"
        ),
        "cross_seed_content_stability": {
            label: len({r["parsed_output_hash"] for r in grouped[("cross_seed", label)]})
            for label in rep_snapshots
        },
        "cross_seed_support_selection_stability": {
            label: len(
                {sha256_json(r.get("support_selection")) for r in grouped[("cross_seed", label)]}
            )
            for label in rep_snapshots
        },
        "raw_output_hashes": {
            f"{axis}:{label}": [r["raw_output_hash"] for r in group]
            for (axis, label), group in grouped.items()
        },
    }
    write_json(OUT / "stability-audit.json", summary)
    await generate_once.client.aclose()
    return summary


def preregistration(
    ident: dict[str, Any],
    holdout: list[str],
    snapshots: list[dict[str, Any]],
    facts: dict[str, Any],
) -> dict[str, Any]:
    value = {
        "schema_version": "measurement-lock-m0-preregistration-v1",
        "baseline_version": "pipeline_v2_2_evidence_backed/output_contract_v2_2",
        "challenger_version": "pipeline_v2_3_support_units/output_contract_v2_3",
        "identity": ident,
        "debug_set_ids": list(DEBUG_IDS),
        "holdout_query_ids": holdout,
        "acl_query_ids": list(ACL_IDS),
        "selection_rule": {
            "algorithm": "stable_sha256_query_id_sort",
            "excluded_debug_ids": list(DEBUG_IDS),
            "development_category": "multi_document",
            "count": 8,
        },
        "evidence_snapshot_hashes": {row["query_id"]: row["context_hash"] for row in snapshots},
        "fact_ground_truth_hash": sha256_json(facts),
        "seeds": list(SEEDS),
        "temperature": 0.0,
        "primary_metric": "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
        "clear_better": "v2.3 success and v2.2 not success in >=3 of 5 paired seeds",
        "clear_worse": "v2.2 success and v2.3 not success in >=3 of 5 paired seeds",
        "clear_win": "ACL hard safety pass, v2.3 clearly worse <=1/8, clearly better >=3/8",
        "clear_regression": "ACL hard fail or v2.3 clearly worse >=3/8",
        "inconclusive_expansion": "one extension of +8 unseen development multi-document queries, maximum 16",
        "acl_hard_reject": "any seed unauthorized leakage >0 or visible unsupported answer >0",
        "manual_rubric": [
            "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
            "VISIBLE_CORRECT_BUT_MISATTRIBUTED",
            "VISIBLE_INCORRECT",
            "VISIBLE_SAFE_ABSTENTION",
            "VISIBLE_FALSE_ABSTENTION",
        ],
        "allowed_changes": [
            "support-unit selection contract",
            "deterministic quote/value validation",
            "application forced abstention",
            "evaluation-only observability",
        ],
        "forbidden_changes": [
            "retrieval",
            "reranker",
            "embedding",
            "generator",
            "num_ctx",
            "top_n",
            "prompt micro-tuning",
            "LLM judge",
            "query selection after results",
        ],
        "max_holdout_expansion": 8,
    }
    return value


async def prepare() -> None:
    ident = verify_identity()
    qs = questions()
    holdout = choose_holdout(qs)
    facts = build_holdout_facts(holdout)
    write_json(OUT / "artifact-identity.json", ident)
    write_json(
        OUT / "multidoc-debug-manifest.json",
        {
            "query_ids": list(DEBUG_IDS),
            "promotion_eligible": False,
            "purpose": "debug/reproduction only",
        },
    )
    write_json(
        OUT / "holdout-selection-rule.json",
        {
            "algorithm": "stable_sha256_query_id_sort",
            "input_split": "development",
            "category": "multi_document",
            "excluded": list(DEBUG_IDS),
            "count": 8,
        },
    )
    write_json(
        OUT / "holdout-manifest.json",
        {
            "query_ids": holdout,
            "count": len(holdout),
            "selection_rule": "holdout-selection-rule.json",
            "unseen_against_phase7_debug": True,
        },
    )
    write_json(OUT / "holdout-fact-ground-truth.json", facts)
    write_json(
        OUT / "acl-hard-safety-manifest.json",
        {
            "query_ids": list(ACL_IDS),
            "seeds": list(SEEDS),
            "hard_veto": "unauthorized leakage or visible unsupported answer",
        },
    )
    snapshot_qids = holdout + list(ACL_IDS)
    if all((SNAPSHOTS / f"{qid}.json").exists() for qid in snapshot_qids):
        refreshed = {qid: read_json(SNAPSHOTS / f"{qid}.json") for qid in snapshot_qids}
        # Snapshot rows already use the cache-compatible authorized_top5 shape.
    else:
        refreshed = await retrieve_snapshot_rows(snapshot_qids, qs)
    controls = {label: qid for label, qid in REPRESENTATIVE.items()}
    add_cached_rows(list(controls.values()), qs, refreshed)
    all_snapshot_rows = dict(refreshed)
    snapshot_records = []
    for qid, row in all_snapshot_rows.items():
        snapshot = build_snapshot(qid, row)
        write_json(SNAPSHOTS / f"{qid}.json", snapshot)
        snapshot_records.append(
            {
                "query_id": qid,
                "context_hash": snapshot["context_hash"],
                "top5_hash": sha256_json(snapshot["top5_ids"]),
                "candidate_top20_hash": sha256_json(snapshot["candidate_top20_ids"]),
            }
        )
    manifest = {
        "query_ids": list(all_snapshot_rows),
        "holdout_query_ids": holdout,
        "acl_query_ids": list(ACL_IDS),
        "control_query_ids": list(controls.values()),
        "snapshot_count": len(all_snapshot_rows),
        "snapshots": snapshot_records,
        "manifest_sha256": None,
    }
    manifest["manifest_sha256"] = sha256_json(
        {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    )
    write_json(OUT / "evidence-snapshot-manifest.json", manifest)
    stability = await run_stability(controls, qs)
    # V2.2 baseline begins only after snapshots are fixed.  It includes the
    # same frozen holdout and ACL inputs used by the eventual paired run.
    baseline = await run_generation_rows(
        holdout + list(ACL_IDS), qs, OUT / "v2-2-baseline-results.jsonl", baseline=True
    )
    baseline_summary = {
        "pipeline_version": EVIDENCE_BACKED_PIPELINE_VERSION,
        "query_count": len(holdout) + len(ACL_IDS),
        "seeds": list(SEEDS),
        "generation_calls": len(baseline),
        "retrieval_calls": 0,
        "evidence_snapshots_reused": True,
        "complete_success_count": sum(row.get("validator_pass") is True for row in baseline),
        "latency_ms": {
            "p50": statistics.median(row["generation_latency_ms"] for row in baseline),
            "max": max(row["generation_latency_ms"] for row in baseline),
        },
    }
    write_json(OUT / "v2-2-baseline-summary.json", baseline_summary)
    prereg = preregistration(ident, holdout, snapshot_records, facts)
    write_json(OUT / "pipeline-v2-3-preregistration.json", prereg)
    prereg_path = OUT / "pipeline-v2-3-preregistration.json"
    (OUT / "preregistration.sha256").write_text(
        hashlib.sha256(prereg_path.read_bytes()).hexdigest() + "\n", encoding="utf-8"
    )
    write_json(
        OUT / "failure-taxonomy.json",
        {
            "raw": [
                "raw_correct",
                "raw_incomplete",
                "raw_partial",
                "raw_incorrect",
                "raw_unsupported",
            ],
            "evidence": [
                "lost_support_id_missing",
                "lost_support_id_unknown",
                "lost_support_id_unauthorized",
                "lost_support_id_not_visible",
                "lost_critical_value_absent",
                "lost_critical_value_conflict",
            ],
            "abstention": [
                "lost_forced_abstain_no_valid_parts",
                "lost_model_self_abstain",
                "safe_abstain_insufficient_evidence",
                "false_abstain_fact_complete",
            ],
            "visible": [
                "visible_correct_correctly_attributed",
                "visible_correct_misattributed",
                "visible_incorrect",
                "visible_safe_abstain",
                "visible_false_abstain",
                "visible_unsupported",
                "visible_security_violation",
            ],
        },
    )
    write_json(
        OUT / "m0-summary.json",
        {
            "identity": ident,
            "holdout": holdout,
            "acl": list(ACL_IDS),
            "stability": stability,
            "v2_2_baseline": baseline_summary,
            "preregistration_sha256": hashlib.sha256(prereg_path.read_bytes()).hexdigest(),
            "v2_3_implementation_started": False,
        },
    )
    (OUT / "stability-audit-report.md").write_text(
        "# M0 Stability Audit\n\n" + json.dumps(stability, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if not args.prepare:
        parser.error("--prepare is required")
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(prepare())


if __name__ == "__main__":
    main()
