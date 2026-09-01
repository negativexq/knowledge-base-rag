"""Create the immutable authorization amendment for corrected TechQA HOLDOUT.

This script reads only audit/provenance/config source artifacts.  It never
reads HOLDOUT rows or arm maps and never executes the corrected experiment.
"""

# ruff: noqa: E501, UP017, UP024

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "artifacts/ragbench/canonical"
AUDIT = CANONICAL / "techqa-holdout-measurement-validity-audit-v1"
RECON = CANONICAL / "techqa-amendment-provenance-reconciliation-v1"
DEBUG_RUN = CANONICAL / "techqa-reranker-removal-debug-v1"
V1 = AUDIT / "05-amendment/preregistration-amendment-v1.json"
V1_SIDECAR = AUDIT / "05-amendment/preregistration-amendment-v1.sha256"
ROOT_CAUSE = AUDIT / "04-root-cause/root-cause.json"
ROOT_CAUSE_REPORT = AUDIT / "04-root-cause/root-cause.md"
AUDIT_REPORT = AUDIT / "06-report/report.md"
RECON_VERDICT = RECON / "05-verdict/verdict.json"
RECON_REPORT = RECON / "07-report/report.md"
DEBUG_GENERATION_CONFIG = DEBUG_RUN / "generation-config.json"
OUT = CANONICAL / "techqa-corrected-holdout-amendment-v2"
TARGET = OUT / "01-amendment/preregistration-amendment-v2.json"
SIDECAR = OUT / "01-amendment/preregistration-amendment-v2.sha256"
EXPECTED_V1_REPORTED = "dd4310b1717a16733e765de3c1d7fa76c9b58cddde43750e2f3bf4d4410b2fe8"

DATASET_REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
OLD_CORPUS_HASH = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"

CODE_FILES = [
    "app/ingestion/chunking_config.py",
    "app/ingestion/chunker.py",
    "app/ingestion/markdown_chunker.py",
    "app/llm/embedding_models.py",
    "app/retrieval/hybrid_search.py",
    "app/retrieval/search.py",
    "app/retrieval/sparse.py",
    "app/retrieval/filters.py",
    "app/ingestion/qdrant_store.py",
    "app/reranker/config.py",
    "app/reranker/cross_encoder.py",
    "app/evidence/section_aware.py",
    "app/evidence/support_units.py",
    "app/evidence/support_relevance.py",
    "app/llm/structured_output.py",
    "app/llm/prompt.py",
    "app/evaluation/critical_values.py",
    "app/llm/citation_location.py",
    "app/llm/openai_client.py",
    "scripts/benchmarks/run_ragbench_techqa_canonical.py",
    "scripts/experiments/run_techqa_reranker_holdout_oneshot_v1.py",
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def write_once_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise IOError(f"short write: {written}/{len(payload)}")
    finally:
        os.close(descriptor)


def source_integrity(starting_head: str) -> dict[str, Any]:
    root_cause = read_json(ROOT_CAUSE)
    recon_verdict = read_json(RECON_VERDICT)
    v1_hash = sha256_file(V1)
    v1_sidecar = V1_SIDECAR.read_text(encoding="utf-8").strip().split()[0]
    if "CORPUS_SCOPE_MISMATCH" not in root_cause.get("root_cause", ""):
        raise RuntimeError("ROOT_CAUSE_SOURCE_MISMATCH")
    if recon_verdict.get("primary_verdict") != "AMENDMENT_V1_PROVENANCE_INCONCLUSIVE":
        raise RuntimeError("PROVENANCE_SOURCE_MISMATCH")
    if v1_hash != v1_sidecar:
        raise RuntimeError("V1_SIDECAR_MISMATCH")
    return {
        "starting_head": starting_head,
        "dataset_revision": DATASET_REVISION,
        "debug50_hash": DEBUG_HASH,
        "holdout50_hash": HOLDOUT_HASH,
        "root_cause": {
            "path": rel(ROOT_CAUSE),
            "sha256": sha256_file(ROOT_CAUSE),
            "report_path": rel(ROOT_CAUSE_REPORT),
            "report_sha256": sha256_file(ROOT_CAUSE_REPORT),
            "root_cause": root_cause["root_cause"],
            "arm_symmetric": root_cause["arm_symmetric"],
            "outcome_independent": root_cause["outcome_independent_invalidity"],
        },
        "measurement_validity_report": {
            "path": rel(AUDIT_REPORT),
            "sha256": sha256_file(AUDIT_REPORT),
        },
        "provenance_reconciliation": {
            "verdict_path": rel(RECON_VERDICT),
            "verdict_sha256": sha256_file(RECON_VERDICT),
            "report_path": rel(RECON_REPORT),
            "report_sha256": sha256_file(RECON_REPORT),
            "verdict": recon_verdict["primary_verdict"],
        },
        "amendment_v1": {
            "path": rel(V1),
            "raw_sha256": v1_hash,
            "sidecar_path": rel(V1_SIDECAR),
            "sidecar_sha256": v1_sidecar,
            "historical_reported_sha256": EXPECTED_V1_REPORTED,
            "authorization_status": "INVALID_FOR_AUTHORIZATION",
        },
        "holdout_content_accessed_this_task": False,
        "arm_maps_opened_this_task": 0,
        "provider_calls_this_task": {
            "retrieval": 0,
            "embedding": 0,
            "bge": 0,
            "luna": 0,
            "terra": 0,
        },
    }


def code_identities() -> dict[str, str]:
    return {path: sha256_file(ROOT / path) for path in CODE_FILES}


def build_amendment(source: dict[str, Any], starting_head: str) -> dict[str, Any]:
    generation = read_json(DEBUG_GENERATION_CONFIG)
    generation_hash = sha256_file(DEBUG_GENERATION_CONFIG)
    prompt_hash = generation["prompt_hash"]
    return {
        "amendment": "TECHQA_CORRECTED_HOLDOUT_AMENDMENT_V2",
        "amendment_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "sha256",
        "hash_convention": "raw_file_bytes",
        "sidecar_path": rel(SIDECAR),
        "supersedes": rel(V1),
        "supersedes_hash_observed": source["amendment_v1"]["raw_sha256"],
        "historical_reported_v1_hash": EXPECTED_V1_REPORTED,
        "provenance_reconciliation_verdict": "AMENDMENT_V1_PROVENANCE_INCONCLUSIVE",
        "reason_for_v2": [
            "v1 provenance could not reconcile the historical reported hash",
            "v1 semantic experiment freeze was incomplete",
            "v1 writer rewrote the same path with dynamic created_at on reruns",
            "v2 is a new write-once authorization artifact and does not repair v1",
        ],
        "semantic_changes_from_v1": [
            "explicitly freeze previously implicit chunking, retrieval, generator, validator, retry, and blind-review constraints",
            "no RAG behavior or benchmark variable is changed by this amendment",
        ],
        "authorization": {
            "corrected_execution_authorized": True,
            "authorization_status": "CORRECTED_HOLDOUT_EXECUTION_AUTHORIZED_BY_AMENDMENT_V2",
            "execution_terminology": "CORRECTED_HOLDOUT_EXECUTION",
            "implementation_check": True,
            "architecture_diagnostic": True,
            "promotion_authority": False,
            "production_change_authorized": False,
        },
        "source": {
            "starting_head": starting_head,
            "dataset_name": "RAGBench TechQA",
            "dataset_revision": DATASET_REVISION,
            "debug50_hash": DEBUG_HASH,
            "holdout50_hash": HOLDOUT_HASH,
            "holdout_size": 50,
            "debug_holdout_overlap": 0,
            "original_holdout_accessed": True,
            "original_run_status": "HOLDOUT_RUN_INVALID_CORPUS_SCOPE",
            "original_semantic_review_started": False,
            "original_semantic_unblind": False,
            "original_arm_map_opened": False,
            "old_wrong_corpus_fingerprint": OLD_CORPUS_HASH,
            "canonical_config_fingerprint": CONFIG_HASH,
        },
        "correction_scope": {
            "only_authorized_benchmark_correction": "CORPUS_SCOPE",
            "original_scope": "DEBUG50-only indexed corpus",
            "corrected_scope": "deterministic proper TechQA source-document corpus required by the pinned test-split benchmark revision",
            "construction_source": "scripts/benchmarks/run_ragbench_techqa_canonical.py::load_rows + unique_candidates + build_documents",
            "construction_rule": "all pinned test-split source documents, content-hash deduplicated; neither DEBUG-only nor HOLDOUT-only selection",
            "gold_usage": [
                "pre-execution L0 source coverage verification",
                "pre-execution L1 annotation mappability verification",
                "post-retrieval evidence scoring",
            ],
            "gold_must_not_influence": [
                "retrieval",
                "ranking",
                "Top5 selection",
                "SectionAware",
                "budget allocation",
                "support units",
                "generation",
            ],
        },
        "corpus_construction": {
            "algorithm_source": "scripts/benchmarks/run_ragbench_techqa_canonical.py::build_documents",
            "document_identity": "source_id=ragbench_techqa_doc_<sha256(text)[:16]>, document_version=sha256(text)",
            "tenant": "ragbench-techqa",
            "source_type": "ragbench_techqa",
            "chunking": {
                "identity": "legacy_word_sentence_heading_page_v1",
                "mode": "baseline",
                "target_tokens": 500,
                "overlap_tokens": 50,
                "hard_max_tokens": None,
                "sentence_end_lookahead_chars": 300,
                "heading_page_grouping": "markdown heading sections; PDF page units in shared legacy chunker",
                "normalization": "source text retained; deterministic source/document hashes",
                "code_hashes": {
                    "app/ingestion/chunking_config.py": code_identities()["app/ingestion/chunking_config.py"],
                    "app/ingestion/chunker.py": code_identities()["app/ingestion/chunker.py"],
                    "app/ingestion/markdown_chunker.py": code_identities()["app/ingestion/markdown_chunker.py"],
                },
            },
        },
        "embedding": {
            "model_family": "Qwen/Qwen3-Embedding-4B",
            "ollama_model": "qwen3-embedding:4b",
            "revision": "latest",
            "backend": "ollama",
            "dimension": 1024,
            "output_dimension": 1024,
            "query_instruction": "Instruct: Given a search query, retrieve relevant passages that answer the query\nQuery: ",
            "document_instruction": "",
            "settings_profile": "Settings.benchmark_reference()",
            "embedding_concurrency": 4,
            "code_hash": code_identities()["app/llm/embedding_models.py"],
        },
        "dense_retrieval": {
            "implementation": "app.retrieval.search.search + app.retrieval.hybrid_search.hybrid_search",
            "query_embedding": "frozen embedding config above",
            "top_k": 20,
            "prefetch_limit_per_branch": 20,
            "named_vector": "dense",
            "distance": "COSINE",
            "acl": "server-owned tenant-scoped ACL before reranking",
            "code_hashes": {
                "app/retrieval/search.py": code_identities()["app/retrieval/search.py"],
                "app/retrieval/hybrid_search.py": code_identities()["app/retrieval/hybrid_search.py"],
                "app/retrieval/filters.py": code_identities()["app/retrieval/filters.py"],
                "app/ingestion/qdrant_store.py": code_identities()["app/ingestion/qdrant_store.py"],
            },
        },
        "bm25": {
            "implementation": "Qdrant/bm25 via app.retrieval.sparse.SparseEncoder",
            "named_vector": "sparse",
            "idf": "Qdrant server-side IDF modifier",
            "query_tokenization": "provider implementation unchanged",
            "top_k": 20,
            "code_hash": code_identities()["app/retrieval/sparse.py"],
        },
        "rrf": {
            "implementation": "Qdrant FusionQuery(Fusion.RRF)",
            "dense_contribution": "prefetch limit 20",
            "bm25_contribution": "prefetch limit 20",
            "candidate_k": 20,
            "tie_break": "stable order by (-score, point_id)",
            "code_hashes": {
                "app/retrieval/hybrid_search.py": code_identities()["app/retrieval/hybrid_search.py"],
                "app/retrieval/search.py": code_identities()["app/retrieval/search.py"],
            },
        },
        "arms": {
            "ON": {
                "pipeline": "Dense + BM25 + RRF shared Top20 -> BAAI/bge-reranker-v2-m3 -> Top5 -> SectionAware -> support units -> Luna -> frozen validators",
                "ranking_source": "BGE",
                "reranker_enabled": True,
            },
            "OFF": {
                "pipeline": "Dense + BM25 + RRF shared Top20 -> direct RRF Top5 -> SectionAware -> support units -> Luna -> frozen validators",
                "ranking_source": "RRF",
                "reranker_enabled": False,
            },
            "only_intended_difference": ["ranking_source", "reranker_enabled"],
            "shared_candidate_set": True,
        },
        "bge": {
            "model": "BAAI/bge-reranker-v2-m3",
            "backend": "sentence-transformers",
            "candidate_k": 20,
            "top_n": 5,
            "max_concurrency": 1,
            "trust_remote_code": False,
            "score_extraction": "CrossEncoder.predict pairs [question, candidate.text], sort descending score",
            "device": "runner-supplied device override only; no new override authorized",
            "code_hashes": {
                "app/reranker/config.py": code_identities()["app/reranker/config.py"],
                "app/reranker/cross_encoder.py": code_identities()["app/reranker/cross_encoder.py"],
            },
        },
        "top_n": 5,
        "section_aware": {
            "implementation": "SectionAwareEvidenceBuilder",
            "legacy_budget": 2400,
            "budget_semantics": "existing whitespace-like internal count",
            "ordering": "anchor-first, deterministic source/section ordering, fair anchor reservation, opportunistic same-boundary expansion",
            "truncation": "existing graceful budget behavior; no tokenizer migration",
            "support_expansion": "same authorized source/document-version/tenant boundary",
            "code_hash": code_identities()["app/evidence/section_aware.py"],
        },
        "support_units": {
            "implementation": "app.evidence.support_units.build_support_units",
            "id_format": "deterministic request-scoped E<n>.S<n>",
            "metadata": "source/document-version/section/tenant/contributing chunks",
            "serialization": "app.evidence.support_units.serialize_support_units",
            "code_hash": code_identities()["app/evidence/support_units.py"],
        },
        "generator": {
            "model": "gpt-5.6-luna",
            "reasoning": "none",
            "stream": False,
            "temperature": 0.0,
            "max_output_tokens": 1024,
            "prompt_hash": prompt_hash,
            "prompt_source": "app.llm.structured_output.ANSWERABILITY_OUTPUT_INSTRUCTIONS",
            "schema": "support_unit_answerability_schema",
            "schema_source": "app.llm.structured_output.support_unit_answerability_schema",
            "schema_source_sha256": code_identities()["app/llm/structured_output.py"],
            "debug_generation_config_path": rel(DEBUG_GENERATION_CONFIG),
            "debug_generation_config_sha256": generation_hash,
            "provider_adapter": "OpenAI Responses native strict json_schema",
        },
        "downstream_contract_and_validators": {
            "output_contract": "existing V4 support-unit answerability contract; no redesign or fallback",
            "support_relevance": "existing deterministic content-token coverage threshold 0.60",
            "critical_value_validator": "existing claim-local critical-value audit unchanged",
            "support_id_validation": "identity, request scope, authorization, model visibility, source/version",
            "citation_resolution": "existing application citation resolver",
            "forced_abstain": "existing behavior unchanged",
            "security_policy": "strict ACL and support-ID validation; no weakening",
            "code_hashes": {
                "app/llm/structured_output.py": code_identities()["app/llm/structured_output.py"],
                "app/evidence/support_relevance.py": code_identities()["app/evidence/support_relevance.py"],
                "app/evaluation/critical_values.py": code_identities()["app/evaluation/critical_values.py"],
                "app/llm/citation_location.py": code_identities()["app/llm/citation_location.py"],
            },
        },
        "retry_policy": {
            "openai_sdk_max_retries": 0,
            "retryable_classes": "existing OpenAI adapter classification only",
            "runner_retry": "only genuine transport/timeout/rate-limit failures; explicit existing retry path; no semantic retry sampling",
            "backoff_seconds": 2.0,
            "logical_vs_physical": "record separately; successful logical output is never regenerated",
            "code_hashes": {
                "app/llm/openai_client.py": code_identities()["app/llm/openai_client.py"],
                "scripts/experiments/run_techqa_reranker_holdout_oneshot_v1.py": code_identities()["scripts/experiments/run_techqa_reranker_holdout_oneshot_v1.py"],
            },
        },
        "gates": {
            "l0": "all 41 currently usable annotated HOLDOUT rows have gold source present before query embedding/retrieval",
            "l0_required": "41/41",
            "l1": "all same 41 rows have faithfully mappable native annotation before retrieval",
            "l1_required": "41/41",
            "post_retrieval_integrity": "corrected collection sources and scorer mapping coherent; not a quality threshold",
            "security": "unknown, cross-query, hidden, unauthorized accepted = 0; citation failures tracked",
        },
        "metrics": {
            "evidence": ["RRF Top20 ANY/ALL/mean recall", "BGE Top5 ANY/ALL/mean recall", "RRF Top5 ANY/ALL/mean recall", "SectionAware ON/OFF ANY/ALL/mean recall", "budget exhausted"],
            "operational": ["provider success", "valid JSON/schema/contract", "ANSWER/ABSTAIN", "visible", "self/forced abstain", "support failures", "critical rejects", "citation failures"],
            "latency": ["query embedding", "hybrid retrieval", "BGE", "SectionAware", "Luna", "validation", "p50/p95/max", "MEASURED_E2E or SUMMED_STAGE_ESTIMATE"],
            "cost": ["ON/OFF Luna usage and cost", "preflight", "total provider cost", "Terra=0", "BGE local compute/latency"],
        },
        "provider_budget": {
            "holdout_queries": 50,
            "official_luna_on": 50,
            "official_luna_off": 50,
            "official_luna_total": 100,
            "technical_preflight_max": 2,
            "terra": 0,
        },
        "paired_execution": {
            "retrieval_per_query": 1,
            "shared_top20": True,
            "arm_order": "deterministic randomized approximately balanced before first official call",
            "outputs_persisted_before_review_pack": True,
        },
        "blind_review": {
            "new_mapping_required": True,
            "reuse_invalid_v1_map": False,
            "candidate_identities_hidden": True,
            "semantic_labels_during_execution": False,
            "rubric": "exact existing DEBUG blind rubric; CORRECT/PARTIAL/INCORRECT/UNAVAILABLE; A_BETTER/B_BETTER/TIE/BOTH_BAD",
            "sequence": "corrected outputs frozen -> new blind pack -> STOP -> separate scoring/freeze/unblind task",
        },
        "catastrophic_regression": [
            "deterministic security leakage",
            "repeatable unauthorized/hidden support acceptance",
            "severe repeatable wrong-value/entity failure unique to OFF",
            "one clearly defined query class materially collapsing uniquely under OFF",
        ],
        "no_tuning": {
            "only_change": "corpus scope correction",
            "forbidden_changes": ["chunk size", "overlap", "embedding", "dense/BM25/RRF weighting", "candidate_k", "top_n", "BGE config", "budget", "SectionAware", "support units", "prompt", "schema", "Luna", "validators", "security", "token accounting semantics"],
            "no_production_change": True,
        },
    }


def validate_completeness(value: dict[str, Any]) -> list[str]:
    required = [
        "source", "correction_scope", "corpus_construction", "embedding", "dense_retrieval",
        "bm25", "rrf", "arms", "bge", "top_n", "section_aware", "support_units", "generator",
        "downstream_contract_and_validators", "retry_policy", "gates", "metrics", "provider_budget",
        "paired_execution", "blind_review", "catastrophic_regression", "no_tuning", "authorization",
    ]
    return [key for key in required if key not in value]


def writer_self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="techqa-amendment-v2-") as temporary:
        path = Path(temporary) / "v2.json"
        payload = b"{\"test\":true}\n"
        write_once_bytes(path, payload)
        try:
            write_once_bytes(path, b"mutate")
        except FileExistsError:
            return {"write_once": True, "second_create_error": "AMENDMENT_V2_ALREADY_EXISTS"}
        raise RuntimeError("WRITE_ONCE_SELF_TEST_FAILED")


def main() -> None:
    if TARGET.exists() or SIDECAR.exists():
        raise RuntimeError("AMENDMENT_V2_ALREADY_EXISTS")
    starting_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = source_integrity(starting_head)
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "00-source-integrity/source-integrity.json", source)
    code_hashes = code_identities()
    amendment = build_amendment(source, starting_head)
    missing = validate_completeness(amendment)
    if missing:
        raise RuntimeError(f"AMENDMENT_V2_INCOMPLETE:{','.join(missing)}")
    raw = (json.dumps(amendment, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_once_bytes(TARGET, raw)
    raw_hash = sha256_file(TARGET)
    write_once_bytes(SIDECAR, (raw_hash + "\n").encode("ascii"))
    sidecar_hash = SIDECAR.read_text(encoding="utf-8").strip()
    reread_hash = sha256_file(TARGET)
    if raw_hash != sidecar_hash or raw_hash != reread_hash:
        raise RuntimeError("V2_HASH_VERIFICATION_FAILED")
    write_json(
        OUT / "02-hash-verification/v2-hash-verification.json",
        {
            "file_exists": True,
            "sidecar_exists": True,
            "path": rel(TARGET),
            "sidecar_path": rel(SIDECAR),
            "file_size": TARGET.stat().st_size,
            "raw_sha256": raw_hash,
            "sidecar_sha256": sidecar_hash,
            "match": True,
            "end_of_creation_recheck": reread_hash == raw_hash,
            "authoritative_convention": "RAW_FILE_BYTES_SHA256",
        },
    )
    write_json(OUT / "03-writer-tests/writer-tests.json", {**writer_self_test(), "target_preexisted": False, "v1_untouched_observed_hash": source["amendment_v1"]["raw_sha256"]})
    write_json(
        OUT / "04-report/status.json",
        {
            "status": "CORRECTED_HOLDOUT_EXECUTION_AUTHORIZED_BY_AMENDMENT_V2",
            "authorized": True,
            "executed": False,
            "holdout_content_accessed_this_task": False,
            "arm_maps_opened": 0,
            "provider_calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0},
            "semantic_review": False,
            "code_hashes": code_hashes,
        },
    )
    report = f"""# TECHQA Corrected HOLDOUT Amendment V2

Status: `CORRECTED_HOLDOUT_EXECUTION_AUTHORIZED_BY_AMENDMENT_V2`

V2 is a new immutable authorization artifact. Amendment v1 remains
`INVALID_FOR_AUTHORIZATION` and was not modified. The original HOLDOUT run
remains invalid due to `HOLDOUT_RUN_INVALID_CORPUS_SCOPE`.

Authoritative v2 SHA256 (exact raw file bytes): `{raw_hash}`

The v2 writer created the JSON once with `O_EXCL`, closed it, hashed the exact
bytes, wrote the sidecar once, and verified the pair again at the end. The JSON
contains no self-referential final hash. Recreating the same target fails with
`AMENDMENT_V2_ALREADY_EXISTS`.

The only authorized benchmark correction is corpus scope: use the deterministic
proper pinned TechQA source-document corpus, with the existing chunking,
embedding, retrieval, reranking, evidence, generator, validator, retry, and
blind-review designs explicitly frozen in the JSON.

No HOLDOUT content was accessed by this task. No retrieval, embedding, BGE,
Luna, or Terra calls were made. Corrected HOLDOUT execution was not run.
"""
    (OUT / "04-report/report.md").write_text(report, encoding="utf-8")
    print(raw_hash)


if __name__ == "__main__":
    main()
