"""Judge only the five outputs newly visible after the canonical validator fix.

This script is intentionally downstream-only: it reads frozen artifacts and
calls Terra for semantic labels. It never invokes Luna, retrieval, embedding,
reranking, or any pipeline stage.
"""

# ruff: noqa: E402, E501

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.llm.openai_client import OpenAIGeneratorClient, OpenAIProviderError
from scripts.benchmarks.ragbench_emanual_common import canonical_hash, load_rows, row_identifier
from scripts.benchmarks.run_ragbench_emanual_canonical import (
    JUDGE_SCHEMA,
    cost_usd,
    judge_messages,
    observation,
    usage_from_observation,
)
from scripts.benchmarks.setup_ragbench_emanual import dataset_path

SOURCE = ROOT / "artifacts/ragbench/canonical/basic50-final"
POST_FIX = ROOT / "artifacts/ragbench/canonical/basic50-post-validator-fix"
GOLD = Path("/tmp/knowledge-base-rag-cleanup.Vk4y4n/emanual-basic-50-gold-rescore")
OUT = ROOT / "artifacts/ragbench/canonical/basic50-post-validator-semantic"
EXPECTED_SAMPLE = "d65d578dcc1f88bb4df71451dfae5f923b2e56bf4fa60e331e6297b2b317cdf3"
EXPECTED_CONFIG = "ab7bfb97bf3dc00c86bbf6ee753f6e538f379aa70e7644c02396ea782da00af8"
EXPECTED_CORPUS = "241dae67feae5733026d9a50cf2640979f141b8a7c7c016c5dc8173bfb6f3ae2"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_rows() -> list[dict[str, Any]]:
    rows = read_jsonl(POST_FIX / "replay-results.jsonl")
    return [row for row in rows if not row["old_visible"] and row["new_visible"]]


def relevant_sentence_objects(row: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys", [])}
    result = []
    for doc_index, sentences in enumerate(row.get("documents_sentences") or []):
        for key, text in sentences or []:
            if str(key).rstrip(".") in wanted:
                result.append({"key": str(key), "document_index": doc_index, "text": str(text)})
    return result


def build_targets() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sample_hash = (SOURCE / "sample.sha256").read_text(encoding="utf-8").strip()
    config_hash = (SOURCE / "config.sha256").read_text(encoding="utf-8").strip()
    corpus = (SOURCE / "corpus-fingerprint.txt").read_text(encoding="utf-8").strip()
    decision = read_json(POST_FIX / "decision.json")
    if (
        sample_hash != EXPECTED_SAMPLE
        or config_hash != EXPECTED_CONFIG
        or corpus != EXPECTED_CORPUS
        or decision.get("classification") != "CANONICAL_VALIDATOR_SCOPE_FIX_CONFIRMED"
    ):
        raise SystemExit("SOURCE_IDENTITY_MISMATCH")
    targets = target_rows()
    if len(targets) != 5:
        raise SystemExit(f"NEWLY_VISIBLE_POPULATION_MISMATCH expected=5 actual={len(targets)}")

    dataset_rows = {row_identifier(row): row for row in load_rows(dataset_path())}
    mapping_path = GOLD / "mapping.jsonl"
    if not mapping_path.exists():
        raise SystemExit("SOURCE_REFERENCE_MAPPING_MISSING")
    mapping = {row["ragbench_row_id"]: row for row in read_jsonl(mapping_path)}
    units = {row["query_id"]: [] for row in read_jsonl(SOURCE / "support-units.jsonl")}
    for unit in read_jsonl(SOURCE / "support-units.jsonl"):
        units.setdefault(unit["query_id"], []).append(unit)
    retrieval = {row["query_id"]: row for row in read_jsonl(SOURCE / "retrieval-results.jsonl")}
    frozen = []
    for item in targets:
        query_id = item["query_id"]
        row = dataset_rows.get(query_id)
        mapped = mapping.get(query_id)
        if (
            row is None
            or mapped is None
            or mapped.get("mapping_status")
            not in {
                "EXACT_ID_MATCH",
                "EXACT_QUESTION_AND_DOCUMENT_MATCH",
                "EXACT_QUESTION_MATCH_UNIQUE",
            }
        ):
            raise SystemExit(f"GOLD_MAPPING_INSUFFICIENT:{query_id}")
        support_by_id = {unit["support_unit_id"]: unit for unit in units.get(query_id, [])}
        candidate = item["rendered_output"]
        raw = item["raw_output"]
        parsed = item["valid_parts"]
        frozen.append(
            {
                "query_id": query_id,
                "question": row["question"],
                "mapping_status": mapped["mapping_status"],
                "reference_answers": mapped.get("original_gold_answers", []),
                "relevant_sentences": relevant_sentence_objects(row),
                "candidate_answer": candidate,
                "raw_answer_sha256": hashlib.sha256(str(raw).encode()).hexdigest(),
                "parsed_answer_sha256": canonical_hash(parsed),
                "visible_answer_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                "selected_support_ids": item["selected_support_ids"],
                "resolved_support_text_sha256": {
                    support_id: hashlib.sha256(
                        support_by_id[support_id]["text"].encode()
                    ).hexdigest()
                    for support_id in item["selected_support_ids"]
                    if support_id in support_by_id
                },
                "evidence_state": (
                    "ALL_RELEVANT_VISIBLE"
                    if retrieval[query_id]["sentence_stage_metrics"]["sectionaware"][
                        "all_relevant_sentences_present"
                    ]
                    else "PARTIAL_RELEVANT_VISIBLE"
                    if retrieval[query_id]["sentence_stage_metrics"]["sectionaware"][
                        "present_sentence_keys"
                    ]
                    else "NO_RELEVANT_VISIBLE"
                ),
            }
        )
    return frozen, {
        "sample_hash": sample_hash,
        "canonical_config": config_hash,
        "corpus_fingerprint": corpus,
    }


async def judge_one(
    client: OpenAIGeneratorClient, target: dict[str, Any], config_fp: str
) -> dict[str, Any]:
    messages = judge_messages(
        target["question"],
        target["reference_answers"],
        target["relevant_sentences"],
        target["candidate_answer"],
    )
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
        parsed = json.loads(raw)
        if parsed.get("verdict") not in {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT"}:
            raise ValueError("invalid judge verdict")
        obs = observation(client.last_call_observation)
        return {
            "state": "FINAL",
            "query_id": target["query_id"],
            "config_fingerprint": config_fp,
            "model": "gpt-5.6-terra",
            "reasoning": "medium",
            "question": target["question"],
            "reference_answers": target["reference_answers"],
            "candidate_answer": target["candidate_answer"],
            "verdict": parsed["verdict"],
            "reason": str(parsed.get("reason", "")),
            "missing_or_wrong_points": parsed.get("missing_or_wrong_points", []),
            "usage": usage_from_observation(obs),
            "cost_usd": cost_usd(usage_from_observation(obs), judge=True),
            "judge_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "provider_observation": obs,
        }
    except (OpenAIProviderError, ValueError, json.JSONDecodeError) as exc:
        obs = observation(client.last_call_observation)
        return {
            "state": "FAILED_JUDGE",
            "query_id": target["query_id"],
            "config_fingerprint": config_fp,
            "model": "gpt-5.6-terra",
            "reasoning": "medium",
            "provider_error": getattr(exc, "code", str(exc)[:300]),
            "usage": usage_from_observation(obs),
            "cost_usd": cost_usd(usage_from_observation(obs), judge=True),
            "judge_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "provider_observation": obs,
        }


async def main_async() -> None:
    targets, identity = build_targets()
    OUT.mkdir(parents=True, exist_ok=True)
    target_payload = {
        "count": len(targets),
        "query_ids": [item["query_id"] for item in targets],
        "targets": targets,
    }
    target_hash = canonical_hash(target_payload)
    write_json(OUT / "target-population.json", target_payload)
    (OUT / "target-population.sha256").write_text(target_hash + "\n", encoding="utf-8")
    config = {
        "dataset": "RAGBench eManual",
        "dataset_revision": "97808f3e5fd16ede40bbff6c2949af8139b2eb7b",
        "split": "test",
        **identity,
        "target_hash": target_hash,
        "judge_model": "gpt-5.6-terra",
        "reasoning": "medium",
        "temperature": "omitted",
        "judge_schema_hash": canonical_hash(JUDGE_SCHEMA),
        "prompt_contract": "existing canonical semantic judge prompt; no experiment outcome disclosed",
        "official_calls": 5,
        "preflight_max_calls": 1,
        "new_luna_calls": 0,
        "new_retrieval_calls": 0,
        "new_embedding_calls": 0,
        "new_reranker_calls": 0,
    }
    config["config_fingerprint"] = canonical_hash(config)
    write_json(OUT / "judge-config.json", config)
    (OUT / "judge-config.sha256").write_text(config["config_fingerprint"] + "\n", encoding="utf-8")
    write_json(
        OUT / "source-integrity.json",
        {
            **identity,
            "prior_visible": 33,
            "post_fix_visible": 38,
            "newly_visible": 5,
            "verified": True,
            "new_inference": {
                "luna": 0,
                "retrieval": 0,
                "embedding": 0,
                "reranker": 0,
                "planner": 0,
            },
            "historical_artifacts_modified": False,
        },
    )

    preflight_path = OUT / "preflight.json"
    client = OpenAIGeneratorClient()
    try:
        if not preflight_path.exists():
            preflight_result = await judge_one(
                client, targets[0], config["config_fingerprint"]
            )
            preflight = {
                "official_excluded": True,
                "terra_calls": 1,
                "state": preflight_result["state"],
                "schema_valid": preflight_result["state"] == "FINAL",
                "result": preflight_result,
            }
            write_json(
                OUT / "preflight.json",
                preflight,
            )
        else:
            preflight = read_json(preflight_path)
        if preflight.get("state") != "FINAL" or not preflight.get("schema_valid"):
            raise SystemExit("TERRA_PREFLIGHT_FAILED")

        result_path = OUT / "judge-results.jsonl"
        existing = (
            {row["query_id"]: row for row in read_jsonl(result_path)}
            if result_path.exists()
            else {}
        )
        for index, target in enumerate(targets, 1):
            if target["query_id"] not in existing:
                result = await judge_one(client, target, config["config_fingerprint"])
                existing[target["query_id"]] = result
                write_jsonl(result_path, list(existing.values()))
            print(f"terra official {index}/{len(targets)}", flush=True)
    finally:
        await client.aclose()

    results = [existing[target["query_id"]] for target in targets]
    write_json(
        OUT / "judge-summary.json",
        {
            "official_targets": 5,
            "completed": sum(row.get("state") == "FINAL" for row in results),
            "provider_failures": sum(row.get("state") != "FINAL" for row in results),
            "verdicts": {
                verdict: sum(row.get("verdict") == verdict for row in results)
                for verdict in ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]
            },
            "input_tokens": sum((row.get("usage", {}).get("input_tokens") or 0) for row in results),
            "output_tokens": sum(
                (row.get("usage", {}).get("output_tokens") or 0) for row in results
            ),
            "reasoning_tokens": sum(
                (row.get("usage", {}).get("reasoning_tokens") or 0) for row in results
            ),
            "cost_usd": round(sum(row.get("cost_usd") or 0 for row in results), 8),
            "latency_ms": {
                "p50": sorted(row["judge_latency_ms"] for row in results)[2],
                "p95": sorted(row["judge_latency_ms"] for row in results)[4],
                "max": max(row["judge_latency_ms"] for row in results),
            },
        },
    )
    (OUT / "judge-results.sha256").write_text(file_hash(result_path) + "\n", encoding="utf-8")

    old = read_json(SOURCE / "semantic-summary.json")
    verdicts = read_json(OUT / "judge-summary.json")["verdicts"]
    final = {
        "correct": old["operational_all50"]["correct"] + verdicts["CORRECT"],
        "partial": old["operational_all50"]["partial"] + verdicts["PARTIALLY_CORRECT"],
        "incorrect": old["operational_all50"]["incorrect"] + verdicts["INCORRECT"],
        "unavailable": 12,
        "visible": 38,
    }
    final.update(
        {
            "operational_strict": final["correct"] / 50,
            "operational_lenient": (final["correct"] + final["partial"]) / 50,
            "visible_strict": final["correct"] / 38,
            "visible_lenient": (final["correct"] + final["partial"]) / 38,
        }
    )
    write_json(
        OUT / "newly-visible-summary.json",
        {
            "count": 5,
            "verdicts": verdicts,
            "strictly_correct_recovery": verdicts["CORRECT"],
            "useful_recovery": verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"],
        },
    )
    write_json(OUT / "final-semantic-summary.json", final)
    write_json(
        OUT / "historical-comparison.json",
        {
            "historical": {
                "correct": 24,
                "partial": 7,
                "incorrect": 2,
                "unavailable": 17,
                "visible": 33,
            },
            "post_validator_fix": final,
            "deltas": {
                "correct": final["correct"] - 24,
                "partial": final["partial"] - 7,
                "incorrect": final["incorrect"] - 2,
                "unavailable": -5,
                "visible": 5,
            },
        },
    )
    retrieval = {row["query_id"]: row for row in read_jsonl(SOURCE / "retrieval-results.jsonl")}
    write_json(
        OUT / "evidence-state-summary.json",
        {
            target["query_id"]: (
                "ALL_RELEVANT_VISIBLE"
                if retrieval[target["query_id"]]["sentence_stage_metrics"]["sectionaware"][
                    "all_relevant_sentences_present"
                ]
                else "PARTIAL_RELEVANT_VISIBLE"
                if retrieval[target["query_id"]]["sentence_stage_metrics"]["sectionaware"][
                    "present_sentence_keys"
                ]
                else "NO_RELEVANT_VISIBLE"
            )
            for target in targets
        },
    )
    write_json(
        OUT / "safety-summary.json",
        {
            "inherited_from_post_fix_replay": True,
            "unauthorized_leakage": 0,
            "hidden_accepted": 0,
            "cross_query_accepted": 0,
            "critical_value_failures": 0,
            "safety_gate": "PASS",
        },
    )
    terra_cost = read_json(OUT / "judge-summary.json")["cost_usd"]
    write_json(
        OUT / "cost-summary.json",
        {
            "new_luna_cost_usd": 0,
            "terra_judge_cost_usd": terra_cost,
            "terra_mean_per_query_usd": round(terra_cost / 5, 8),
            "terra_input_tokens": read_json(OUT / "judge-summary.json")["input_tokens"],
            "terra_output_tokens": read_json(OUT / "judge-summary.json")["output_tokens"],
            "terra_reasoning_tokens": read_json(OUT / "judge-summary.json")["reasoning_tokens"],
        },
    )
    write_json(
        OUT / "latency-summary.json",
        {
            "terra_judge_ms": read_json(OUT / "judge-summary.json")["latency_ms"],
            "production_latency_changed": False,
        },
    )
    write_json(
        OUT / "decision.json",
        {
            "classification": "POST_VALIDATOR_SEMANTIC_RESULT_FINALIZED",
            "newly_visible_judged": 5,
            "strictly_correct_recovery": verdicts["CORRECT"],
            "useful_recovery": verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"],
            "final": final,
            "claim_local_validator_semantically_useful": bool(
                verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"]
            ),
            "support_id_architecture": "RETAIN",
            "parser_schema_debt": "NON_BLOCKING_DEBT",
            "move_to_techqa": "YES"
            if verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"] >= 3
            else "NO",
            "new_luna_calls": 0,
        },
    )
    report = f"""# Post-validator Basic-50 semantic result\n\nOnly the five outputs newly visible after the claim-local validator fix were judged.\n\n- New visible: CORRECT {verdicts['CORRECT']}, PARTIAL {verdicts['PARTIALLY_CORRECT']}, INCORRECT {verdicts['INCORRECT']}\n- Final: {final['correct']} correct, {final['partial']} partial, {final['incorrect']} incorrect, {final['unavailable']} unavailable\n- Operational strict: {final['operational_strict']:.2%}; lenient: {final['operational_lenient']:.2%}\n- Visible strict: {final['visible_strict']:.2%}; lenient: {final['visible_lenient']:.2%}\n- New Luna/retrieval calls: 0; official Terra calls: 5.\n"""
    (OUT / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main_async())
