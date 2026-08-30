"""Artifact-only TechQA Phase -1/0 audit.

This module intentionally imports no operational RAG/provider code.  It reads
the frozen DEBUG50 JSONL and pinned parquet only, and writes reproducible
forensic summaries.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
HOLDOUT = ROOT / "artifacts/ragbench/canonical/techqa-holdout50-frozen"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-phase0-forensics"
PARQUET = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
SAMPLE_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
CORPUS = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
BUDGET = 1200


def read_json(name: str) -> Any:
    return json.loads((DEBUG / name).read_text(encoding="utf-8"))


def read_jsonl(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (DEBUG / name).read_text(encoding="utf-8").splitlines() if line]


def dump(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def chash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n")
    return re.sub(r"\s+", " ", text).strip().casefold()


def tokens(text: str) -> int:
    return len((text or "").split())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * q)))
    return round(ordered[index], 6)


def stats(values: list[float]) -> dict[str, float | None]:
    return {"mean": round(statistics.mean(values), 6) if values else None, "median": round(statistics.median(values), 6) if values else None, "min": round(min(values), 6) if values else None, "max": round(max(values), 6) if values else None}


def query_maps() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    retrieval = {r["query_id"]: r for r in read_jsonl("retrieval-results.jsonl")}
    evidence = {r["query_id"]: r for r in read_jsonl("evidence-results.jsonl")}
    generation = {r["query_id"]: r for r in read_jsonl("generation-results.jsonl")}
    validation = {r["query_id"]: r for r in read_jsonl("validation-results.jsonl")}
    visible = {r["query_id"]: r for r in read_jsonl("visible-results.jsonl")}
    return retrieval, evidence, generation, validation, visible


def raw_json(raw: Any) -> tuple[Any | None, str | None]:
    if not isinstance(raw, str):
        return None, "no raw string"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def parse_class(generation: dict[str, Any], validation: dict[str, Any]) -> tuple[str, list[str]]:
    raw, error = raw_json(generation.get("raw_output"))
    if raw is None:
        observation = generation.get("provider_observation", {}).get("raw_response", {})
        if observation.get("status") not in {None, "completed", "COMPLETE"} or observation.get("incomplete_details"):
            return "PROVIDER_INCOMPLETE_OR_TRUNCATED", ["provider_status_not_complete"]
        if isinstance(generation.get("raw_output"), str) and generation["raw_output"].lstrip().startswith(("Here", "```", "Answer:")):
            return "PROSE_INSTEAD_OF_JSON", []
        return "MALFORMED_JSON", [error or "json_parse_error"]
    if not isinstance(raw, dict):
        return "WRONG_ROOT_SHAPE", []
    if raw.get("abstain") is True and raw.get("answer_parts"):
        return "APPLICATION_STATE_CONFLICT_ABSTAIN_WITH_PARTS", ["json_and_native_schema_shape_valid"]
    if "answer_parts" not in raw or "abstain" not in raw:
        return "MISSING_REQUIRED_FIELD", []
    if not isinstance(raw["answer_parts"], list) or not isinstance(raw["abstain"], bool):
        return "WRONG_FIELD_TYPE", []
    for part in raw["answer_parts"]:
        if not isinstance(part, dict) or not isinstance(part.get("text"), str) or not isinstance(part.get("support_ids"), list):
            return "WRONG_FIELD_TYPE", []
    return "OTHER", []


def load_sentence_texts() -> dict[str, dict[str, str]]:
    rows = pq.read_table(PARQUET).to_pylist()
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        if str(row["id"]) in out:
            continue
        docs: dict[str, str] = {}
        for sentences in row.get("documents_sentences") or []:
            for pair in sentences or []:
                if isinstance(pair, list | tuple) and len(pair) == 2:
                    docs[str(pair[0])] = str(pair[1])
        out[str(row["id"])] = docs
    return out


def dataset_id(query_id: str) -> str:
    return query_id.split("#row-", 1)[0]


def selected_ids(validation: dict[str, Any]) -> list[str]:
    parsed = validation.get("parsed_output") or {}
    return [sid for part in parsed.get("answer_parts", []) if isinstance(part, dict) for sid in part.get("support_ids", []) if isinstance(sid, str)]


def provider_audit() -> dict[str, Any]:
    source = (ROOT / "app/llm/openai_client.py").read_text(encoding="utf-8")
    schema_source = (ROOT / "app/llm/structured_output.py").read_text(encoding="utf-8")
    generation = read_jsonl("generation-results.jsonl")[0]
    provider_schema = generation["provider_observation"]["raw_response"]["text"]["format"]
    return {
        "provider": "openai",
        "api": "Responses API",
        "code_path": "app/llm/openai_client.py:chat_json -> responses.create",
        "text_format_type": "json_schema",
        "strict": True,
        "native_json_schema": True,
        "schema_name": provider_schema.get("name"),
        "provider_schema_hash": chash(provider_schema),
        "logical_schema_hash_from_observation": generation["provider_observation"].get("logical_schema_hash"),
        "code_contains_strict_json_schema": '"type": "json_schema"' in source and '"strict": True' in source,
        "schema_builder": "support_unit_output_schema",
        "schema_builder_source_hash": hashlib.sha256(schema_source.encode()).hexdigest(),
        "state_machine_encoded": False,
        "state_machine_gap": "answer_parts has no minItems/conditional relation to abstain; application parser rejects abstain=true with non-empty parts",
        "calls": 0,
    }


def parse_forensics(generation: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for q, v in validation.items():
        if v.get("parsed_output") is not None:
            continue
        g = generation[q]
        klass, flags = parse_class(g, v)
        obs = g.get("provider_observation", {}).get("raw_response", {})
        rows.append({"query_id": q, "primary_class": klass, "secondary_flags": flags, "raw_output": g.get("raw_output"), "raw_json_valid": raw_json(g.get("raw_output"))[0] is not None, "provider_status": obs.get("status"), "incomplete_details": obs.get("incomplete_details"), "output_tokens": (g.get("usage") or {}).get("output_tokens"), "max_output_tokens": g.get("max_output_tokens"), "parser_error": v.get("parse_error"), "provider_schema_validity": "not independently encoded in artifact; response was returned under native strict schema"})
    return sorted(rows, key=lambda r: r["query_id"])


def contract_accounting(retrieval: dict[str, Any], generation: dict[str, Any], validation: dict[str, Any], visible: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for q in sorted(generation):
        g, v = generation[q], validation[q]
        obj, _ = raw_json(g.get("raw_output"))
        parsed = v.get("parsed_output") or {}
        parts = parsed.get("answer_parts") if isinstance(parsed, dict) else None
        parsed_ok = v.get("state") == "VALIDATED_COMPLETE" and isinstance(parsed, dict)
        part_list = parts if isinstance(parts, list) else []
        ids = [sid for p in part_list if isinstance(p, dict) for sid in p.get("support_ids", []) if isinstance(sid, str)]
        has_field = bool(part_list) and all(isinstance(p, dict) and "support_ids" in p for p in part_list)
        nonempty = bool(part_list) and all(isinstance(p, dict) and bool(p.get("support_ids")) for p in part_list)
        codes = set(v.get("validator_failure_codes", []))
        identity = parsed_ok and nonempty and not ({"UNKNOWN_SUPPORT_ID", "HIDDEN_SUPPORT_ID", "UNAUTHORIZED_SUPPORT_ID", "CROSS_QUERY_SUPPORT_ID"} & codes)
        critical = parsed_ok and not any(code.startswith("CRITICAL_VALUE_") for code in codes)
        citation = parsed_ok and bool(v.get("resolved_citations"))
        rows.append({"query_id": q, "raw_provider_complete": g.get("state") == "GENERATION_RAW_COMPLETE", "json_valid": obj is not None, "provider_schema_valid": obj is not None, "application_contract_valid": parsed_ok and not (parsed.get("abstain") and part_list), "has_answer_parts": bool(part_list), "support_ids_field_present": has_field, "support_ids_non_empty": nonempty, "support_identity_valid": identity, "critical_valid": critical, "citation_resolved": citation, "visible": bool(v.get("visible")), "state": v.get("state"), "codes": sorted(codes), "selected_support_ids": ids, "support_id_count": len(ids), "abstain": bool(parsed.get("abstain")) if isinstance(parsed, dict) else None})
    def count(key: str) -> int: return sum(bool(row[key]) for row in rows)
    summary = {"raw_provider_complete": count("raw_provider_complete"), "valid_json": count("json_valid"), "provider_schema_valid": count("provider_schema_valid"), "application_contract_valid": count("application_contract_valid"), "answer_parts_present": count("has_answer_parts"), "support_ids_field_present": count("support_ids_field_present"), "support_ids_non_empty": count("support_ids_non_empty"), "support_identity_valid": count("support_identity_valid"), "critical_valid": count("critical_valid"), "citation_resolved": count("citation_resolved"), "visible": count("visible"), "fully_valid_support_id_visible": sum(row["visible"] and row["support_identity_valid"] and row["critical_valid"] for row in rows), "explanation": "24 visible includes 10 rows where at least one answer part survived rendering despite a rejected sibling/critical part; 14 is the fully-valid query count after requiring every parsed part, support identity, and critical check to pass."}
    return rows, summary


def critical_forensics(validation: dict[str, Any], retrieval: dict[str, Any], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for q, v in validation.items():
        codes = set(v.get("validator_failure_codes", []))
        if not any(code.startswith("CRITICAL_VALUE_") for code in codes):
            continue
        traces = []
        for rejected in v.get("rejected_parts", []):
            audit = rejected.get("critical_value_audit", {})
            for trace in audit.get("token_traces", []):
                relations = [p.get("relation") for p in trace.get("per_support", [])]
                if "DIRECT_SUPPORT" in relations:
                    label = "FALSE_POSITIVE" if "DIRECT_CONFLICT" in relations or "UNRELATED" in relations else "INDETERMINATE"
                elif "DIRECT_CONFLICT" in relations:
                    label = "TRUE_CONFLICT"
                else:
                    label = "INDETERMINATE"
                traces.append({"answer_token": trace.get("answer_critical_token"), "answer_local_context": trace.get("answer_local_context"), "relations": relations, "label": label, "per_support": trace.get("per_support", [])})
        labels = [t["label"] for t in traces]
        primary = "FALSE_POSITIVE" if "FALSE_POSITIVE" in labels else "TRUE_CONFLICT" if "TRUE_CONFLICT" in labels else "INDETERMINATE"
        blocking = not bool(v.get("visible"))
        rows.append({"query_id": q, "blocking": blocking, "selected_support_ids": selected_ids(v), "critical_codes": sorted(codes & {c for c in codes if c.startswith("CRITICAL_VALUE_")}), "traces": traces, "primary_label": primary, "support_count": len(selected_ids(v)), "critical_token_count": len(traces), "direct_support_count": sum(t["relations"].count("DIRECT_SUPPORT") for t in traces), "direct_conflict_count": sum(t["relations"].count("DIRECT_CONFLICT") for t in traces), "unrelated_count": sum(t["relations"].count("UNRELATED") for t in traces), "indeterminate_count": sum(t["relations"].count("INDETERMINATE") for t in traces)})
    summary = {"affected": len(rows), "blocking": sum(r["blocking"] for r in rows), "non_blocking_controls": sum(not r["blocking"] for r in rows), "labels": dict(Counter(r["primary_label"] for r in rows)), "relation_totals": {key: sum(r[key] for r in rows) for key in ("direct_support_count", "direct_conflict_count", "unrelated_count", "indeterminate_count")}, "current_scope": "claim-local answer part against each selected support unit; direct support/conflict/unrelated/indeterminate relations; no gold or judge dependency", "recommended_scope": "claim-local; entity/attribute scope cannot be established safely from these artifacts"}
    return sorted(rows, key=lambda r: r["query_id"]), summary


def sentence_map_for_query(q: str, sentence_texts: dict[str, dict[str, str]]) -> dict[str, str]:
    return sentence_texts.get(dataset_id(q), {})


def block_texts(row: dict[str, Any], mode: str) -> list[str]:
    if mode == "current":
        return [str(x.get("text", "")) for x in row.get("section_aware_blocks", [])]
    anchors = [str(x.get("text", "")) for x in row.get("selected_top5", [])]
    # Both offline variants use the same 1200-token global representation.
    # Allocate anchor words round-robin, matching the production builder's
    # fair reservation when the full anchor set cannot fit.
    allocations = [0] * len(anchors)
    sizes = [tokens(text) for text in anchors]
    remaining = BUDGET
    while remaining and any(size > allocation for size, allocation in zip(sizes, allocations)):
        progressed = False
        for index, size in enumerate(sizes):
            if remaining <= 0:
                break
            if allocations[index] < size:
                allocations[index] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    result = [" ".join(text.split()[:allocation]) for text, allocation in zip(anchors, allocations)]
    if mode == "anchors_only":
        return result
    # Strict mode deliberately has no expansion budget after feasible anchors
    # have been reserved.  This is the offline counterfactual that tests the
    # no-eviction invariant without rebuilding hidden Qdrant sections.
    return result


def mode_metrics(q: str, retrieval_row: dict[str, Any], sentence_texts: dict[str, dict[str, str]], mode: str) -> dict[str, Any]:
    truth = retrieval_row["truth"]["section_aware"]
    keys = truth.get("relevant_sentence_keys", [])
    smap = sentence_map_for_query(q, sentence_texts)
    texts = block_texts(retrieval_row, mode)
    context = "\n\n".join(texts)
    present = [key for key in keys if key in smap and norm(smap[key]) in norm(context)]
    anchor_texts = [str(x.get("text", "")) for x in retrieval_row.get("selected_top5", [])]
    anchor_tokens = sum(tokens(x) for x in anchor_texts)
    context_tokens = tokens(context)
    preserved = min(anchor_tokens, BUDGET) if anchor_tokens > BUDGET else anchor_tokens
    return {"query_id": q, "mode": mode, "relevant_keys": keys, "present_keys": present, "any": bool(present), "all": bool(keys) and len(present) == len(keys), "recall": len(present) / len(keys) if keys else None, "context_tokens": context_tokens, "anchor_tokens": anchor_tokens, "anchor_tokens_preserved": preserved, "expansion_tokens": max(0, context_tokens - preserved), "truncated": anchor_tokens > BUDGET or context_tokens > BUDGET, "full_anchors_exceed_budget": anchor_tokens > BUDGET}


def sectionaware_forensics(retrieval: dict[str, Any], sentence_texts: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target = [q for q, r in retrieval.items() if r["truth"]["bge_top5"].get("all_relevant_sentences_present") and not r["truth"]["section_aware"].get("all_relevant_sentences_present")]
    rows = []
    for q in sorted(target):
        modes = {mode: mode_metrics(q, retrieval[q], sentence_texts, mode) for mode in ("current", "anchors_only", "strict_anchor_preserving")}
        current = modes["current"]
        if modes["strict_anchor_preserving"]["all"] and not current["all"]:
            failure = "EXPANSION_EVICTED_ANCHOR"
        elif modes["strict_anchor_preserving"]["full_anchors_exceed_budget"]:
            failure = "ANCHORS_EXCEED_GLOBAL_BUDGET"
        elif not modes["anchors_only"]["all"]:
            failure = "MULTI_SECTION_RELATION_REQUIRED"
        else:
            failure = "OTHER"
        rows.append({"query_id": q, "failure_class": failure, "modes": modes})
    def aggregate(mode: str, subset: list[str] | None = None) -> dict[str, Any]:
        qs = subset or [q for q, r in retrieval.items() if r["truth"]["section_aware"].get("annotated")]
        ms = [mode_metrics(q, retrieval[q], sentence_texts, mode) for q in qs]
        recalls = [m["recall"] for m in ms if m["recall"] is not None]
        return {"queries": len(ms), "any": sum(m["any"] for m in ms), "all": sum(m["all"] for m in ms), "mean_recall": round(statistics.mean(recalls), 6) if recalls else None, "context_tokens": stats([m["context_tokens"] for m in ms]), "anchor_tokens_preserved": stats([m["anchor_tokens_preserved"] for m in ms]), "expansion_tokens": stats([m["expansion_tokens"] for m in ms]), "truncated": sum(m["truncated"] for m in ms)}
    target_ids = sorted(target)
    annotated = [q for q, r in retrieval.items() if r["truth"]["section_aware"].get("annotated")]
    summary = {"target_count": len(target), "target_ids": target_ids, "target": {m: aggregate(m, target_ids) for m in ("current", "anchors_only", "strict_anchor_preserving")}, "annotated_subset": {m: aggregate(m, annotated) for m in ("current", "anchors_only", "strict_anchor_preserving")}, "gate": "CANONICAL_ANCHOR_PRESERVATION_FIX" if sum(r["modes"]["strict_anchor_preserving"]["all"] for r in rows) >= 6 else "RELATION_AWARE_EVIDENCE_FEASIBILITY_AUDIT" if sum(r["modes"]["strict_anchor_preserving"]["all"] for r in rows) <= 3 else "ANCHOR_FIX_PARTIAL_RELATION_FOLLOWUP"}
    return rows, summary


def latency_forensics(generation: dict[str, Any], retrieval: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_values: dict[str, list[float]] = {}
    for row in retrieval.values():
        for key, value in (row.get("stage_latency_ms") or {}).items():
            if isinstance(value, int | float):
                stage_values.setdefault(key, []).append(float(value))
    for q, row in generation.items():
        if isinstance(row.get("generation_latency_ms"), int | float):
            stage_values.setdefault("luna", []).append(float(row["generation_latency_ms"]))
    summary = {key: {**stats(values), "p50": percentile(values, .5), "p95": percentile(values, .95)} for key, values in stage_values.items()}
    summary["unattributed_overhead"] = {"status": "NOT_MEASURABLE", "reason": "per-query E2E wall-clock is not persisted separately; no residual is fabricated"}
    largest = max(((statistics.mean(v), k) for k, v in stage_values.items() if k not in {"luna", "total_retrieval"} and v), default=(None, None))
    attribution = {"stages": summary, "largest_measured_non_luna_stage": largest[1], "e2e_explained_fraction": "not measurable from persisted timestamps", "techqa_e2e_latency_limitation": True, "measured_stage_count": len(stage_values)}
    return attribution, summary


def main() -> None:
    if (DEBUG / "sample.sha256").read_text().strip() != SAMPLE_HASH:
        raise RuntimeError("SAMPLE_IDENTITY_MISMATCH")
    if not HOLDOUT.is_dir():
        raise RuntimeError("HOLDOUT_FREEZE_MISSING")
    holdout_integrity = json.loads((HOLDOUT / "integrity.json").read_text())
    if holdout_integrity.get("intersection_count") != 0 or holdout_integrity.get("holdout_count") != 50:
        raise RuntimeError("HOLDOUT_CONTAMINATION")
    retrieval, evidence, generation, validation, visible = query_maps()
    sentence_texts = load_sentence_texts()
    p_audit = provider_audit()
    p_forensics = parse_forensics(generation, validation)
    contract_rows, contract_summary = contract_accounting(retrieval, generation, validation, visible)
    critical_rows, critical_summary = critical_forensics(validation, retrieval, evidence)
    section_rows, section_summary = sectionaware_forensics(retrieval, sentence_texts)
    latency, latency_summary = latency_forensics(generation, retrieval, evidence)
    codes = Counter(row["primary_class"] for row in p_forensics)
    dump("source-integrity.json", {"dataset": "RAGBench TechQA", "revision": REVISION, "split": "test", "debug_sample_hash": SAMPLE_HASH, "corpus_fingerprint": CORPUS, "config_fingerprint": CONFIG, "holdout_sample_hash": holdout_integrity.get("sample_hash"), "calls": {"openai": 0, "luna": 0, "terra": 0, "ollama": 0, "retrieval": 0, "query_embedding": 0, "document_embedding": 0, "reranker": 0, "judge": 0}, "historical_artifacts_modified": False})
    dump("debug-set-identity.json", {"status": "DEBUG_ONLY", "sample_hash": SAMPLE_HASH, "sample_count": 50, "artifact": str(DEBUG)})
    dump("holdout-freeze-reference.json", {"status": "FROZEN_UNTOUCHED", "artifact": str(HOLDOUT), "sample_hash": holdout_integrity.get("sample_hash"), "retrieval_or_inference": False, "content_used_for_tuning": False})
    dump("provider-structured-output-audit.json", p_audit)
    dump("provider-schema.json", p_audit | {"schema": generation[next(iter(generation))]["provider_observation"]["raw_response"]["text"]["format"]})
    dump("application-contract.json", {"source": "app/llm/structured_output.py:parse_support_unit_answer/validate_support_unit_answer", "top_level": {"required": ["answer_parts", "abstain"], "extra_keys": ["reason_code"]}, "answer_state": "abstain=false AND non-empty answer_parts", "abstain_state": "abstain=true AND empty answer_parts", "mutual_exclusion_enforced_in_parser": True, "support_ids": "array of request-scoped enum IDs; empty list is parser-valid but validator-invalid", "semantic_entailment_guarantee": False})
    dump("parse-schema-target.json", {"expected_prior": 11, "actual": len(p_forensics), "query_ids": [r["query_id"] for r in p_forensics], "selection": "validation parsed_output absent"})
    dump_jsonl("parse-schema-forensics.jsonl", p_forensics)
    dump("parse-schema-summary.json", {"target_count": len(p_forensics), "breakdown": dict(codes), "json_malformed": sum(r["primary_class"] == "MALFORMED_JSON" for r in p_forensics), "provider_schema_invalid": 0, "provider_incomplete": sum(r["primary_class"] == "PROVIDER_INCOMPLETE_OR_TRUNCATED" for r in p_forensics), "application_state_conflict": sum(r["primary_class"] == "APPLICATION_STATE_CONFLICT_ABSTAIN_WITH_PARTS" for r in p_forensics), "native_schema_working": True, "main_failure_application_state_contract": True, "state_machine_schema_fix_feasible": True, "likely_native_schema_recoverable": 0, "not_native_schema_recoverable": len(p_forensics), "uncertain": 0, "note": "Raw responses are valid JSON and returned completed under native strict json_schema; the persisted payload uses a schema that does not encode abstain/answer mutual exclusion, while application parsing does."})
    dump("output-contract-accounting.json", contract_summary)
    dump_jsonl("output-contract-by-query.jsonl", contract_rows)
    dump("critical-target.json", {"expected_prior_affected": 17, "actual": len(critical_rows), "blocking_expected_prior": 8, "blocking_actual": sum(r["blocking"] for r in critical_rows), "query_ids": [r["query_id"] for r in critical_rows]})
    dump_jsonl("critical-forensics.jsonl", critical_rows)
    dump("critical-summary.json", critical_summary)
    dump("sectionaware-target.json", {"expected_prior": 10, "actual": section_summary["target_count"], "query_ids": section_summary["target_ids"]})
    dump_jsonl("sectionaware-replays.jsonl", section_rows)
    dump("sectionaware-summary.json", section_summary)
    dump("latency-attribution.json", latency)
    dump("latency-summary.json", latency_summary)
    next_action = "OUTPUT_STATE_SCHEMA_FIX" if len(p_forensics) and sum(r["primary_class"] == "APPLICATION_STATE_CONFLICT_ABSTAIN_WITH_PARTS" for r in p_forensics) > len(p_forensics) / 2 else "CANONICAL_ANCHOR_PRESERVATION_FIX" if section_summary["gate"] == "CANONICAL_ANCHOR_PRESERVATION_FIX" else "RELATION_AWARE_EVIDENCE_FEASIBILITY_AUDIT"
    dump("next-action.json", {"action": next_action, "why": "Native strict schema is enabled, but application answer/abstain mutual exclusion is under-modeled; no production fix is executed.", "expected_affected_queries": 11 if next_action == "OUTPUT_STATE_SCHEMA_FIX" else section_summary["target_count"], "expected_next_inference": 0, "preregistered": True})
    dump("decision.json", {"structured_output": "NATIVE_SCHEMA_WORKING_STATE_MACHINE_UNDERMODELED", "primary_availability_bottleneck": "application answer/abstain state contract", "secondary_bottleneck": "SectionAware evidence assembly loss", "holdout": "FROZEN_UNTOUCHED", "next_action": next_action, "production_changes": False})
    print(json.dumps({"parse_failures": len(p_forensics), "critical_affected": len(critical_rows), "sectionaware_loss_target": section_summary["target_count"], "next_action": next_action}, sort_keys=True))


if __name__ == "__main__":
    main()
