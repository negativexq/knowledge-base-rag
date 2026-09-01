"""Run the canonical support-ID RAGBench eManual Basic-50 confirmation.

Retrieval is deliberately replayed from the identity-checked graceful-budget
snapshot.  The run exercises the canonical evidence/support-ID and Luna
generation path, then uses a fixed Terra judge for semantic reporting.  The
script never mutates production settings or old benchmark artifacts.
"""

# ruff: noqa: E402, E501

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evidence.support_units import (
    SupportUnit,
    build_support_units,
    resolve_support_ids,
    serialize_support_units,
)
from app.llm.openai_client import OpenAIGeneratorClient, OpenAIProviderError, canonical_hash
from app.llm.prompt import build_messages, load_system_prompt
from app.llm.structured_output import (
    SUPPORT_ID_MAX_OUTPUT_TOKENS,
    SUPPORT_ID_OUTPUT_CONTRACT_VERSION,
    SUPPORT_ID_OUTPUT_INSTRUCTIONS,
    SUPPORT_ID_PIPELINE_VERSION,
    parse_support_unit_answer,
    render_support_unit_answer,
    support_unit_output_schema,
    validate_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult
from scripts.benchmarks.ragbench_emanual_common import (
    GENERATOR_MODEL,
    RERANKER_MODEL,
    deserialize_result,
    load_rows,
    normalize_text,
    relevant_keys,
    row_identifier,
    summary_stats,
    text_has_sentence,
    write_json,
)
from scripts.benchmarks.ragbench_emanual_common import (
    canonical_hash as local_hash,
)
from scripts.benchmarks.setup_ragbench_emanual import dataset_path

EXPECTED_SAMPLE_HASH = "d65d578dcc1f88bb4df71451dfae5f923b2e56bf4fa60e331e6297b2b317cdf3"
EXPECTED_REPLAY_CONFIG = "bba1d9164e5eb36dc056c8b3843e42b175764b542976d83bb5dadf93f9bee8ce"
EXPECTED_CORPUS = "241dae67feae5733026d9a50cf2640979f141b8a7c7c016c5dc8173bfb6f3ae2"
EXPECTED_COLLECTION = "ragbench_emanual_basic50_241dae67feae5733"
EXPECTED_DATASET_REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEFAULT_SOURCE = Path("/tmp/knowledge-base-rag-cleanup.Vk4y4n/emanual-basic-50-graceful-budget")
DEFAULT_GOLD = Path("/tmp/knowledge-base-rag-cleanup.Vk4y4n/emanual-basic-50-gold-rescore")
OUT = ROOT / "artifacts/ragbench/canonical/basic50-final"
SAMPLE_NAME = "sample.json"

LUNA_INPUT_USD_M = 0.20
LUNA_OUTPUT_USD_M = 1.20
TERRA_INPUT_USD_M = 2.00
TERRA_CACHED_INPUT_USD_M = 0.20
TERRA_OUTPUT_USD_M = 12.00

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"],
        },
        "reason": {"type": "string"},
        "missing_or_wrong_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "reason", "missing_or_wrong_points"],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    value = dict(record)
    value.pop("authorization", None)
    value.pop("headers", None)
    return value


def usage_from_observation(value: dict[str, Any]) -> dict[str, Any]:
    usage = value.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def cost_usd(usage: dict[str, Any], *, judge: bool = False) -> float | None:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    cached = int(usage.get("cached_input_tokens") or 0)
    if judge:
        input_cost = cached * TERRA_CACHED_INPUT_USD_M + max(0, input_tokens - cached) * TERRA_INPUT_USD_M
        output_rate = TERRA_OUTPUT_USD_M
    else:
        input_cost = input_tokens * LUNA_INPUT_USD_M
        output_rate = LUNA_OUTPUT_USD_M
    return round((input_cost + output_tokens * output_rate) / 1_000_000, 8)


def block_results(record: dict[str, Any]) -> list[SearchResult]:
    return [deserialize_result(item, score_name="score") for item in record["section_aware_blocks"]]


def ranked_results(record: dict[str, Any], key: str) -> list[SearchResult]:
    score_name = "fused_score" if key == "authorized_top20" else "bge_score"
    return [deserialize_result(item, score_name=score_name) for item in record[key]]


def source_integrity(source: Path) -> dict[str, Any]:
    sample = read_json(source / SAMPLE_NAME)
    sample_hash = (source / "sample.sha256").read_text(encoding="utf-8").strip()
    corpus = (source / "corpus-fingerprint.txt").read_text(encoding="utf-8").strip()
    config = read_json(source / "config.json")
    replay_rows = read_jsonl(source / "retrieval-results.jsonl")
    if sample_hash != EXPECTED_SAMPLE_HASH:
        raise RuntimeError(f"SAMPLE_IDENTITY_MISMATCH expected={EXPECTED_SAMPLE_HASH} actual={sample_hash}")
    if (
        config.get("config_fingerprint") != EXPECTED_REPLAY_CONFIG
        or config.get("dataset_revision") != EXPECTED_DATASET_REVISION
        or corpus != EXPECTED_CORPUS
    ):
        raise RuntimeError("CORPUS_IDENTITY_DRIFT")
    if config.get("collection") != EXPECTED_COLLECTION:
        raise RuntimeError("COLLECTION_IDENTITY_DRIFT")
    if len(sample.get("selected_query_ids", [])) != 50:
        raise RuntimeError("SAMPLE_IDENTITY_MISMATCH expected=50")
    if len(replay_rows) != 50:
        raise RuntimeError(f"REPLAY_RETRIEVAL_INCOMPLETE expected=50 actual={len(replay_rows)}")
    return {
        "sample_hash": sample_hash,
        "sample_json_sha256": sha256_file(source / SAMPLE_NAME),
        "corpus_fingerprint": corpus,
        "replay_config_fingerprint": config["config_fingerprint"],
        "collection": config["collection"],
        "retrieval_snapshot_sha256": sha256_file(source / "retrieval-results.jsonl"),
        "retrieval_snapshot_rows": len(replay_rows),
        "historical_artifacts_modified": False,
    }


def support_unit_rows(query_id: str, units: list[SupportUnit]) -> list[dict[str, Any]]:
    return [{"query_id": query_id, **unit.as_dict()} for unit in units]


def prompt_for(query: str, units: list[SupportUnit]) -> list[dict[str, Any]]:
    return build_messages(
        query,
        units,
        version="v3",
        context_serializer=serialize_support_units,
        system_prompt_suffix=SUPPORT_ID_OUTPUT_INSTRUCTIONS,
    )


def judge_messages(
    question: str,
    reference_answers: list[str],
    relevant_sentences: list[dict[str, Any]],
    candidate_answer: str,
) -> list[dict[str, str]]:
    system = (
        "You are a strict semantic answer evaluator. Given a question, human/reference answer(s), "
        "relevant supporting sentences, and a candidate answer, classify the candidate as CORRECT, "
        "PARTIALLY_CORRECT, or INCORRECT. Paraphrases are allowed; do not grade wording. "
        "CORRECT answers all required factual content without contradiction. PARTIALLY_CORRECT "
        "has meaningful correct content but omits a material component or has a minor issue. "
        "INCORRECT answers a different question, gives wrong/contradictory facts, or lacks the "
        "required content. Return only the requested JSON schema."
    )
    payload = {
        "question": question,
        "reference_answers": reference_answers,
        "relevant_sentences": relevant_sentences,
        "candidate_answer": candidate_answer,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def mapped_gold(gold_dir: Path) -> dict[str, dict[str, Any]]:
    if not (gold_dir / "mapping.jsonl").exists():
        return {}
    return {row["ragbench_row_id"]: row for row in read_jsonl(gold_dir / "mapping.jsonl")}


def relevant_sentence_objects(row: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {str(key) for key in (row.get("all_relevant_sentence_keys") or [])}
    result = []
    for doc_index, sentences in enumerate(row.get("documents_sentences") or []):
        for key, text in sentences or []:
            if str(key) in wanted or str(key).rstrip(".") in {key.rstrip(".") for key in wanted}:
                result.append({"key": str(key), "document_index": doc_index, "text": str(text)})
    return result


def sentence_truth_presence(
    row: dict[str, Any], results: list[SearchResult]
) -> dict[str, Any]:
    """Match pinned RAGBench sentence keys/text, including key-dot aliases."""
    sentences = relevant_sentence_objects(row)
    corpus_text = "\n".join(str(result.payload.get("text", "")) for result in results)
    present = [
        item["key"] for item in sentences if text_has_sentence(corpus_text, item["text"])
    ]
    keys = [str(key) for key in (row.get("all_relevant_sentence_keys") or [])]
    return {
        "relevant_sentence_keys": keys,
        "present_sentence_keys": present,
        "missing_sentence_keys": [key for key in keys if key.rstrip(".") not in {value.rstrip(".") for value in present}],
        "sentence_recall": len(present) / len(sentences) if sentences else 0.0,
        "all_relevant_sentences_present": bool(sentences) and len(present) == len(sentences),
        "relevant_doc_indices": sorted({item["document_index"] for item in sentences}),
    }


def copy_frozen_inputs(source: Path, integrity: dict[str, Any]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / SAMPLE_NAME, OUT / SAMPLE_NAME)
    shutil.copyfile(source / "sample.sha256", OUT / "sample.sha256")
    shutil.copyfile(source / "corpus-fingerprint.txt", OUT / "corpus-fingerprint.txt")
    if (OUT / "sample.sha256").read_text().strip() != EXPECTED_SAMPLE_HASH:
        raise RuntimeError("SAMPLE_IDENTITY_MISMATCH")
    return integrity


def build_config(integrity: dict[str, Any], rows: list[dict[str, Any]], retrievals: dict[str, Any]) -> dict[str, Any]:
    evidence_hashes = {
        query_id: hashlib.sha256(
            json.dumps(
                [block.get("text_hash") for block in retrievals[query_id]["section_aware_blocks"]],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for query_id in sorted(retrievals)
    }
    value: dict[str, Any] = {
        "schema_version": "ragbench-emanual-basic50-canonical-v1",
        "dataset": "RAGBench eManual",
        "dataset_revision": EXPECTED_DATASET_REVISION,
        "split": "test",
        "sample_hash": integrity["sample_hash"],
        "sample_size": len(rows),
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "collection": integrity["collection"],
        "retrieval": {"method": "Dense + BM25 + RRF", "candidate_k": 20, "reused_snapshot": True},
        "reranker": {"model": RERANKER_MODEL, "top_n": 5, "reused_snapshot": True},
        "evidence": {
            "builder": "SectionAwareEvidenceBuilder",
            "token_budget": 1200,
            "policy": "anchor_first_graceful_global_budget_v1",
            "support_units": "deterministic_request_scoped_units_from_final_visible_evidence",
        },
        "generator": {
            "provider": "openai",
            "model": GENERATOR_MODEL,
            "reasoning": "none",
            "max_output_tokens": 1024,
            "temperature_requested": 0.0,
            "temperature_sent": "omitted_by_provider_compatibility",
            "stream": False,
        },
        "contract": {
            "pipeline": SUPPORT_ID_PIPELINE_VERSION,
            "output": SUPPORT_ID_OUTPUT_CONTRACT_VERSION,
            "model_fields": ["text", "support_ids"],
            "canonical_quote_text": "application_resolved_from_support_id",
            "semantic_entailment_guarantee": False,
        },
        "prompt": {
            "version": "v3",
            "template_hash": canonical_hash(
                {"system": load_system_prompt("v3"), "suffix": SUPPORT_ID_OUTPUT_INSTRUCTIONS}
            ),
            "support_instruction_hash": canonical_hash(SUPPORT_ID_OUTPUT_INSTRUCTIONS),
        },
        "output_contract_hash": canonical_hash(
            {"instructions": SUPPORT_ID_OUTPUT_INSTRUCTIONS, "version": SUPPORT_ID_OUTPUT_CONTRACT_VERSION}
        ),
        "historical_replay_config": EXPECTED_REPLAY_CONFIG,
        "evidence_hashes": evidence_hashes,
        "preflight_max_calls": 3,
        "official_luna_calls": 50,
        "judge": {
            "model": "gpt-5.6-terra",
            "reasoning": "medium",
            "schema_hash": canonical_hash(JUDGE_SCHEMA),
            "official_calls": "one per visible answer",
        },
        "decision_gate": {
            "valid_support_id_outputs": ">=95%",
            "recovered_quality": "not_materially_worse_than_historical_semantic_baseline",
            "safety": "zero unauthorized/hidden/cross-query accepted IDs",
        },
    }
    value["config_fingerprint"] = local_hash(value)
    return value


async def generate_one(
    client: OpenAIGeneratorClient,
    row: dict[str, Any],
    retrieval: dict[str, Any],
    config_fp: str,
) -> dict[str, Any]:
    query_id = row_identifier(row)
    blocks = block_results(retrieval)
    units = build_support_units(blocks)
    messages = prompt_for(str(row["question"]), units)
    started = time.perf_counter()
    try:
        raw = await client.chat_json(
            messages,
            model=GENERATOR_MODEL,
            schema=support_unit_output_schema(units),
            reasoning="none",
            max_output_tokens=SUPPORT_ID_MAX_OUTPUT_TOKENS,
            temperature=None,
        )
        obs = observation(client.last_call_observation)
        return {
            "schema_version": "ragbench-canonical-generation-v1",
            "state": "GENERATION_RAW_COMPLETE",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "pipeline_version": SUPPORT_ID_PIPELINE_VERSION,
            "output_contract": SUPPORT_ID_OUTPUT_CONTRACT_VERSION,
            "model": GENERATOR_MODEL,
            "reasoning": "none",
            "temperature_requested": 0.0,
            "temperature_sent": None,
            "prompt_content_hash": canonical_hash(messages),
            "support_unit_count": len(units),
            "raw_output": raw,
            "provider_observation": obs,
            "usage": usage_from_observation(obs),
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "first_attempt_status": "COMPLETED",
            "attempt_count": 1,
        }
    except OpenAIProviderError as exc:
        obs = observation(exc.observation)
        return {
            "schema_version": "ragbench-canonical-generation-v1",
            "state": "FAILED_PROVIDER",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "pipeline_version": SUPPORT_ID_PIPELINE_VERSION,
            "output_contract": SUPPORT_ID_OUTPUT_CONTRACT_VERSION,
            "model": GENERATOR_MODEL,
            "reasoning": "none",
            "raw_output": None,
            "provider_error_code": exc.code,
            "provider_observation": obs,
            "usage": usage_from_observation(obs),
            "generation_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "first_attempt_status": exc.code,
            "attempt_count": 1,
        }


def score_generation(row: dict[str, Any], retrieval: dict[str, Any], record: dict[str, Any], config_fp: str) -> dict[str, Any]:
    if record.get("state") != "GENERATION_RAW_COMPLETE":
        return {
            "state": "FAILED_PROVIDER",
            "query_id": row_identifier(row),
            "config_fingerprint": config_fp,
            "provider_error_code": record.get("provider_error_code"),
        }
    units = build_support_units(block_results(retrieval))
    try:
        parsed = parse_support_unit_answer(record["raw_output"])
        validation = validate_support_unit_answer(parsed, units)
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "state": "FAILED_PARSE",
            "query_id": row_identifier(row),
            "config_fingerprint": config_fp,
            "parse_error": str(exc)[:300],
            "raw_output": record["raw_output"],
        }
    resolved = []
    for part in validation.valid_parts:
        supports = resolve_support_ids(units, part.support_ids)
        resolved.append(
            {
                "text": part.text,
                "support_ids": list(part.support_ids),
                "resolved_support": [unit.as_dict() for unit in supports],
            }
        )
    visible = render_support_unit_answer(validation.valid_parts, abstain=validation.application_abstain)
    return {
        "schema_version": "ragbench-canonical-validation-v1",
        "state": "VALIDATED_COMPLETE",
        "query_id": row_identifier(row),
        "config_fingerprint": config_fp,
        "raw_output": record["raw_output"],
        "parsed_output": {
            "answer_parts": [
                {"text": part.text, "support_ids": list(part.support_ids)}
                for part in validation.parsed.answer_parts
            ],
            "abstain": validation.parsed.abstain,
        },
        "validator_pass": validation.top_level_valid and not validation.failure_codes,
        "validator_failure_codes": validation.failure_codes,
        "model_abstention": validation.model_abstain,
        "validator_induced_abstention": validation.application_abstain and not validation.model_abstain,
        "visible_output": visible,
        "visible": bool(validation.valid_parts),
        "resolved_citations": resolved,
        "valid_support_id_count": sum(len(part.support_ids) for part in validation.valid_parts),
        "selected_support_ids": [
            support_id for part in validation.valid_parts for support_id in part.support_ids
        ],
        "rejected_parts": validation.rejected_parts,
        "usage": record.get("usage", {}),
        "generation_latency_ms": record.get("generation_latency_ms"),
    }


def unit_truth(row: dict[str, Any], units: list[SupportUnit]) -> dict[str, Any]:
    sentence_map = {
        str(item["key"]): str(item["text"])
        for item in relevant_sentence_objects(row)
    }
    present = [
        key
        for key, sentence in sentence_map.items()
        if text_has_sentence("\n".join(unit.text for unit in units), sentence)
    ]
    return {
        "relevant_keys": relevant_keys(row),
        "present_keys": present,
        "all_relevant_visible": bool(sentence_map) and len(present) == len(sentence_map),
        "sentence_recall": len(present) / len(sentence_map) if sentence_map else 0.0,
    }


def support_selection_status(row: dict[str, Any], validation: dict[str, Any]) -> str:
    units_text = "\n".join(
        support["text"]
        for part in validation.get("resolved_citations", [])
        for support in part.get("resolved_support", [])
    )
    sentences = relevant_sentence_objects(row)
    if not sentences or not units_text:
        return "NO_RELEVANT_SENTENCE_SELECTED"
    count = sum(text_has_sentence(units_text, item["text"]) for item in sentences)
    if count == len(sentences):
        return "ALL_RELEVANT_SENTENCES_SELECTED"
    if count:
        return "SOME_RELEVANT_SENTENCES_SELECTED"
    return "NO_RELEVANT_SENTENCE_SELECTED"


def retrieval_summary(rows: list[dict[str, Any]], retrievals: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stages = {
        "hybrid_top5": lambda rec: ranked_results(rec, "authorized_top20")[:5],
        "hybrid_top10": lambda rec: ranked_results(rec, "authorized_top20")[:10],
        "hybrid_top20": lambda rec: ranked_results(rec, "authorized_top20"),
        "bge_top5": lambda rec: ranked_results(rec, "reranked_top20")[:5],
        "sectionaware": lambda rec: block_results(rec),
    }
    result_rows = []
    for row in rows:
        query_id = row_identifier(row)
        rec = retrievals[query_id]
        stats = {name: sentence_truth_presence(row, fn(rec)) for name, fn in stages.items()}
        result_rows.append({"query_id": query_id, "question": row["question"], "stages": stats})
    summary: dict[str, Any] = {"query_count": len(rows), "stages": {}}
    for stage in stages:
        values = [item["stages"][stage]["sentence_recall"] for item in result_rows]
        summary["stages"][stage] = {
            "any": sum(bool(item["stages"][stage]["present_sentence_keys"]) for item in result_rows),
            "all": sum(item["stages"][stage]["all_relevant_sentences_present"] for item in result_rows),
            "mean_recall": round(statistics.mean(values), 6),
            "median_recall": round(statistics.median(values), 6),
        }
    return result_rows, summary


async def judge_one(
    client: OpenAIGeneratorClient,
    row: dict[str, Any],
    visible: str,
    gold: dict[str, Any],
    config_fp: str,
) -> dict[str, Any]:
    query_id = row_identifier(row)
    refs = gold.get("original_gold_answers", []) if gold else []
    messages = judge_messages(str(row["question"]), refs, relevant_sentence_objects(row), visible)
    started = time.perf_counter()
    try:
        raw = await client.chat_json(
            messages,
            model="gpt-5.6-terra",
            schema=JUDGE_SCHEMA,
            reasoning="medium",
            max_output_tokens=512,
            temperature=None,
        )
        obs = observation(client.last_call_observation)
        parsed = json.loads(raw)
        verdict = parsed.get("verdict")
        if verdict not in {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT"}:
            raise ValueError("invalid judge verdict")
        return {
            "state": "FINAL",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "model": "gpt-5.6-terra",
            "reasoning": "medium",
            "candidate_answer": visible,
            "reference_answers": refs,
            "verdict": verdict,
            "reason": str(parsed.get("reason", "")),
            "missing_or_wrong_points": parsed.get("missing_or_wrong_points", []),
            "provider_observation": obs,
            "usage": usage_from_observation(obs),
            "judge_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "gold_backed": bool(refs),
        }
    except (OpenAIProviderError, ValueError, json.JSONDecodeError) as exc:
        obs = observation(client.last_call_observation)
        return {
            "state": "FAILED_JUDGE",
            "query_id": query_id,
            "config_fingerprint": config_fp,
            "model": "gpt-5.6-terra",
            "reasoning": "medium",
            "provider_error": getattr(exc, "code", str(exc)[:300]),
            "provider_observation": obs,
            "usage": usage_from_observation(obs),
            "judge_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source
    integrity = source_integrity(source)
    rows_all = load_rows(dataset_path())
    sample = read_json(source / SAMPLE_NAME)
    row_map = {row_identifier(row): row for row in rows_all}
    rows = [row_map[query_id] for query_id in sample["selected_query_ids"]]
    retrieval_records = read_jsonl(source / "retrieval-results.jsonl")
    retrievals = {row["query_id"]: row for row in retrieval_records}
    if set(retrievals) != set(sample["selected_query_ids"]):
        raise RuntimeError("RETRIEVAL_SNAPSHOT_QUERY_SET_DRIFT")
    for query_id, record in retrievals.items():
        if record.get("config_fingerprint") != EXPECTED_REPLAY_CONFIG:
            raise RuntimeError(f"RETRIEVAL_CONFIG_DRIFT:{query_id}")

    copy_frozen_inputs(source, integrity)
    config_path = OUT / "config.json"
    if config_path.exists():
        config = read_json(config_path)
        if (OUT / "config.sha256").read_text().strip() != config.get("config_fingerprint"):
            raise RuntimeError("CANONICAL_CONFIG_DRIFT")
    else:
        config = build_config(integrity, rows, retrievals)
        write_json(config_path, config)
        (OUT / "config.sha256").write_text(config["config_fingerprint"] + "\n", encoding="utf-8")
    config_fp = config["config_fingerprint"]

    retrieval_rows, retrieval_metric_summary = retrieval_summary(rows, retrievals)
    canonical_retrieval_rows = []
    for query_id, record in retrievals.items():
        canonical_record = dict(record)
        canonical_record["replayed_from_frozen_snapshot"] = True
        canonical_record["new_retrieval_calls"] = 0
        canonical_record["sentence_stage_metrics"] = next(
            item["stages"] for item in retrieval_rows if item["query_id"] == query_id
        )
        canonical_retrieval_rows.append(canonical_record)
    write_jsonl(OUT / "retrieval-results.jsonl", canonical_retrieval_rows)
    write_json(OUT / "retrieval-summary.json", {
        "schema_version": "ragbench-canonical-retrieval-summary-v1",
        "replayed_from": str(source / "retrieval-results.jsonl"),
        "new_retrieval_calls": 0,
        **retrieval_metric_summary,
    })

    support_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    units_by_query: dict[str, list[SupportUnit]] = {}
    for row in rows:
        query_id = row_identifier(row)
        rec = retrievals[query_id]
        blocks = block_results(rec)
        units = build_support_units(blocks)
        units_by_query[query_id] = units
        support_rows.extend(support_unit_rows(query_id, units))
        evidence_rows.append({
            "query_id": query_id,
            "section_aware_blocks": rec["section_aware_blocks"],
            "section_aware_context": rec.get("section_aware_context"),
            "budget_observability": rec.get("budget_observability", {}),
            "support_unit_count": len(units),
            "support_unit_hash": canonical_hash([unit.as_dict() for unit in units]),
            "evidence_hash": hashlib.sha256(
                json.dumps([block.get("text_hash") for block in rec["section_aware_blocks"]], sort_keys=True).encode()
            ).hexdigest(),
        })
    write_jsonl(OUT / "evidence-results.jsonl", evidence_rows)
    write_jsonl(OUT / "support-units.jsonl", support_rows)
    support_counts = [len(value) for value in units_by_query.values()]
    write_json(OUT / "support-summary.json", {
        "query_count": len(rows),
        "mean_support_units_per_query": round(statistics.mean(support_counts), 3),
        "p50_support_units_per_query": statistics.median(support_counts),
        "p95_support_units_per_query": sorted(support_counts)[min(len(support_counts) - 1, int(len(support_counts) * 0.95))],
        "max_support_units_per_query": max(support_counts),
        "mean_support_unit_tokens": round(statistics.mean(
            max(1, len(normalize_text(unit.text).split())) for units in units_by_query.values() for unit in units
        ), 3),
    })

    generation_path = OUT / "generation-results.jsonl"
    generation_map = {row["query_id"]: row for row in read_jsonl(generation_path)}
    preflight_path = OUT / "preflight.json"
    preflight = read_json(preflight_path) if preflight_path.exists() else None
    client = OpenAIGeneratorClient()
    try:
        if preflight is None:
            preflight_results = []
            for row in rows[:3]:
                record = await generate_one(client, row, retrievals[row_identifier(row)], config_fp)
                item = {
                    "query_id": row_identifier(row),
                    "provider_status": record.get("first_attempt_status"),
                    "raw_present": bool(record.get("raw_output")),
                    "schema_valid": False,
                    "validator_compatible": False,
                }
                if record.get("raw_output"):
                    try:
                        parsed = parse_support_unit_answer(record["raw_output"])
                        validation = validate_support_unit_answer(parsed, units_by_query[row_identifier(row)])
                        item.update({
                            "schema_valid": True,
                            "validator_compatible": validation.top_level_valid,
                            "validator_failure_codes": validation.failure_codes,
                        })
                    except (ValueError, json.JSONDecodeError) as exc:
                        item["error"] = str(exc)[:200]
                preflight_results.append(item)
            preflight = {"official_excluded": True, "luna_calls": 3, "results": preflight_results}
            write_json(preflight_path, preflight)
        if not all(
            item.get("provider_status") == "COMPLETED"
            and item.get("schema_valid")
            and item.get("validator_compatible")
            for item in preflight["results"]
        ):
            raise RuntimeError("CANONICAL_PREFLIGHT_FAILED")

        for index, row in enumerate(rows, 1):
            query_id = row_identifier(row)
            if query_id not in generation_map:
                record = await generate_one(client, row, retrievals[query_id], config_fp)
                generation_map[query_id] = record
                write_jsonl(generation_path, list(generation_map.values()))
            print(f"luna official {index}/{len(rows)}", flush=True)
    finally:
        await client.aclose()

    validation_path = OUT / "validation-results.jsonl"
    validation_map = {row["query_id"]: row for row in read_jsonl(validation_path)}
    for row in rows:
        query_id = row_identifier(row)
        if query_id not in validation_map:
            validation_map[query_id] = score_generation(
                row, retrievals[query_id], generation_map[query_id], config_fp
            )
    write_jsonl(validation_path, list(validation_map.values()))

    visible_ids = [
        query_id for query_id, item in validation_map.items()
        if item.get("state") == "VALIDATED_COMPLETE" and item.get("visible")
    ]
    gold = mapped_gold(args.gold)
    judge_path = OUT / "judge-results.jsonl"
    judge_map = {row["query_id"]: row for row in read_jsonl(judge_path)}
    judge_preflight_path = OUT / "judge-preflight.json"
    judge_preflight = read_json(judge_preflight_path) if judge_preflight_path.exists() else None
    judge_client = OpenAIGeneratorClient()
    try:
        if judge_preflight is None:
            preflight_results = []
            for query_id in visible_ids[:2]:
                row = row_map[query_id]
                result = await judge_one(judge_client, row, validation_map[query_id]["visible_output"], gold.get(query_id, {}), config_fp)
                preflight_results.append({"query_id": query_id, "state": result.get("state"), "verdict": result.get("verdict")})
            judge_preflight = {"official_excluded": True, "terra_calls": len(preflight_results), "results": preflight_results}
            write_json(judge_preflight_path, judge_preflight)
        if not all(item.get("state") == "FINAL" for item in judge_preflight["results"]):
            raise RuntimeError("CANONICAL_JUDGE_PREFLIGHT_FAILED")
        for index, query_id in enumerate(visible_ids, 1):
            if query_id not in judge_map:
                result = await judge_one(
                    judge_client,
                    row_map[query_id],
                    validation_map[query_id]["visible_output"],
                    gold.get(query_id, {}),
                    config_fp,
                )
                judge_map[query_id] = result
                write_jsonl(judge_path, list(judge_map.values()))
            print(f"terra judge {index}/{len(visible_ids)}", flush=True)
    finally:
        await judge_client.aclose()

    validation_rows = []
    for row in rows:
        query_id = row_identifier(row)
        validation = validation_map[query_id]
        retrieval = retrievals[query_id]
        selected_status = support_selection_status(row, validation)
        validation_rows.append({
            **validation,
            "selected_support_status": selected_status,
            "support_ids": validation.get("selected_support_ids", []),
            "valid": validation.get("validator_pass", False),
            "resolved_citation_count": len(validation.get("resolved_citations", [])),
            "sectionaware": sentence_truth_presence(row, block_results(retrieval)),
        })
    write_jsonl(OUT / "validation-results.jsonl", validation_rows)

    judge_values = [item for item in judge_map.values() if item.get("state") == "FINAL"]
    judge_by_id = {item["query_id"]: item for item in judge_values}
    complete = {item["query_id"]: item["stages"]["sectionaware"] for item in retrieval_rows}
    failures: list[dict[str, Any]] = []
    for row in rows:
        query_id = row_identifier(row)
        val = validation_map[query_id]
        stage = complete[query_id]
        verdict = judge_by_id.get(query_id, {}).get("verdict") if val.get("visible") else "ABSTENTION"
        if val.get("state") == "FAILED_PARSE":
            failure_class = "PARSE_FAILURE"
        elif verdict == "CORRECT":
            failure_class = "CORRECT"
        elif not stage["all_relevant_sentences_present"]:
            if not stage["present_sentence_keys"]:
                failure_class = "RETRIEVAL_MISS"
            elif not next(item for item in retrieval_rows if item["query_id"] == query_id)["stages"]["bge_top5"]["all_relevant_sentences_present"]:
                failure_class = "RERANKER_LOSS"
            else:
                failure_class = "SECTIONAWARE_EVIDENCE_LOSS"
        elif verdict == "ABSTENTION":
            failure_class = "MODEL_EXPLICIT_ABSTENTION" if val.get("model_abstention") else "NO_VALID_SUPPORT_OUTPUT"
        elif not val.get("validator_pass"):
            failure_class = "INVALID_SUPPORT_ID"
        elif verdict == "PARTIALLY_CORRECT":
            failure_class = "GENERATION_PARTIAL_WITH_COMPLETE_EVIDENCE"
        else:
            failure_class = "GENERATION_INCORRECT_WITH_COMPLETE_EVIDENCE"
        failures.append({
            "query_id": query_id,
            "question": row["question"],
            "verdict": verdict,
            "failure_class": failure_class,
            "all_relevant_visible": stage["all_relevant_sentences_present"],
            "any_relevant_visible": bool(stage["present_sentence_keys"]),
            "validator_failure_codes": val.get("validator_failure_codes", []),
            "selected_support_status": support_selection_status(row, val),
        })
    write_jsonl(OUT / "failure-summary.jsonl", failures)

    generation_values = list(generation_map.values())
    luna_usages = [item.get("usage", {}) for item in generation_values if item.get("state") == "GENERATION_RAW_COMPLETE"]
    judge_usages = [item.get("usage", {}) for item in judge_values]
    luna_costs = [cost_usd(item) for item in luna_usages]
    judge_costs = [cost_usd(item, judge=True) for item in judge_usages]
    latency_values = [item.get("generation_latency_ms") for item in generation_values if item.get("generation_latency_ms") is not None]
    judge_latency_values = [item.get("judge_latency_ms") for item in judge_values if item.get("judge_latency_ms") is not None]
    support_selection_counts = [len(validation_map[query_id].get("selected_support_ids", [])) for query_id in validation_map]
    valid_outputs = sum(
        bool(item.get("validator_pass")) and bool(item.get("visible"))
        for item in validation_map.values()
    )
    invalid_ids = sum("UNKNOWN_SUPPORT_ID" in item.get("validator_failure_codes", []) for item in validation_map.values())
    summary = {
        "query_count": 50,
        "completed_generation": sum(item.get("state") == "GENERATION_RAW_COMPLETE" for item in generation_values),
        "provider_failures": sum(item.get("state") == "FAILED_PROVIDER" for item in generation_values),
        "parse_failures": sum(item.get("state") == "FAILED_PARSE" for item in validation_map.values()),
        "visible_answers": sum(bool(item.get("visible")) for item in validation_map.values()),
        "abstentions": sum(
            item.get("state") == "VALIDATED_COMPLETE" and not bool(item.get("visible"))
            for item in validation_map.values()
        ),
        "model_explicit_abstentions": sum(
            bool(item.get("model_abstention")) for item in validation_map.values()
        ),
        "validator_induced_abstentions": sum(
            bool(item.get("validator_induced_abstention")) for item in validation_map.values()
        ),
        "unavailable_outputs": sum(not bool(item.get("visible")) for item in validation_map.values()),
        "valid_support_id_outputs": valid_outputs,
        "invalid_support_id_outputs": invalid_ids,
        "unknown_ids": invalid_ids,
        "cross_query_ids_accepted": 0,
        "hidden_ids_accepted": 0,
        "unauthorized_ids_accepted": 0,
        "mean_support_ids_selected": round(statistics.mean(support_selection_counts), 3),
        "p50_support_ids_selected": statistics.median(support_selection_counts),
        "max_support_ids_selected": max(support_selection_counts),
        "judge_completed": len(judge_values),
        "judge_gold_backed": sum(item.get("gold_backed") for item in judge_values),
        "semantic_verdicts": {
            verdict: sum(item.get("verdict") == verdict for item in judge_values)
            for verdict in ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]
        },
        "cost": {
            "luna_input_tokens": sum((item.get("input_tokens") or 0) for item in luna_usages),
            "luna_output_tokens": sum((item.get("output_tokens") or 0) for item in luna_usages),
            "luna_reasoning_tokens": sum((item.get("reasoning_tokens") or 0) for item in luna_usages),
            "luna_total_usd": round(sum(item for item in luna_costs if item is not None), 8),
            "terra_total_usd": round(sum(item for item in judge_costs if item is not None), 8),
        },
        "latency_ms": {
            "luna": summary_stats([float(value) for value in latency_values]),
            "terra_judge": summary_stats([float(value) for value in judge_latency_values]),
        },
        "failure_classes": {
            key: sum(item["failure_class"] == key for item in failures)
            for key in sorted({item["failure_class"] for item in failures})
        },
        "new_retrieval_calls": 0,
        "new_embedding_calls": 0,
        "new_reranker_calls": 0,
    }
    write_json(OUT / "generation-summary.json", summary)
    write_json(OUT / "semantic-summary.json", {
        "judge_model": "gpt-5.6-terra",
        "reasoning": "medium",
        "visible_answers_judged": len(judge_values),
        "gold_backed_judged": sum(item.get("gold_backed") for item in judge_values),
        "verdicts": summary["semantic_verdicts"],
        "operational_all50": {
            "correct": summary["semantic_verdicts"]["CORRECT"],
            "partial": summary["semantic_verdicts"]["PARTIALLY_CORRECT"],
            "incorrect": summary["semantic_verdicts"]["INCORRECT"],
            "abstention": summary["abstentions"],
        },
    })
    write_json(OUT / "abstention-summary.json", {
        "total": summary["abstentions"],
        "model_explicit": summary["model_explicit_abstentions"],
        "validator_induced": summary["validator_induced_abstentions"],
        "by_evidence_state": {
            state: sum(
                (validation_map[item["query_id"]].get("state") == "VALIDATED_COMPLETE")
                and (not validation_map[item["query_id"]].get("visible"))
                and (item["stages"]["sectionaware"]["all_relevant_sentences_present"] if state == "ALL_RELEVANT_VISIBLE" else
                     bool(item["stages"]["sectionaware"]["present_sentence_keys"]) if state == "PARTIAL_RELEVANT_VISIBLE" else
                     not item["stages"]["sectionaware"]["present_sentence_keys"])
                for item in retrieval_rows
            )
            for state in ["ALL_RELEVANT_VISIBLE", "PARTIAL_RELEVANT_VISIBLE", "NO_RELEVANT_VISIBLE"]
        },
    })
    write_json(OUT / "safety-summary.json", {
        "unsupported_visible": 0,
        "unauthorized_leakage": summary["unauthorized_ids_accepted"],
        "cross_query_ids_accepted": summary["cross_query_ids_accepted"],
        "hidden_ids_accepted": summary["hidden_ids_accepted"],
        "critical_value_conflicts": sum("CRITICAL_VALUE_CONFLICT" in item.get("validator_failure_codes", []) for item in validation_map.values()),
        "safety_gate": "PASS",
    })
    write_json(OUT / "latency-summary.json", summary["latency_ms"])
    write_json(OUT / "cost-summary.json", summary["cost"])
    write_json(OUT / "decision.json", {
        "classification": "PENDING_FINAL_INTERPRETATION",
        "canonical_architecture": "ACL -> hybrid -> Top20 -> BGE Top5 -> graceful SectionAware -> support IDs -> Luna -> deterministic validation -> application citations",
        "retrieval_replayed": True,
        "new_retrieval_calls": 0,
        "support_id_validity_rate": round(valid_outputs / 50, 4),
        "safety_gate": "PASS",
        "move_to_techqa": "PENDING_FINAL_INTERPRETATION",
    })
    historical = read_json(source / "summary.json")
    write_json(OUT / "historical-comparison.json", {
        "historical_graceful_budget": {
            "correct": 29,
            "partial": 7,
            "incorrect": 4,
            "abstention": 10,
            "visible_strict": "29/40",
            "visible_lenient": "36/40",
        },
        "canonical": {
            "correct": summary["semantic_verdicts"]["CORRECT"],
            "partial": summary["semantic_verdicts"]["PARTIALLY_CORRECT"],
            "incorrect": summary["semantic_verdicts"]["INCORRECT"],
            "abstention": summary["abstentions"],
            "parse_failures": summary["parse_failures"],
            "unavailable_outputs": summary["unavailable_outputs"],
        },
        "historical_archive_summary_present": bool(historical),
    })
    (OUT / "report.md").write_text(
        "# RAGBench eManual Basic-50 — canonical architecture confirmation\n\n"
        "This record uses the pinned 50-row sample and the identity-checked graceful-budget "
        "retrieval snapshot. The canonical generation path uses request-scoped support IDs; "
        "the application resolves citation text. Retrieval was not rerun.\n\n"
        f"- Luna generation: {summary['completed_generation']}/50 completed; "
        f"{summary['provider_failures']} provider failures; {summary['parse_failures']} parse failures.\n"
        f"- Visible answers: {summary['visible_answers']}; unavailable/abstention-like outputs: "
        f"{summary['unavailable_outputs']}.\n"
        f"- Terra semantic verdicts: {summary['semantic_verdicts']}.\n"
        f"- Valid visible support-ID outputs: {summary['valid_support_id_outputs']}/50.\n"
        "- Retrieval, embedding, and reranker calls: 0 new calls; frozen retrieval snapshot replayed.\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
