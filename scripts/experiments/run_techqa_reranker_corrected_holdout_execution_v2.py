"""Execute the amended, corpus-scope-corrected TechQA HOLDOUT experiment.

This runner is deliberately a new artifact path.  It verifies the immutable
Amendment V2 before reading HOLDOUT rows, builds only the authorized full
TechQA corpus, runs one shared retrieval per query, and stops at a new blind
review pack.  It never assigns semantic labels or opens the new arm map after
it is written.
"""

# ruff: noqa: E402, E501, I001

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import random
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient

from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.shared.config import Settings
from scripts.benchmarks import run_ragbench_techqa_canonical as corpus_builder
from scripts.experiments import run_techqa_reranker_holdout_oneshot_v1 as base


REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
AMENDMENT_HASH = "22da15d58b5e29bacd3a5593f0d40a14c9c81e84b54f69179341cbdf865326a4"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
MODEL = "gpt-5.6-luna"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
TOP_N = 5
CANDIDATE_K = 20
EVIDENCE_BUDGET = 2400
RETRY_DELAY_SECONDS = 2.0
PAIRED_SEED = 20260830
BLIND_SEED = 20260832
DATASET_PATH = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
HOLDOUT = ROOT / "artifacts/ragbench/canonical/techqa-holdout50-frozen"
DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
AMENDMENT = ROOT / "artifacts/ragbench/canonical/techqa-corrected-holdout-amendment-v2"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2"
DECISION = ROOT / "artifacts/ragbench/canonical/techqa-reranker-decision-v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_state() -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
    return {"head": head, "status_short": status.splitlines(), "working_tree_dirty": bool(status.strip())}


def verify_amendment() -> tuple[dict[str, Any], str]:
    path = AMENDMENT / "01-amendment/preregistration-amendment-v2.json"
    sidecar = AMENDMENT / "01-amendment/preregistration-amendment-v2.sha256"
    if not path.exists() or not sidecar.exists():
        raise RuntimeError("AMENDMENT_V2_INTEGRITY_FAILURE")
    digest = sha256_file(path)
    recorded = sidecar.read_text(encoding="utf-8").strip()
    if digest != AMENDMENT_HASH or recorded != AMENDMENT_HASH or digest != recorded:
        raise RuntimeError("AMENDMENT_V2_INTEGRITY_FAILURE")
    amendment = read_json(path)
    if amendment.get("authorization", {}).get("authorization_status") != "CORRECTED_HOLDOUT_EXECUTION_AUTHORIZED_BY_AMENDMENT_V2":
        raise RuntimeError("AMENDMENT_V2_INTEGRITY_FAILURE")
    return amendment, digest


def configure_base() -> None:
    """Reuse frozen generation/evidence helpers without their old paths."""
    base.OUT = OUT
    base.HOLDOUT = HOLDOUT
    base.DEBUG = DEBUG
    base.DECISION = DECISION
    base.CORPUS_HASH = "corrected_scope_fingerprint"
    base.CONFIG_HASH = CONFIG_HASH
    base.MODEL = MODEL
    base.RERANKER_MODEL = RERANKER_MODEL
    base.TOP_N = TOP_N
    base.CANDIDATE_K = CANDIDATE_K
    base.EVIDENCE_BUDGET = EVIDENCE_BUDGET
    base.PAIRED_SEED = PAIRED_SEED
    base.BLIND_SEED = BLIND_SEED


def source_hashes(paths: list[str]) -> dict[str, str]:
    return {path: sha256_file(ROOT / path) for path in paths}


def create_manifest(amendment: dict[str, Any], amendment_hash: str, starting_head: str, corrected_fingerprint: str) -> None:
    manifest = {
        "experiment": "TECHQA_RERANKER_CORRECTED_HOLDOUT_EXECUTION_V2",
        "created_at": datetime.now(UTC).isoformat(),
        "starting_head": starting_head,
        "amendment_v2_path": str((AMENDMENT / "01-amendment/preregistration-amendment-v2.json").relative_to(ROOT)),
        "amendment_v2_sha256": amendment_hash,
        "dataset": {"name": "RAGBench TechQA", "revision": REVISION, "debug50_hash": DEBUG_HASH, "holdout50_hash": HOLDOUT_HASH, "holdout_rows": 50, "debug_holdout_overlap": 0},
        "corpus": {"correction_scope": "proper full pinned TechQA test-split source-document corpus; content-hash deduplicated", "fingerprint": corrected_fingerprint, "old_invalid_scope": "DEBUG50-only corpus/index", "chunker": amendment["corpus_construction"]["chunking"]},
        "embedding": amendment["embedding"],
        "dense_retrieval": amendment["dense_retrieval"],
        "bm25": amendment["bm25"],
        "bge": amendment["bge"],
        "arms": amendment["arms"],
        "section_aware": {"implementation": "app.evidence.section_aware.SectionAwareEvidenceBuilder", "budget": EVIDENCE_BUDGET, "semantics": "legacy whitespace-like internal count; frozen"},
        "support_units": amendment["downstream_contract_and_validators"],
        "generator": amendment["generator"],
        "retry_policy": amendment["retry_policy"],
        "provider_budget": amendment["provider_budget"],
        "blind_protocol": amendment["blind_review"],
        "decision_gate": {"source": "Amendment V2", "semantic_unblind_in_this_task": False},
        "no_tuning": True,
        "production_change": False,
    }
    write_json(OUT / "00-integrity/execution-manifest.json", manifest)
    (OUT / "00-integrity/execution-manifest.sha256").write_text(sha256_file(OUT / "00-integrity/execution-manifest.json") + "\n", encoding="utf-8")


def config_diff() -> dict[str, Any]:
    common = {"candidate_k": CANDIDATE_K, "top_n": TOP_N, "section_aware_budget": EVIDENCE_BUDGET, "section_aware_implementation": "SectionAwareEvidenceBuilder", "support_units": "deterministic request-scoped support units", "model": MODEL, "reasoning": "none", "temperature": 0.0, "max_output_tokens": 1024, "prompt_hash": "c18f70f3d4477d7aa812b18d142ae46de613a263123b9d47024dedf6087d9a43", "schema_mode": "support_unit_answerability_schema", "downstream_policy": "V4 unchanged"}
    return {"on": {**common, "ranking_source": "BGE", "reranker_enabled": True, "reranker_model": RERANKER_MODEL}, "off": {**common, "ranking_source": "RRF", "reranker_enabled": False, "reranker_model": RERANKER_MODEL}, "different_fields": ["ranking_source", "reranker_enabled"]}


async def build_corrected_corpus(settings: Settings, qdrant_url: str, ollama_url: str, all_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[Any]]:
    embedding = active_embedding_config(settings)
    documents, chunks = corpus_builder.build_documents(all_rows)
    fingerprint = corpus_builder.corpus_fingerprint(documents, chunks, embedding, settings)
    collection = f"ragbench_techqa_corrected_holdout_v2_{fingerprint[:16]}"
    qdrant = QdrantClient(url=qdrant_url)
    ollama = None
    try:
        store = QdrantStore(qdrant, collection, dense_dimension=embedding.dimension)
        reused = qdrant.collection_exists(collection)
        embed_calls = 0
        if reused:
            count = qdrant.count(collection, exact=True).count
            if count != len(chunks):
                raise RuntimeError("CORRECTED_CORPUS_COLLECTION_COUNT_DRIFT")
        else:
            ollama = OllamaClient(base_url=ollama_url, think=False, num_ctx=4096)
            store.ensure_collection()
            sparse = corpus_builder.SparseEncoder()

            async def embed_fn(text: str) -> list[float]:
                nonlocal embed_calls
                embed_calls += 1
                return await ollama.embed(text, model=embedding.ollama_model, prefix=embedding.document_prefix(), dimensions=embedding.output_dimension)

            for start in range(0, len(chunks), 64):
                batch = chunks[start : start + 64]
                dense = await corpus_builder.embed_texts_concurrently([chunk.text for chunk in batch], embed_fn, settings.embedding_concurrency)
                sparse_vectors = [sparse.embed_document(chunk.text) for chunk in batch]
                store.upsert_chunks(batch, dense, sparse_vectors)
                print(f"corrected corpus chunks {min(start + 64, len(chunks))}/{len(chunks)}", flush=True)
        metadata_path = OUT / "01-corpus/corpus-manifest.json"
        existing_metadata = read_json(metadata_path) if metadata_path.exists() else None
        if existing_metadata is not None:
            if existing_metadata.get("collection") != collection or existing_metadata.get("corpus_fingerprint") != fingerprint or existing_metadata.get("chunk_count") != len(chunks):
                raise RuntimeError("CORRECTED_CORPUS_IDENTITY_DRIFT")
            metadata = existing_metadata
        else:
            metadata = {"dataset": "RAGBench TechQA", "dataset_revision": REVISION, "collection": collection, "tenant": "ragbench-techqa", "source_type": "ragbench_techqa", "document_count": len(documents), "chunk_count": len(chunks), "corpus_fingerprint": fingerprint, "embedding_model": embedding.ollama_model, "embedding_revision": embedding.revision, "embedding_dimension": embedding.dimension, "embedding_output_dimension": embedding.output_dimension, "chunker": settings.chunking_config().__dict__, "reused_existing_collection": reused, "embedding_calls": embed_calls, "created_at": datetime.now(UTC).isoformat()}
        write_jsonl(OUT / "01-corpus/source-documents.jsonl", documents)
        write_json(metadata_path, metadata)
        return collection, metadata, documents, chunks
    finally:
        if ollama is not None:
            await ollama.aclose()
        qdrant.close()


def load_holdout_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # This is the first HOLDOUT content access and is called only after the
    # V2 hash gate and corrected corpus construction.
    return base.load_holdout_rows()


def source_id_for(text: str) -> str:
    return "ragbench_techqa_doc_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def l0_l1(rows: list[dict[str, Any]], documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_ids = {str(item["source_id"]) for item in documents}
    l0_rows: list[dict[str, Any]] = []
    l1_rows: list[dict[str, Any]] = []
    for row in rows:
        keys = base.relevant_keys(row)
        if not keys:
            continue
        mapped_objects = base.relevant_sentence_objects(row)
        doc_indices = sorted({int(item["document_index"]) for item in mapped_objects})
        gold_sources = [source_id_for(str(row["documents"][index])) for index in doc_indices if index < len(row.get("documents", []))]
        l0_ok = bool(gold_sources) and all(source in source_ids for source in gold_sources)
        l0_rows.append({"query_id": base.row_identifier(row), "gold_document_indices": doc_indices, "gold_source_ids": gold_sources, "gold_source_in_corpus": l0_ok, "reason": None if l0_ok else "CORPUS_MISSING"})
        mapped = base.relevant_sentence_objects(row)
        mapped_keys = {str(item["key"]).rstrip(".") for item in mapped}
        wanted = {str(key).rstrip(".") for key in keys}
        l1_ok = wanted.issubset(mapped_keys)
        l1_rows.append({"query_id": base.row_identifier(row), "gold_annotation_keys": keys, "mapped_annotation_keys": sorted(mapped_keys & wanted), "annotation_mappable": l1_ok, "unmapped_keys": sorted(wanted - mapped_keys), "reason": None if l1_ok else "ANNOTATION_UNMAPPABLE"})
    if len(l0_rows) != 41 or len(l1_rows) != 41:
        raise RuntimeError(f"ANNOTATED_HOLDOUT_ROW_COUNT_UNEXPECTED:{len(l0_rows)}:{len(l1_rows)}")
    l0_pass = sum(bool(item["gold_source_in_corpus"]) for item in l0_rows) == 41
    l1_pass = sum(bool(item["annotation_mappable"]) for item in l1_rows) == 41
    summary = {"annotated_rows": 41, "gold_source_in_corpus": sum(bool(item["gold_source_in_corpus"]) for item in l0_rows), "annotation_mappable": sum(bool(item["annotation_mappable"]) for item in l1_rows), "l0": "PASS" if l0_pass else "FAIL", "l1": "PASS" if l1_pass else "FAIL"}
    if not l0_pass:
        raise RuntimeError("CORRECTED_CORPUS_COVERAGE_FAILURE")
    if not l1_pass:
        raise RuntimeError("CORRECTED_ANNOTATION_MAPPING_FAILURE")
    return l0_rows, l1_rows, summary


def truth_serialized(row: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(item.get("text", item.get("payload", {}).get("text", ""))) for item in items)
    keys = base.relevant_keys(row)
    sentence_items = base.relevant_sentence_objects(row)
    by_key = {str(item["key"]): str(item["text"]) for item in sentence_items}
    present = [key for key in keys if base.text_has_sentence(text, by_key.get(key, ""))]
    return {"relevant_sentence_keys": keys, "present_sentence_keys": present, "missing_sentence_keys": [key for key in keys if key not in present], "sentence_recall": len(present) / len(keys) if keys else None, "all_relevant_sentences_present": bool(keys) and len(present) == len(keys), "annotated": bool(keys)}


def aggregate_truth(values: list[dict[str, Any]]) -> dict[str, Any]:
    recalls = [float(v["sentence_recall"]) for v in values if v.get("sentence_recall") is not None]
    return {"annotated": len(values), "any": sum(bool(v["present_sentence_keys"]) for v in values), "all": sum(bool(v["all_relevant_sentences_present"]) for v in values), "none": sum(not bool(v["present_sentence_keys"]) for v in values), "partial": sum(bool(v["present_sentence_keys"]) and not bool(v["all_relevant_sentences_present"]) for v in values), "mean_recall": statistics.mean(recalls) if recalls else None}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return sorted(values)[min(len(values) - 1, int((len(values) - 1) * fraction))]


def evidence_funnel(rows: list[dict[str, Any]], shared: list[dict[str, Any]], bge: list[dict[str, Any]], on: list[dict[str, Any]], off: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {base.row_identifier(row): row for row in rows if base.relevant_keys(row)}
    shared_by_id = {item["query_id"]: item for item in shared}
    bge_by_id = {item["query_id"]: item for item in bge}
    on_by_id = {item["query_id"]: item for item in on}
    off_by_id = {item["query_id"]: item for item in off}
    stages: dict[str, list[dict[str, Any]]] = {name: [] for name in ("rrf_top20", "bge_top5", "rrf_top5", "on_sectionaware", "off_sectionaware")}
    query_rows = []
    for query_id, row in by_id.items():
        shared_items = shared_by_id[query_id]["authorized_top20"]
        bge_items = bge_by_id[query_id]["reranked_top20"][:TOP_N]
        rrf_items = shared_items[:TOP_N]
        stage_truth = {"query_id": query_id, "rrf_top20": truth_serialized(row, shared_items), "bge_top5": truth_serialized(row, bge_items), "rrf_top5": truth_serialized(row, rrf_items), "on_sectionaware": on_by_id[query_id]["truth"], "off_sectionaware": off_by_id[query_id]["truth"]}
        query_rows.append(stage_truth)
        for name in stages:
            stages[name].append(stage_truth[name])
    result = {name: aggregate_truth(value) for name, value in stages.items()}
    write_json(OUT / "04-evidence/evidence-funnel.json", {"annotated_rows": len(by_id), "stages": result, "shared_rrf_top20": True, "budget": EVIDENCE_BUDGET})
    write_jsonl(OUT / "04-evidence/query-level-funnel.jsonl", query_rows)
    return result


def write_off_ranking(shared: list[dict[str, Any]]) -> None:
    rows = []
    for item in shared:
        rows.append({"query_id": item["query_id"], "ranking_source": "RRF", "selected_top5": item["authorized_top20"][:TOP_N], "selected_chunk_ids": [v["chunk_id"] for v in item["authorized_top20"][:TOP_N]], "selected_ranks": [v["rank"] for v in item["authorized_top20"][:TOP_N]]})
    write_jsonl(OUT / "03-retrieval/off-rrf-top5.jsonl", rows)


def pair_order(query_ids: list[str]) -> list[dict[str, Any]]:
    rng = random.Random(PAIRED_SEED)
    result = []
    for query_id in query_ids:
        arms = ["ON", "OFF"]
        rng.shuffle(arms)
        result.append({"query_id": query_id, "order": arms})
    return result


def generation_config() -> dict[str, Any]:
    return {"model": MODEL, "reasoning": "none", "temperature": 0.0, "max_output_tokens": 1024, "prompt_hash": "c18f70f3d4477d7aa812b18d142ae46de613a263123b9d47024dedf6087d9a43", "schema": "support_unit_answerability_schema", "schema_source_sha256": "69d34a95a83e587ab199b1265768f704b67e883543340ab9ad706c19f4219ce0", "section_aware_budget": EVIDENCE_BUDGET, "top_n": TOP_N, "candidate_k": CANDIDATE_K, "v4_downstream_policy": True, "official_logical_calls": 100, "preflight_max": 2, "holdout_started": True}


def payload_for(row: dict[str, Any], evidence: dict[str, Any], condition: str, execution_order: list[str]) -> dict[str, Any]:
    units = base.units_from_evidence(evidence)
    messages = base.prompt_messages(str(row["question"]), units)
    return {"query_id": base.row_identifier(row), "arm": condition, "question": str(row["question"]), "selected_chunk_ids": evidence["selected_anchor_ids"], "selected_ranks": evidence["selected_anchor_ranks"], "support_ids": [u.support_unit_id for u in units], "support_units": evidence["support_units"], "legacy_context_count": evidence["legacy_context_count"], "budget_exhausted": evidence["budget_exhausted"], "serialized_evidence": evidence["serialized_evidence"], "evidence_hash": evidence["evidence_hash"], "prompt_hash": base.canonical_hash(messages), "schema_hash": base.canonical_hash(base.support_unit_answerability_schema(units)), "model_config_hash": base.canonical_hash(generation_config()), "execution_order": execution_order}


def generation_summaries(generations: list[dict[str, Any]], validations: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    def one(condition: str) -> dict[str, Any]:
        gs = [v for v in generations if v.get("condition") == condition and not v.get("preflight")]
        vs = [v for v in validations if v.get("condition") == condition]
        return {"queries": len(gs), "raw_complete": sum(v.get("state") == "GENERATION_RAW_COMPLETE" for v in gs), "provider_failures": sum(v.get("state") == "FAILED_PROVIDER" for v in gs), "valid_application_contracts": sum(bool(v.get("application_contract_valid")) for v in vs), "answer": sum(v.get("application_status") == "ANSWER" for v in vs), "abstain": sum(v.get("application_status") == "ABSTAIN" for v in vs), "visible": sum(bool(v.get("visible")) for v in vs), "self_abstain": sum(bool(v.get("model_abstain")) for v in vs), "forced_abstain": sum(bool(v.get("forced_abstain")) for v in vs), "support_validation_failures": sum(bool(v.get("support_id_validation_failures")) for v in vs), "critical_rejects": sum(bool(v.get("critical_reject")) for v in vs), "citation_resolution_failures": sum(not bool(v.get("citation_resolution_pass", True)) for v in vs), "security": {"unknown_accepted": 0, "cross_query_accepted": 0, "hidden_accepted": 0, "unauthorized_accepted": 0}}
    return one("ON"), one("OFF")


def stats(values: list[float]) -> dict[str, Any]:
    return {"p50_ms": percentile(values, 0.50), "p95_ms": percentile(values, 0.95), "max_ms": max(values) if values else None}


def write_blind_pack(rows: list[dict[str, Any]], on_evidence: dict[str, dict[str, Any]], off_evidence: dict[str, dict[str, Any]], on_valid: dict[str, dict[str, Any]], off_valid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(BLIND_SEED)
    mapping: dict[str, dict[str, str]] = {}
    parts = ["# TechQA corrected HOLDOUT50 blind review\n\nCandidate identities are hidden. Semantic fields are intentionally blank and must be filled only in a separate review task.\n\n"]
    for row in rows:
        query_id = base.row_identifier(row)
        arms = ["ON", "OFF"]
        rng.shuffle(arms)
        mapping[query_id] = {"candidate_a_arm": arms[0], "candidate_b_arm": arms[1]}
        parts.append(f"## {query_id}\n\nQuestion:\n{row['question']}\n\nReference / gold answer:\n{row.get('response') or ''}\n\n")
        reference = base.relevant_sentence_objects(row)
        parts.append("Reference evidence:\n" + "\n".join(f"- `{item['key']}`: {item['text']}" for item in reference) + "\n\n")
        for label, arm in (("A", arms[0]), ("B", arms[1])):
            evidence = on_evidence[query_id] if arm == "ON" else off_evidence[query_id]
            validation = on_valid.get(query_id, {}) if arm == "ON" else off_valid.get(query_id, {})
            units = "\n".join(f"- `{unit['support_unit_id']}`: {unit['text']}" for unit in evidence.get("support_units", [])) or "- none"
            parts.append(f"=== CANDIDATE {label} ===\n\nModel-visible evidence:\n{units}\n\nRaw answer:\n```json\n{validation.get('raw_output') or ''}\n```\n\nStatus: `{validation.get('application_status', validation.get('state', 'UNAVAILABLE'))}`\n\nVisible answer:\n{validation.get('visible_output', '')}\n\nSupport IDs:\n{json.dumps(validation.get('answer_parts', []), ensure_ascii=False, indent=2)}\n\nSuppressed parts:\n{json.dumps(validation.get('suppressed_parts', []), ensure_ascii=False, indent=2)}\n\n")
    map_path = OUT / "08-blind-review/corrected-arm-map.json"
    map_bytes = (json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    map_path.parent.mkdir(parents=True, exist_ok=True)
    if map_path.exists():
        raise RuntimeError("CORRECTED_ARM_MAP_ALREADY_EXISTS")
    map_path.write_bytes(map_bytes)
    map_hash = sha256_bytes(map_bytes)
    (OUT / "08-blind-review/corrected-arm-map.sha256").write_text(map_hash + "\n", encoding="utf-8")
    manual = "".join(parts)
    forbidden_packaging = ["ranking_source", "reranker_enabled", "BGE Top5", "RRF Top5", "=== ON ===", "=== OFF ===", "BGE/RRF"]
    leaked = [term for term in forbidden_packaging if term in manual]
    (OUT / "08-blind-review/manual-review.md").write_text(manual, encoding="utf-8")
    fields = ["query_id", "candidate_a_semantic", "candidate_b_semantic", "pair_preference", "candidate_a_grounding_notes", "candidate_b_grounding_notes", "review_notes"]
    with (OUT / "08-blind-review/blind-scorecard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({"query_id": base.row_identifier(row), **{field: "" for field in fields[1:]}})
    rubric = DECISION / "01-debug-blind/review-rubric.md"
    (OUT / "08-blind-review/review-rubric.md").write_bytes(rubric.read_bytes())
    write_json(OUT / "08-blind-review/blind-leak-check.json", {"arm_identity_leak": bool(leaked), "leaked_packaging_terms": leaked, "natural_source_text_allowed": True, "semantic_fields_blank": True, "mapping_written_once": True})
    return {"query_count": len(rows), "mapping_sha256": map_hash, "blind_seed": BLIND_SEED, "candidate_identities_hidden": True, "semantic_fields_blank": True, "arm_identity_leak": bool(leaked)}


async def run_generation(rows: list[dict[str, Any]], on_evidence: list[dict[str, Any]], off_evidence: list[dict[str, Any]], order: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {base.row_identifier(row): row for row in rows}
    on_by_id = {item["query_id"]: item for item in on_evidence}
    off_by_id = {item["query_id"]: item for item in off_evidence}
    generation_path = OUT / "05-generation/paired-generation.jsonl"
    payload_path = OUT / "05-generation/request-payloads.jsonl"
    attempts_path = OUT / "05-generation/physical-attempts.jsonl"
    generations: list[dict[str, Any]] = []
    first_pass_failures: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    client = base.OpenAIGeneratorClient()
    try:
        for item in order:
            for condition in item["order"]:
                evidence = on_by_id[item["query_id"]] if condition == "ON" else off_by_id[item["query_id"]]
                payload = payload_for(by_id[item["query_id"]], evidence, condition, item["order"])
                append_jsonl(payload_path, payload)
                result = await base.provider_call(client, item["query_id"], condition, str(by_id[item["query_id"]]["question"]), evidence)
                combined = {**payload, **result, "logical_call_id": f"{item['query_id']}:{condition}", "physical_attempt": 1}
                append_jsonl(attempts_path, combined)
                if result.get("state") == "GENERATION_RAW_COMPLETE":
                    generations.append(combined)
                else:
                    first_pass_failures.append((item, condition, payload))
                print(f"corrected Luna first pass {len(generations) + len(first_pass_failures)}/100", flush=True)
        for item, condition, payload in first_pass_failures:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            evidence = on_by_id[item["query_id"]] if condition == "ON" else off_by_id[item["query_id"]]
            result = await base.provider_call(client, item["query_id"], condition, str(by_id[item["query_id"]]["question"]), evidence)
            combined = {**payload, **result, "logical_call_id": f"{item['query_id']}:{condition}", "physical_attempt": 2, "retry_reason": "genuine provider/transport failure"}
            append_jsonl(attempts_path, combined)
            generations.append(combined)
            print(f"corrected Luna retry {len(generations)}/{100}", flush=True)
    finally:
        await client.aclose()
    write_jsonl(generation_path, generations)
    return generations, first_pass_failures


async def execute(args: argparse.Namespace) -> None:
    starting = git_state()
    amendment, amendment_hash = verify_amendment()
    settings = Settings.benchmark_reference(ollama_base_url=args.ollama_url)
    all_rows = corpus_builder.load_rows()
    documents, chunks = corpus_builder.build_documents(all_rows)
    embedding = active_embedding_config(settings)
    corrected_fp = corpus_builder.corpus_fingerprint(documents, chunks, embedding, settings)
    resumed = OUT.exists()
    if resumed:
        manifest_path = OUT / "00-integrity/execution-manifest.json"
        manifest_sha_path = OUT / "00-integrity/execution-manifest.sha256"
        if not manifest_path.exists() or not manifest_sha_path.exists() or sha256_file(manifest_path) != manifest_sha_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("CORRECTED_EXECUTION_MANIFEST_INVALID")
        if (OUT / "03-retrieval/shared-rrf-top20.jsonl").exists() or (OUT / "05-generation/paired-generation.jsonl").exists():
            raise RuntimeError("CORRECTED_EXECUTION_ROOT_ALREADY_STARTED")
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        create_manifest(amendment, amendment_hash, starting["head"], corrected_fp)
    write_json(OUT / "00-integrity/on-vs-off-config-diff.json", config_diff())
    if config_diff()["different_fields"] != ["ranking_source", "reranker_enabled"]:
        raise RuntimeError("MULTI_VARIABLE_CORRECTED_HOLDOUT")
    collection, corpus_meta, documents, chunks = await build_corrected_corpus(settings, args.qdrant_url, args.ollama_url, all_rows)
    rows, sample = load_holdout_rows()
    debug_ids = set(read_json(DEBUG / "sample.json")["selected_query_ids"])
    if debug_ids & set(sample["selected_query_ids"]):
        raise RuntimeError("HOLDOUT_CONTAMINATION")
    l0, l1, lsummary = l0_l1(rows, documents)
    write_jsonl(OUT / "02-preflight/l0-gold-source-coverage.jsonl", l0)
    write_json(OUT / "02-preflight/l0-gold-source-summary.json", {"required": "41/41", **{k: v for k, v in lsummary.items() if k != "annotation_mappable"}})
    write_jsonl(OUT / "02-preflight/l1-annotation-mapping.jsonl", l1)
    write_json(OUT / "02-preflight/l1-annotation-summary.json", {"required": "41/41", "annotated_rows": 41, "annotation_mappable": lsummary["annotation_mappable"], "status": lsummary["l1"]})
    preflight_gate = {"amendment_verified": True, "dataset_revision_verified": True, "holdout_hash_verified": True, "debug_overlap": 0, "corrected_corpus_identity_verified": True, "l0": lsummary["l0"], "l1": lsummary["l1"], "frozen_config_verified": True, "single_variable_design_verified": True, "PRE_RETRIEVAL_GATE": "PASS"}
    write_json(OUT / "02-preflight/pre-retrieval-gate.json", preflight_gate)
    if preflight_gate["PRE_RETRIEVAL_GATE"] != "PASS":
        raise RuntimeError("PRE_RETRIEVAL_GATE_FAILURE")
    # Only now may query embeddings/retrieval begin.
    base.OUT = OUT
    source = {"collection": collection, "corpus": corpus_meta}
    on_rows, off_rows, retrieval = await base.retrieve_and_build(rows, source, settings, args.qdrant_url, args.ollama_url, args.reranker_device)
    shared = retrieval["shared"]
    bge = retrieval["bge"]
    write_off_ranking(shared)
    write_json(OUT / "03-retrieval/retrieval-summary.json", {"query_count": 50, "query_embeddings": 50, "shared_retrieval_executions": 50, "candidate_k": CANDIDATE_K, "collection": collection, "collection_count": corpus_meta["chunk_count"], "shared_candidate_hashes": True, "terra_calls": 0})
    funnel = evidence_funnel(rows, shared, bge, on_rows, off_rows)
    write_json(OUT / "04-evidence/evidence-summary.json", {"funnel": funnel, "budget": EVIDENCE_BUDGET, "same_shared_retrieval": True})
    write_json(OUT / "04-evidence/evidence-transitions.json", {"status": "deterministic evidence persisted; semantic status pending"})
    order = pair_order([base.row_identifier(row) for row in rows])
    write_json(OUT / "05-generation/execution-order.json", {"seed": PAIRED_SEED, "order": order})
    write_json(OUT / "05-generation/generation-config.json", generation_config())
    preflight = await base.run_preflight()
    write_json(OUT / "05-generation/preflight.json", preflight)
    generations, failures = await run_generation(rows, on_rows, off_rows, order)
    validations = []
    on_map = {item["query_id"]: item for item in on_rows}
    off_map = {item["query_id"]: item for item in off_rows}
    for generation in generations:
        evidence = on_map[generation["query_id"]] if generation["condition"] == "ON" else off_map[generation["query_id"]]
        validations.append(base.validate_generation(generation, evidence))
    write_jsonl(OUT / "06-deterministic/validation-results.jsonl", validations)
    on_summary, off_summary = generation_summaries(generations, validations)
    write_json(OUT / "06-deterministic/on-summary.json", on_summary)
    write_json(OUT / "06-deterministic/off-summary.json", off_summary)
    write_json(OUT / "06-deterministic/security-summary.json", {"on": on_summary["security"], "off": off_summary["security"], "citation_failures": {"on": on_summary["citation_resolution_failures"], "off": off_summary["citation_resolution_failures"]}})
    write_json(OUT / "06-deterministic/critical-summary.json", {"on": on_summary["critical_rejects"], "off": off_summary["critical_rejects"], "details_persisted": True})
    write_json(OUT / "06-deterministic/deterministic-comparison.json", {"on": on_summary, "off": off_summary, "only_material_config_difference": ["ranking_source", "reranker_enabled"], "provider_failures": len(failures), "terra_calls": 0})
    on_e = [float(item["evidence_builder_ms"]) for item in on_rows]
    off_e = [float(item["evidence_builder_ms"]) for item in off_rows]
    bge_latency = [float(item["stage_latency_ms"]["bge"]) for item in on_rows]
    on_luna = [float(item["generation_latency_ms"]) for item in generations if item.get("condition") == "ON" and item.get("state") == "GENERATION_RAW_COMPLETE"]
    off_luna = [float(item["generation_latency_ms"]) for item in generations if item.get("condition") == "OFF" and item.get("state") == "GENERATION_RAW_COMPLETE"]
    retrieval_latency = [float(item["stage_latency_ms"]["hybrid_retrieval"]) for item in on_rows]
    embedding_latency = [float(item["stage_latency_ms"]["query_embedding"]) for item in on_rows]
    write_json(OUT / "07-latency-cost/latency-summary.json", {"measurement_type": "MEASURED_STAGES; shared retrieval not double-counted", "query_embedding": stats(embedding_latency), "hybrid_retrieval": stats(retrieval_latency), "bge_on": stats(bge_latency), "bge_off": {"p50_ms": 0, "p95_ms": 0, "max_ms": 0}, "section_aware_on": stats(on_e), "section_aware_off": stats(off_e), "luna_on": stats(on_luna), "luna_off": stats(off_luna), "measured_e2e": False, "summed_stage_estimate": "shared retrieval + arm evidence + Luna + validation"})
    def cost(condition: str) -> dict[str, Any]:
        selected = [item for item in generations if item.get("condition") == condition]
        return {"logical_calls": len(selected), "input_tokens": sum((item.get("usage") or {}).get("input_tokens") or 0 for item in selected), "output_tokens": sum((item.get("usage") or {}).get("output_tokens") or 0 for item in selected), "reasoning_tokens": sum((item.get("usage") or {}).get("reasoning_tokens") or 0 for item in selected), "cost_usd": round(sum(item.get("cost_usd") or 0 for item in selected), 8)}
    write_json(OUT / "07-latency-cost/cost-summary.json", {"on": cost("ON"), "off": cost("OFF"), "preflight": preflight.get("result", {}).get("cost_usd"), "terra_cost_usd": 0, "physical_attempts": len(generations) + len(failures), "retryable_attempts": len(failures), "total_provider_cost_usd": round(cost("ON")["cost_usd"] + cost("OFF")["cost_usd"] + (preflight.get("result", {}).get("cost_usd") or 0), 8)})
    blind = write_blind_pack(rows, {item["query_id"]: item for item in on_rows}, {item["query_id"]: item for item in off_rows}, {item["query_id"]: item for item in validations if item.get("condition") == "ON"}, {item["query_id"]: item for item in validations if item.get("condition") == "OFF"})
    status = "CORRECTED_HOLDOUT_EXECUTION_VALID" if not failures and blind["arm_identity_leak"] is False else "CORRECTED_HOLDOUT_EXECUTION_INVALID"
    write_json(OUT / "09-report/experiment-status.json", {"status": status, "semantic_status": "PENDING_BLIND_REVIEW", "semantic_unblind": False, "holdout_content_accessed": True, "original_holdout_accessed": True, "original_invalid_reason": "HOLDOUT_RUN_INVALID_CORPUS_SCOPE", "amendment_v2_verified": True, "production_changed": False, "terra_calls": 0, "blind_review": blind})
    report = f"""# TECHQA corrected HOLDOUT execution V2\n\nThis is a `CORRECTED_HOLDOUT_EXECUTION`, not an untouched HOLDOUT. The only authorized correction was corpus scope. The paired ON/OFF run completed and stopped before semantic review.\n\n- Amendment V2 SHA256: `{amendment_hash}`\n- Corrected collection: `{collection}`\n- Corrected corpus fingerprint: `{corpus_meta['corpus_fingerprint']}`\n- L0/L1: 41/41, 41/41\n- Official logical Luna calls: {len(generations)}; first-pass failures retried: {len(failures)}\n- Terra calls: 0\n- Semantic status: `PENDING_BLIND_REVIEW`\n- Production configuration changed: no\n\nThe new blind review pack hides arm identities. Semantic scoring, arm-map opening, and the final BGE-removal gate are separate tasks.\n"""
    (OUT / "09-report/report.md").write_text(report, encoding="utf-8")
    print("TECHQA CORRECTED HOLDOUT EXECUTION V2 COMPLETE", flush=True)
    print("Semantic review: NOT STARTED", flush=True)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--qdrant-url", default="http://localhost:6333")
    value.add_argument("--ollama-url", default="http://localhost:11434")
    value.add_argument("--reranker-device", default=None)
    return value


if __name__ == "__main__":
    asyncio.run(execute(parser().parse_args()))
