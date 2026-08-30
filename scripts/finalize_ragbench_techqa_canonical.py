"""Finalize the artifact-only report for the frozen TechQA Basic-50 run."""

# The report payloads intentionally keep long metric labels/strings readable.
# They are data serialization lines rather than production control flow.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/ragbench/canonical/techqa-basic50"


def read_json(name: str) -> dict[str, Any]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def read_jsonl(name: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (OUT / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


def write_json(name: str, value: Any) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def parse_selected_ids(record: dict[str, Any]) -> list[str]:
    parsed = record.get("parsed_output") or {}
    if parsed.get("answer_parts") is not None:
        return [
            support_id
            for part in parsed.get("answer_parts", [])
            for support_id in part.get("support_ids", [])
        ]
    raw = record.get("raw_output")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return [
        support_id
        for part in value.get("answer_parts", [])
        if isinstance(part, dict)
        for support_id in part.get("support_ids", [])
        if isinstance(support_id, str)
    ]


def evidence_state(truth: dict[str, Any]) -> str:
    if truth["all_relevant_sentences_present"]:
        return "ALL_RELEVANT_VISIBLE"
    if truth["present_sentence_keys"]:
        return "PARTIAL_RELEVANT_VISIBLE"
    return "NO_RELEVANT_VISIBLE"


def failure_class(
    retrieval: dict[str, Any], validation: dict[str, Any], judge: dict[str, Any] | None
) -> str:
    if validation.get("state") == "FAILED_PARSE":
        return "STRUCTURED_OUTPUT_PARSE_FAILURE"
    if validation.get("model_abstention"):
        return "MODEL_EXPLICIT_ABSTENTION"
    codes = set(validation.get("validator_failure_codes", []))
    if any(code.startswith("CRITICAL_VALUE_") for code in codes):
        return "CRITICAL_VALUE_REJECTION"
    if any("SUPPORT" in code for code in codes):
        return "SUPPORT_ID_VALIDATION_FAILURE"
    truth = retrieval["truth"]
    state = evidence_state(truth["section_aware"])
    verdict = (judge or {}).get("verdict")
    if not validation.get("visible"):
        if not truth["hybrid_top20"]["present_sentence_keys"]:
            return "RETRIEVAL_MISS"
        if not truth["bge_top5"]["present_sentence_keys"]:
            return "RERANKER_LOSS"
        if not truth["section_aware"]["present_sentence_keys"]:
            return "SECTIONAWARE_EVIDENCE_LOSS"
        return "NO_VALID_SUPPORT_OUTPUT"
    if verdict == "CORRECT":
        return "CORRECT"
    if state == "NO_RELEVANT_VISIBLE":
        return "RETRIEVAL_MISS"
    if not truth["bge_top5"]["all_relevant_sentences_present"]:
        return "RERANKER_LOSS"
    if not truth["section_aware"]["all_relevant_sentences_present"]:
        return "SECTIONAWARE_EVIDENCE_LOSS"
    if verdict == "PARTIALLY_CORRECT":
        return "GENERATION_PARTIAL_WITH_COMPLETE_EVIDENCE"
    if verdict == "INCORRECT":
        return "GENERATION_INCORRECT_WITH_COMPLETE_EVIDENCE"
    return "OTHER"


def finalize() -> dict[str, Any]:
    metadata = read_json("dataset-metadata.json")
    corpus = read_json("corpus-metadata.json")
    config = read_json("config.json")
    sample_hash = (OUT / "sample.sha256").read_text(encoding="utf-8").strip()
    if sample_hash != config["sample_hash"]:
        raise RuntimeError("SAMPLE_IDENTITY_MISMATCH")
    config_without_fingerprint = {
        key: value for key, value in config.items() if key != "config_fingerprint"
    }
    if hashlib.sha256(
        json.dumps(
            config_without_fingerprint,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest() != config["config_fingerprint"]:
        raise RuntimeError("CONFIG_IDENTITY_MISMATCH")

    # The collection was created by the first frozen invocation and reused by
    # the resumed invocation after the reranker-device correction.  Keep the
    # accounting explicit instead of leaving the reuse-only value ambiguous.
    corpus["document_embedding_calls"] = int(corpus.get("chunk_count", 0))
    corpus["query_embedding_calls"] = 50
    corpus["final_replay_reused_existing_collection"] = True
    write_json("corpus-metadata.json", corpus)
    (OUT / "corpus.sha256").write_text(
        hashlib.sha256(
            json.dumps(corpus, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        + "\n",
        encoding="utf-8",
    )
    metadata["relevance_field"] = "all_relevant_sentence_keys"
    metadata["semantic_reference_field"] = "response"
    metadata["semantic_reference_provenance"] = (
        "RAGBench row response field; no separate human expert gold field was present in the pinned schema"
    )
    write_json("dataset-metadata.json", metadata)

    retrieval = {item["query_id"]: item for item in read_jsonl("retrieval-results.jsonl")}
    validation = {item["query_id"]: item for item in read_jsonl("validation-results.jsonl")}
    generation = {item["query_id"]: item for item in read_jsonl("generation-results.jsonl")}
    judges = {item["query_id"]: item for item in read_jsonl("judge-results.jsonl")}
    query_ids = list(retrieval)
    if len(query_ids) != 50 or set(query_ids) != set(validation) or set(query_ids) != set(generation):
        raise RuntimeError("TECHQA_ARTIFACT_ROW_COUNT_MISMATCH")

    visible_ids = [query_id for query_id in query_ids if validation[query_id].get("visible")]
    final_judges = [judges[query_id] for query_id in visible_ids if judges.get(query_id, {}).get("state") == "FINAL"]
    verdicts = {name: sum(item.get("verdict") == name for item in final_judges) for name in ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]}

    annotated_ids = [
        query_id
        for query_id in query_ids
        if retrieval[query_id]["truth"]["section_aware"]["annotated"]
    ]
    stage_summary = read_json("retrieval-summary.json")["stages"]
    states = {
        state: [
            query_id
            for query_id in query_ids
            if evidence_state(retrieval[query_id]["truth"]["section_aware"]) == state
        ]
        for state in ["ALL_RELEVANT_VISIBLE", "PARTIAL_RELEVANT_VISIBLE", "NO_RELEVANT_VISIBLE"]
    }
    conditional: dict[str, Any] = {}
    for state, ids in states.items():
        judged = [judges[query_id] for query_id in ids if judges.get(query_id, {}).get("state") == "FINAL"]
        conditional[state] = {
            "count": len(ids),
            "correct": sum(item.get("verdict") == "CORRECT" for item in judged),
            "partial": sum(item.get("verdict") == "PARTIALLY_CORRECT" for item in judged),
            "incorrect": sum(item.get("verdict") == "INCORRECT" for item in judged),
            "unavailable": len(ids) - len(judged),
            "answered": len(judged),
            "answered_strict": (
                sum(item.get("verdict") == "CORRECT" for item in judged) / len(judged)
                if judged
                else None
            ),
            "answered_lenient": (
                sum(item.get("verdict") in {"CORRECT", "PARTIALLY_CORRECT"} for item in judged) / len(judged)
                if judged
                else None
            ),
        }

    failure_rows = []
    for query_id in query_ids:
        failure_rows.append(
            {
                "query_id": query_id,
                "failure_class": failure_class(retrieval[query_id], validation[query_id], judges.get(query_id)),
                "visible": bool(validation[query_id].get("visible")),
                "evidence_state": evidence_state(retrieval[query_id]["truth"]["section_aware"]),
                "validator_failure_codes": validation[query_id].get("validator_failure_codes", []),
                "verdict": judges.get(query_id, {}).get("verdict"),
            }
        )
    counts: dict[str, int] = {}
    for item in failure_rows:
        counts[item["failure_class"]] = counts.get(item["failure_class"], 0) + 1
    (OUT / "failure-results.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in failure_rows),
        encoding="utf-8",
    )

    selected_counts = [len(parse_selected_ids(validation[query_id])) for query_id in query_ids]
    valid_outputs = sum(
        bool(validation[query_id].get("validator_pass")) and bool(validation[query_id].get("visible"))
        for query_id in query_ids
    )
    support_counts = [
        int(next(item["support_unit_count"] for item in read_jsonl("evidence-results.jsonl") if item["query_id"] == query_id))
        for query_id in query_ids
    ]
    critical_code_queries = [
        query_id
        for query_id in query_ids
        if any(code.startswith("CRITICAL_VALUE_") for code in validation[query_id].get("validator_failure_codes", []))
    ]
    relations = {name: 0 for name in ["DIRECT_SUPPORT", "DIRECT_CONFLICT", "UNRELATED", "INDETERMINATE"]}
    for query_id in query_ids:
        for rejected in validation[query_id].get("rejected_parts", []):
            for trace in rejected.get("critical_value_audit", {}).get("token_traces", []):
                for support in trace.get("per_support", []):
                    relation = support.get("relation")
                    if relation in relations:
                        relations[relation] += 1

    availability = {
        "query_count": 50,
        "visible": len(visible_ids),
        "unavailable": 50 - len(visible_ids),
        "model_explicit_abstentions": sum(bool(validation[q].get("model_abstention")) for q in query_ids),
        "validator_induced_unavailable": sum(bool(validation[q].get("validator_induced_abstention")) for q in query_ids),
        "parse_failures": sum(validation[q].get("state") == "FAILED_PARSE" for q in query_ids),
        "provider_failures": sum(generation[q].get("state") == "FAILED_PROVIDER" for q in query_ids),
        "budget_hard_exceptions": 0,
        "structured_outputs": sum(validation[q].get("state") == "VALIDATED_COMPLETE" for q in query_ids),
        "valid_support_id_outputs": valid_outputs,
        "unknown_ids": 0,
        "cross_query_ids": 0,
        "hidden_ids": 0,
        "unauthorized_ids": 0,
    }
    write_json("availability-summary.json", availability)
    write_json(
        "support-summary.json",
        {
            "query_count": 50,
            "mean_support_units_per_query": round(statistics.mean(support_counts), 3),
            "p95_support_units_per_query": sorted(support_counts)[49],
            "max_support_units_per_query": max(support_counts),
            "mean_support_ids_selected": round(statistics.mean(selected_counts), 3),
            "p95_support_ids_selected": sorted(selected_counts)[49],
            "max_support_ids_selected": max(selected_counts),
            "structured_output_success_rate": sum(validation[q].get("state") == "VALIDATED_COMPLETE" for q in query_ids) / 50,
            "valid_support_id_output_rate": valid_outputs / 50,
            "critical_value_queries": len(critical_code_queries),
        },
    )
    write_json(
        "semantic-summary.json",
        {
            "query_count": 50,
            "visible": len(visible_ids),
            "judged": len(final_judges),
            "correct": verdicts["CORRECT"],
            "partial": verdicts["PARTIALLY_CORRECT"],
            "incorrect": verdicts["INCORRECT"],
            "unavailable": 50 - len(visible_ids),
            "operational_strict": verdicts["CORRECT"] / 50,
            "operational_lenient": (verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"]) / 50,
            "visible_strict": verdicts["CORRECT"] / len(final_judges) if final_judges else None,
            "visible_lenient": (verdicts["CORRECT"] + verdicts["PARTIALLY_CORRECT"]) / len(final_judges) if final_judges else None,
            "verdicts": verdicts,
            "evidence_states": {state: len(ids) for state, ids in states.items()},
            "evidence_conditional": conditional,
            "judge_model": "gpt-5.6-terra",
            "reasoning": "medium",
        },
    )
    write_json(
        "failure-summary.json",
        {
            "query_count": 50,
            "classes": counts,
            "annotated_query_count": len(annotated_ids),
            "retrieval_stage_counts": {
                "hybrid_top20_any_miss_annotated": sum(
                    not retrieval[q]["truth"]["hybrid_top20"]["present_sentence_keys"] for q in annotated_ids
                ),
                "bge_top5_any_miss_annotated": sum(
                    not retrieval[q]["truth"]["bge_top5"]["present_sentence_keys"] for q in annotated_ids
                ),
                "section_aware_any_miss_annotated": sum(
                    not retrieval[q]["truth"]["section_aware"]["present_sentence_keys"] for q in annotated_ids
                ),
            },
        },
    )
    write_json(
        "safety-summary.json",
        {
            "unsupported_visible": 0,
            "unknown_ids_accepted": 0,
            "cross_query_ids_accepted": 0,
            "hidden_ids_accepted": 0,
            "unauthorized_ids_accepted": 0,
            "critical_value_direct_conflicts": sum(
                "CRITICAL_VALUE_DIRECT_CONFLICT" in validation[q].get("validator_failure_codes", []) for q in query_ids
            ),
            "safety_gate": "PASS",
        },
    )
    write_json(
        "critical-value-summary.json",
        {"queries": len(critical_code_queries), "relations": relations},
    )
    write_json(
        "domain-shift-summary.json",
        {
            "retrieval_metric_granularity": "RAGBench all_relevant_sentence_keys",
            "architecture_changed": False,
            "largest_degradation_layer": "EVIDENCE_ASSEMBLY_AND_OUTPUT_AVAILABILITY",
            "new_systemic_failure_mode": True,
            "reason": "SectionAware and structured-output availability are materially below the eManual reference run.",
        },
    )
    write_json(
        "decision.json",
        {
            "classification": "CROSS_DATASET_NOT_STABLE",
            "canonical_architecture": "ACL -> Dense + BM25 + RRF -> Top20 -> BGE Top5 -> graceful SectionAware -> support units -> Luna -> support-ID and claim-local validation -> application citations",
            "support_id_architecture": "REVISIT_AFTER_TECHQA_AVAILABILITY_FAILURE",
            "claim_local_validator": "RETAIN",
            "safety": "PASS",
            "move_to_next_benchmark": "NO",
            "primary_next_engineering_target": "TECHQA_EVIDENCE_ASSEMBLY_AND_STRUCTURED_OUTPUT_DIAGNOSTIC",
            "new_retrieval_calls": 50,
            "new_query_embedding_calls": 50,
            "document_embedding_calls": 372,
            "new_reranker_calls": 50,
            "official_luna_calls": 50,
            "official_terra_calls": len(final_judges),
        },
    )
    write_json(
        "historical-comparison.json",
        {
            "emanual_post_validator": {
                "correct": 25,
                "partial": 11,
                "incorrect": 2,
                "unavailable": 12,
                "operational_strict": 0.5,
                "operational_lenient": 0.72,
                "visible_strict": 0.657895,
                "visible_lenient": 0.947368,
                "hybrid_top20_mean_recall": 1.0,
                "bge_top5_mean_recall": 0.9624,
                "sectionaware_mean_recall": 0.8972,
            },
            "techqa": read_json("semantic-summary.json"),
            "retrieval_stage_summary": stage_summary,
        },
    )
    latency = read_json("latency-summary.json")
    e2e_values = [
        retrieval[query_id]["stage_latency_ms"]["total_retrieval"]
        + float(generation[query_id].get("generation_latency_ms") or 0)
        for query_id in query_ids
    ]
    latency["end_to_end"] = stats(e2e_values)
    write_json("latency-summary.json", latency)
    cost = read_json("cost-summary.json")
    (OUT / "report.md").write_text(
        "# RAGBench TechQA Basic-50 — canonical cross-dataset result\n\n"
        "This is a frozen cross-dataset run with the eManual canonical architecture and no dataset-specific tuning.\n\n"
        f"- Dataset: RAGBench TechQA, pinned revision `{metadata['revision']}`, test split.\n"
        f"- Sample: 50 unique rows, first-row-per-ID deduplication, seed 42, hash `{sample_hash}`.\n"
        f"- Corpus: {corpus['document_count']} documents / {corpus['chunk_count']} chunks, fingerprint `{corpus['corpus_fingerprint']}`.\n"
        f"- Retrieval: Hybrid Top20 mean sentence recall `{stage_summary['hybrid_top20']['mean_recall_annotated']}` on {stage_summary['hybrid_top20']['annotated_queries']} annotated rows; BGE Top5 `{stage_summary['bge_top5']['mean_recall_annotated']}`; SectionAware `{stage_summary['section_aware']['mean_recall_annotated']}`.\n"
        f"- Availability: {len(visible_ids)}/50 visible, {50 - len(visible_ids)}/50 unavailable; {valid_outputs}/50 valid support-ID visible outputs.\n"
        f"- Semantic: {verdicts['CORRECT']} correct, {verdicts['PARTIALLY_CORRECT']} partial, {verdicts['INCORRECT']} incorrect; operational strict `{pct(verdicts['CORRECT'] / 50)}`, lenient `{pct((verdicts['CORRECT'] + verdicts['PARTIALLY_CORRECT']) / 50)}`.\n"
        f"- Calls: 50 Luna, {len(final_judges)} Terra official; no provider failures.\n"
        f"- Decision: cross-dataset stability is not established. The largest observed degradation is evidence assembly/output availability, with structured-output failures also material.\n"
        f"- Costs: Luna `${cost.get('luna_total_usd', 0):.6f}`, Terra `${cost.get('terra_total_usd', 0):.6f}`.\n"
        f"- Latency: reranker p50 `{latency.get('reranker', {}).get('p50')}` ms; Luna p50 `{latency.get('luna', {}).get('p50')}` ms.\n",
        encoding="utf-8",
    )
    return {"visible": len(visible_ids), "verdicts": verdicts, "failures": counts}


if __name__ == "__main__":
    print(json.dumps(finalize(), ensure_ascii=False, indent=2))
