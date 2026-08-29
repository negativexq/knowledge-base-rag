"""Run the pinned RAGBench eManual Basic-50 benchmark."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient

from app.evidence.section_aware import SectionAwareEvidenceBuilder, serialize_section_aware_context
from app.llm.ollama_client import OllamaClient
from app.llm.openai_client import OpenAIGeneratorClient, OpenAIProviderError, canonical_hash
from app.llm.prompt import build_messages, load_system_prompt
from app.llm.structured_output import (
    EVIDENCE_BACKED_OUTPUT_INSTRUCTIONS,
    EVIDENCE_BACKED_OUTPUT_SCHEMA,
    parse_evidence_backed_answer,
    render_evidence_backed_answer,
    validate_evidence_backed_answer,
)
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.filters import build_acl_filter, filter_authorized_candidates
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from scripts.ragbench_emanual_common import (
    CONTRACT_VERSION,
    EMBED_DIM,
    EMBED_MODEL,
    GENERATOR_MODEL,
    OUT,
    PROMPT_VERSION,
    RERANKER_MODEL,
    SAMPLE_SIZE,
    TENANT,
    append_jsonl,
    deserialize_result,
    load_rows,
    read_json,
    read_jsonl,
    relevant_doc_indices,
    relevant_keys,
    row_identifier,
    score_benchmark,
    serialize_result,
    truth_presence,
    write_json,
)
from scripts.ragbench_emanual_common import (
    canonical_hash as local_hash,
)
from scripts.setup_ragbench_emanual import dataset_path

RETRIEVAL_PATH = OUT / "retrieval-results.jsonl"
GENERATION_PATH = OUT / "generation-results.jsonl"
SCORED_PATH = OUT / "scored-results.jsonl"
PREFLIGHT_PATH = OUT / "preflight.json"


def prompt_template_hash() -> str:
    return canonical_hash(
        {
            "system": load_system_prompt(PROMPT_VERSION),
            "suffix": EVIDENCE_BACKED_OUTPUT_INSTRUCTIONS,
        }
    )


def config() -> dict[str, Any]:
    return read_json(OUT / "config.json")


def assert_config() -> dict[str, Any]:
    value = config()
    expected = value.get("config_fingerprint")
    actual = local_hash({key: val for key, val in value.items() if key != "config_fingerprint"})
    if (
        expected != actual
        or (OUT / "config.sha256").read_text(encoding="utf-8").strip() != expected
    ):
        raise RuntimeError("RAGBENCH_CONFIG_DRIFT")
    if value["generator"]["model"] != GENERATOR_MODEL or value["retrieval"]["candidate_k"] != 20:
        raise RuntimeError("RAGBENCH_CONFIG_UNEXPECTED")
    if value["prompt"].get("template_hash") != prompt_template_hash():
        raise RuntimeError("RAGBENCH_PROMPT_DRIFT")
    return value


def rows_by_id() -> dict[str, dict[str, Any]]:
    return {row_identifier(row): row for row in load_rows(dataset_path())}


def sample_rows() -> list[dict[str, Any]]:
    sample = read_json(OUT / "sample.json")
    if sample.get("row_count") != 132 or len(sample.get("selected_query_ids", [])) != SAMPLE_SIZE:
        raise RuntimeError("RAGBENCH_SAMPLE_INVALID")
    if (OUT / "sample.sha256").read_text(encoding="utf-8").strip() != local_hash(sample):
        raise RuntimeError("RAGBENCH_SAMPLE_HASH_MISMATCH")
    rows = rows_by_id()
    try:
        return [rows[query_id] for query_id in sample["selected_query_ids"]]
    except KeyError as exc:
        raise RuntimeError(f"RAGBENCH_SAMPLE_ID_MISSING:{exc}") from exc


def retrieval_context() -> RetrievalContext:
    return RetrievalContext(tenant_id=TENANT, is_system=False)


def retrieval_record_map() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(RETRIEVAL_PATH)}


def generation_record_map() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(GENERATION_PATH)}


def scored_record_map() -> dict[str, dict[str, Any]]:
    return {row["query_id"]: row for row in read_jsonl(SCORED_PATH)}


def block_results(record: dict[str, Any]) -> list[SearchResult]:
    return [
        deserialize_result(item, score_name="score")
        for item in record.get("section_aware_blocks", [])
    ]


async def retrieve_one(
    row: dict[str, Any],
    qdrant: QdrantClient,
    ollama: OllamaClient,
    sparse: SparseEncoder,
    reranker: CrossEncoderReranker,
    builder: SectionAwareEvidenceBuilder,
    collection: str,
    embedding_model: str,
) -> dict[str, Any]:
    query = str(row["question"])
    query_id = row_identifier(row)
    context = retrieval_context()
    started = time.perf_counter()
    embed_started = time.perf_counter()
    dense = await ollama.embed(
        query,
        model=embedding_model,
        prefix=(
            "Instruct: Given a search query, retrieve relevant passages that answer the query\n"
            "Query: "
        ),
        dimensions=EMBED_DIM,
    )
    embed_ms = (time.perf_counter() - embed_started) * 1000
    sparse_started = time.perf_counter()
    sparse_vector = sparse.embed_query(query)
    sparse_ms = (time.perf_counter() - sparse_started) * 1000
    acl_filter = build_acl_filter(context)
    retrieve_started = time.perf_counter()
    raw = hybrid_search(
        qdrant, collection, dense, sparse_vector, top_k=20, prefetch_limit=20, filters=acl_filter
    )
    authorized = filter_authorized_candidates(raw, context)
    retrieval_ms = (time.perf_counter() - retrieve_started) * 1000
    rerank_started = time.perf_counter()
    reranked = await reranker.async_rerank(query, authorized, top_n=20)
    rerank_ms = (time.perf_counter() - rerank_started) * 1000
    selected = reranked[:5]
    assembly_started = time.perf_counter()
    built = await builder.build(selected, context)
    assembly_ms = (time.perf_counter() - assembly_started) * 1000
    return {
        "schema_version": "ragbench-emanual-retrieval-v1",
        "state": "RETRIEVAL_COMPLETE",
        "query_id": query_id,
        "dataset_row_id": row["id"],
        "dataset_row_index": row["_row_index"],
        "tenant_id": TENANT,
        "collection": collection,
        "query_hash": hashlib.sha256(query.encode()).hexdigest(),
        "authorized_top20": [
            serialize_result(item, rank=index, score_name="fused_score")
            for index, item in enumerate(authorized, 1)
        ],
        "reranked_top20": [
            serialize_result(item, rank=index, score_name="bge_score")
            for index, item in enumerate(reranked, 1)
        ],
        "selected_top5": [
            serialize_result(item, rank=index, score_name="bge_score")
            for index, item in enumerate(selected, 1)
        ],
        "section_aware_blocks": [
            serialize_result(item, rank=index, score_name="score")
            for index, item in enumerate(built.blocks, 1)
        ],
        "section_aware_context": serialize_section_aware_context(built.blocks),
        "section_aware_error": None,
        "stage_latency_ms": {
            "embedding": round(embed_ms, 3),
            "sparse": round(sparse_ms, 3),
            "hybrid_retrieval": round(retrieval_ms, 3),
            "reranker": round(rerank_ms, 3),
            "section_aware": round(assembly_ms, 3),
            "total_retrieval": round((time.perf_counter() - started) * 1000, 3),
        },
        "counts": {
            "authorized_top20": len(authorized),
            "reranked_top20": len(reranked),
            "selected_top5": len(selected),
            "section_aware_blocks": len(built.blocks),
            "unique_sources_top20": len({item.payload.get("source_id") for item in authorized}),
            "unique_sources_top5": len({item.payload.get("source_id") for item in selected}),
        },
        "truth": {
            "relevant_sentence_keys": relevant_keys(row),
            "relevant_doc_indices": sorted(relevant_doc_indices(row)),
            "top20": truth_presence(row, authorized),
            "top5": truth_presence(row, selected),
            "section_aware": truth_presence(row, built.blocks),
        },
    }


def messages_for(row: dict[str, Any], blocks: list[SearchResult]) -> list[dict[str, Any]]:
    return build_messages(
        row["question"],
        blocks,
        version=PROMPT_VERSION,
        context_serializer=serialize_section_aware_context,
        system_prompt_suffix=EVIDENCE_BACKED_OUTPUT_INSTRUCTIONS,
    )


def safe_observation(observation: dict[str, Any] | None) -> dict[str, Any]:
    if not observation:
        return {}
    value = dict(observation)
    # Provider observations are deliberately sanitized at this boundary too:
    # no request headers/environment values are ever written to benchmark artifacts.
    value.pop("authorization", None)
    value.pop("headers", None)
    return value


async def generate_one(
    client: OpenAIGeneratorClient, row: dict[str, Any], retrieval: dict[str, Any], config_fp: str
) -> dict[str, Any]:
    query_id = row_identifier(row)
    blocks = block_results(retrieval)
    messages = messages_for(row, blocks)
    prompt_hash = canonical_hash(messages)
    started = time.perf_counter()
    try:
        raw = await client.chat_json(
            messages,
            model=GENERATOR_MODEL,
            schema=EVIDENCE_BACKED_OUTPUT_SCHEMA,
            reasoning="none",
            max_output_tokens=1024,
            temperature=None,
            seed=42,
        )
        provider_observation = safe_observation(client.last_call_observation)
        raw_record = {
            "schema_version": "ragbench-emanual-generation-raw-v1",
            "state": "GENERATION_RAW_COMPLETE",
            "query_id": query_id,
            "dataset_row_id": row["id"],
            "dataset_row_index": row["_row_index"],
            "config_fingerprint": config_fp,
            "prompt_content_hash": prompt_hash,
            "output_contract": CONTRACT_VERSION,
            "provider": "openai",
            "model": GENERATOR_MODEL,
            "reasoning": "none",
            "temperature_requested": 0.0,
            "temperature_sent": None,
            "max_output_tokens": 1024,
            "raw_output": raw,
            "provider_observation": provider_observation,
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "first_attempt_status": "COMPLETED",
            "attempt_count": 1,
        }
        return raw_record
    except OpenAIProviderError as exc:
        return {
            "schema_version": "ragbench-emanual-generation-raw-v1",
            "state": "FAILED_PROVIDER",
            "query_id": query_id,
            "dataset_row_id": row["id"],
            "dataset_row_index": row["_row_index"],
            "config_fingerprint": config_fp,
            "prompt_content_hash": prompt_hash,
            "provider": "openai",
            "model": GENERATOR_MODEL,
            "reasoning": "none",
            "raw_output": None,
            "provider_error_code": exc.code,
            "provider_observation": safe_observation(exc.observation),
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "first_attempt_status": exc.code,
            "attempt_count": 1,
        }


def score_one(
    row: dict[str, Any], retrieval: dict[str, Any], raw_record: dict[str, Any], config_fp: str
) -> dict[str, Any]:
    query_id = row_identifier(row)
    if raw_record.get("state") != "GENERATION_RAW_COMPLETE":
        return {
            "schema_version": "ragbench-emanual-scored-v1",
            "state": "FAILED_PROVIDER",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "provider_status": "FAILED",
            "provider_error_code": raw_record.get("provider_error_code"),
        }
    blocks = block_results(retrieval)
    try:
        parsed = parse_evidence_backed_answer(raw_record["raw_output"])
        validation = validate_evidence_backed_answer(parsed, blocks)
        visible = render_evidence_backed_answer(
            validation.valid_parts, abstain=validation.application_abstain
        )
        benchmark = score_benchmark(row, visible, validation)
        return {
            "schema_version": "ragbench-emanual-scored-v1",
            "state": "SCORED_COMPLETE",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "provider_status": "COMPLETED",
            "raw_output": raw_record["raw_output"],
            "parsed_output": {
                "answer_parts": [
                    {
                        "text": part.text,
                        "evidence": [
                            {"evidence_id": item.evidence_id, "quote": item.quote}
                            for item in part.evidence
                        ],
                    }
                    for part in validation.parsed.answer_parts
                ]
                if validation.parsed
                else None,
                "abstain": validation.parsed.abstain if validation.parsed else None,
            },
            "visible_output": visible,
            "validator_pass": validation.top_level_valid and not validation.failure_codes,
            "validator_failure_codes": validation.failure_codes,
            "validated_parts": [
                {
                    "text": part.text,
                    "evidence": [
                        {"evidence_id": item.evidence_id, "quote": item.quote}
                        for item in part.evidence
                    ],
                }
                for part in validation.valid_parts
            ],
            "rejected_parts": validation.rejected_parts,
            "model_abstention": validation.model_abstain,
            "application_forced_abstention": validation.application_abstain,
            "benchmark": benchmark,
            "provider_observation": raw_record.get("provider_observation", {}),
            "generation_latency_ms": raw_record.get("generation_latency_ms"),
        }
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "ragbench-emanual-scored-v1",
            "state": "FAILED_PARSE",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "provider_status": "COMPLETED",
            "raw_output": raw_record["raw_output"],
            "parse_error": str(exc)[:300],
            "generation_latency_ms": raw_record.get("generation_latency_ms"),
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cfg = assert_config()
    rows = sample_rows()
    query_ids = [row_identifier(row) for row in rows]
    collection = cfg["collection"]
    qdrant = QdrantClient(url=args.qdrant_url)
    ollama = OllamaClient(base_url=args.ollama_url, think=False, num_ctx=4096)
    sparse = SparseEncoder()
    reranker = CrossEncoderReranker(RERANKER_MODEL, max_concurrency=1, device=args.reranker_device)
    builder = SectionAwareEvidenceBuilder(
        qdrant, collection, token_budget=cfg["evidence"]["token_budget"]
    )
    client = OpenAIGeneratorClient()
    retrievals = retrieval_record_map()
    generations = generation_record_map()
    scored = scored_record_map()
    try:
        # Retrieval is checkpointed independently and is never repeated for a
        # query that already has an identity-matching completed record.
        for index, row in enumerate(rows, 1):
            query_id = row_identifier(row)
            if query_id not in retrievals:
                record = await retrieve_one(
                    row, qdrant, ollama, sparse, reranker, builder, collection, EMBED_MODEL
                )
                record["config_fingerprint"] = cfg["config_fingerprint"]
                retrievals[query_id] = record
                append_jsonl(RETRIEVAL_PATH, record)
            print(f"retrieval {index}/{len(rows)}", flush=True)

        preflight_ids = query_ids[:3]
        preflight: list[dict[str, Any]] = []
        for query_id in preflight_ids:
            raw = await generate_one(
                client,
                next(row for row in rows if row_identifier(row) == query_id),
                retrievals[query_id],
                cfg["config_fingerprint"],
            )
            item = {
                "query_id": query_id,
                "provider_status": raw.get("first_attempt_status"),
                "raw_present": bool(raw.get("raw_output")),
            }
            if raw.get("raw_output"):
                try:
                    parsed = parse_evidence_backed_answer(raw["raw_output"])
                    validation = validate_evidence_backed_answer(
                        parsed, block_results(retrievals[query_id])
                    )
                    item.update(
                        {
                            "schema_valid": True,
                            "validator_compatible": validation.top_level_valid,
                            "validator_failure_codes": validation.failure_codes,
                        }
                    )
                except (ValueError, json.JSONDecodeError) as exc:
                    item.update({"schema_valid": False, "error": str(exc)[:200]})
            preflight.append(item)
        write_json(
            PREFLIGHT_PATH,
            {
                "schema_version": "ragbench-emanual-preflight-v1",
                "official_excluded": True,
                "query_ids": preflight_ids,
                "results": preflight,
            },
        )
        if not all(
            item.get("provider_status") == "COMPLETED"
            and item.get("schema_valid")
            and item.get("validator_compatible")
            for item in preflight
        ):
            raise RuntimeError("RAGBENCH_PREFLIGHT_FAILED")

        for index, row in enumerate(rows, 1):
            query_id = row_identifier(row)
            if query_id not in generations:
                raw = await generate_one(
                    client, row, retrievals[query_id], cfg["config_fingerprint"]
                )
                generations[query_id] = raw
                append_jsonl(GENERATION_PATH, raw)
            if query_id not in scored:
                scored_row = score_one(
                    row, retrievals[query_id], generations[query_id], cfg["config_fingerprint"]
                )
                scored[query_id] = scored_row
                append_jsonl(SCORED_PATH, scored_row)
            print(f"official {index}/{len(rows)}", flush=True)
        return {
            "required": len(rows),
            "retrieval": len(retrievals),
            "generation": len(generations),
            "scored": len(scored),
            "preflight": preflight,
        }
    finally:
        await client.aclose()
        await ollama.aclose()
        qdrant.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--reranker-device")
    print(json.dumps(asyncio.run(run(parser.parse_args())), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
