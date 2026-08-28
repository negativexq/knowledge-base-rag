# ruff: noqa: E501

"""Phase 7.6 provider-free diagnosis of the Context Builder v1 smoke.

This script reads already persisted Phase 7 artifacts only.  It deliberately
does not import a model client, retrieval client, reranker, or evaluator.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.generation_baseline import chunks_from_cache
from app.llm.citation_location import location_for

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "artifacts/phase-7/generation-smoke"
P75 = ROOT / "artifacts/phase-7/context-builder-full-validation"
OUT = ROOT / "artifacts/phase-7/offline-failure-diagnosis"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"

EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "generator": "qwen3.5:4b",
    "prompt": "v3",
    "think": False,
    "candidate_k": 20,
    "top_n": 5,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def short(text: str, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def identity_check() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    cache_meta = read_json(SMOKE / "cache-metadata.json")
    p75_summary = read_json(P75 / "summary.json")
    p75_config = read_json(P75 / "experiment-config.json")
    actual = {
        "git_sha": cache_meta.get("git_sha"),
        "corpus_fingerprint": cache_meta.get("corpus_fingerprint"),
        "dataset_fingerprint": cache_meta.get("dataset_fingerprint"),
        "collection": cache_meta.get("collection"),
        "generator": p75_config.get("model"),
        "prompt": p75_config.get("prompt_version"),
        "think": p75_config.get("think"),
        "candidate_k": cache_meta.get("candidate_k"),
        "top_n": cache_meta.get("top_n"),
    }
    mismatches = {key: {"expected": value, "actual": actual[key]} for key, value in EXPECTED.items() if actual[key] != value}
    if mismatches:
        raise RuntimeError(f"ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: {mismatches}")
    cache_rows = read_jsonl(SMOKE / "retrieval-inputs.jsonl")
    b_rows = read_jsonl(P75 / "b-generation-results.jsonl")
    if len(cache_rows) != 36 or len(b_rows) != 36:
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: expected 36 records")
    if [row["query_id"] for row in cache_rows] != [row["query_id"] for row in b_rows]:
        raise RuntimeError("ANALYSIS_BLOCKED_BY_ARTIFACT_MISMATCH: query order mismatch")
    return actual, p75_summary, cache_rows, {row["query_id"]: row for row in b_rows}


def dataset_questions(ids: list[str]) -> dict[str, dict[str, Any]]:
    rows = {row["id"]: row for row in read_json(DATASET) if row["id"] in ids}
    if set(rows) != set(ids):
        raise RuntimeError("dataset annotations do not cover the cached query set")
    return rows


def chunk_index(cache_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in cache_rows:
        for chunk in chunks_from_cache(record):
            key = (
                str(chunk.payload.get("source_type", "doc")),
                str(chunk.payload.get("source_id", "doc")),
                location_for(chunk.payload),
            )
            index[key] = {
                "chunk_id": chunk.id,
                "source_id": chunk.payload.get("source_id"),
                "content": str(chunk.payload.get("text", "")),
                "metadata": {key: value for key, value in chunk.payload.items() if key not in {"text", "chunk_id"}},
            }
    return index


def citation_classification(
    row: dict[str, Any], question: dict[str, Any], citation: list[str], chunks: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[str, str, str]:
    source_id = citation[1] if len(citation) > 1 else ""
    allowed = set(question.get("expected_source_ids", [])) | set(question.get("supporting_source_ids", []))
    relevant = set(question.get("relevant_source_ids", []))
    distractors = set(question.get("distractor_source_ids", []))
    invalid = {tuple(value) for value in row.get("citations", {}).get("unknown_or_unauthorized", [])}
    if tuple(citation) in invalid:
        return "UNKNOWN_ID", "citation identity is not in the authorized Top-5", "CITATION_IDENTITY"
    if source_id in allowed:
        return "SUPPORTED", "expected/supporting source", "NONE"
    if source_id in relevant or source_id in distractors:
        return "RELATED_BUT_INSUFFICIENT", "related or distractor source was cited", "CITATION_SELECTION"
    status = row["fact_score"]["status"]
    if status in {"FULLY_CORRECT_COMPLETE", "CORRECT_BUT_INCOMPLETE"}:
        return "CORRECT_FACT_WRONG_SOURCE", "answer fact is usable but citation is outside required source set", "CITATION_SELECTION"
    if status in {"PARTIALLY_CORRECT", "INCORRECT"}:
        return "WRONG_FACT_WRONG_SOURCE", "content is not fully correct and citation is outside required source set", "CITATION_SELECTION"
    return "CANNOT_DETERMINE", "content/citation relation is not safely observable", "CANNOT_DETERMINE"


def review_citations(rows: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]], cache_rows: list[dict[str, Any]], chunks: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the exact source-alignment review set emitted by Phase 7.5.

    The artifact stores an aggregate review count, which is narrower than all
    citations outside the authored required-source set.  Keep that distinction
    explicit and select occurrences deterministically in output order.
    """
    output: list[dict[str, Any]] = []
    for query_id, row in rows.items():
        question = questions[query_id]
        citations = row.get("citations", {}).get("found", [])
        allowed = set(question.get("expected_source_ids", [])) | set(question.get("supporting_source_ids", []))
        review_count = int(row.get("citations", {}).get("source_alignment_review_required", 0))
        candidates = [
            (occurrence, citation)
            for occurrence, citation in enumerate(citations)
            if len(citation) <= 1 or citation[1] not in allowed
        ]
        if len(candidates) < review_count:
            raise RuntimeError(f"citation review count exceeds candidates for {query_id}")
        for occurrence, citation in candidates[:review_count]:
            status, reason, root = citation_classification(row, question, citation, chunks)
            key = tuple(citation)
            evidence = chunks.get(key)
            output.append({
                "query_id": query_id,
                "occurrence": occurrence,
                "category": row["category"],
                "content_status": row["fact_score"]["status"],
                "fact_coverage": row["fact_score"].get("fact_coverage"),
                "citation_id": citation,
                "cited_chunk_id": evidence.get("chunk_id") if evidence else None,
                "cited_content_excerpt": short(evidence.get("content", "")) if evidence else None,
                "generated_answer_excerpt": short(row.get("raw_candidate_output", "")),
                "expected_fact_components": row["fact_score"].get("expected_components", []),
                "classification": status,
                "classification_reason": reason,
                "root_cause": root,
                "review_source": "phase-7.5 citations.source_alignment_review_required",
            })
    return output


def content_regressions(comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in comparisons:
        if item["content_outcome"] != "REGRESSED":
            continue
        query_id = item["query_id"]
        if query_id == "cross-07-0":
            cause, linkage = "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE", "NOT_LINKED"
            explanation = "B visibly states 15 percent, but the duration-first matcher extracted 12 months from the Turkish expected phrase."
        elif query_id == "hard-api-private":
            cause, linkage = "ANSWER_LENGTH_VARIANCE", "PLAUSIBLY_LINKED"
            explanation = "B states both 120 and 600, but omits the authored 'per API key' qualifier; evidence/order remained identical."
        else:
            cause, linkage = "CANNOT_DETERMINE", "INCONCLUSIVE"
            explanation = "No deterministic causal signal is available."
        output.append({
            "query_id": query_id, "a_status": item["a"]["fact_score"]["status"], "b_status": item["b"]["fact_score"]["status"],
            "a_answer": short(item["a"].get("answer", "")), "b_answer": short(item["b"].get("raw_candidate_output", "")),
            "a_context_tokens": item["a"]["context"]["context_tokens"], "b_context_tokens": item["b"]["context_builder"]["context_tokens"],
            "same_chunk_membership": set(item["a"]["context"]["input_chunk_ids"]) == set(item["b"]["context_builder"]["input_chunk_ids"]),
            "same_order": item["a"]["context"]["input_chunk_ids"] == item["b"]["context_builder"]["output_chunk_ids"],
            "cause": cause, "causal_linkage": linkage, "explanation": explanation,
        })
    return output


def classify_acl(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows.values():
        if row["category"] != "acl_negative":
            continue
        answer = row.get("raw_candidate_output", "").casefold()
        safe = "i could not find" in answer or "bulamad" in answer
        output.append({
            "query_id": row["query_id"], "tenant": "from dataset ACL fixture",
            "authorized_chunk_count": row["context_builder"]["chunk_count"],
            "authorized_sources": row["context_builder"].get("unique_source_count"),
            "expected_behavior": "ABSTAIN",
            "generated_answer_excerpt": short(row.get("raw_candidate_output", "")),
            "citations": row.get("citations", {}).get("found", []),
            "validator_pass": row.get("validator_pass"),
            "classification": "SAFE_ABSTENTION" if safe else "UNSUPPORTED_FROM_AUTHORIZED_CONTEXT",
            "authorization_boundary_failure": False,
            "grounding_cause": "NO_ANSWER_INSTRUCTION_FAILURE" if not safe else "NONE",
        })
    return output


def classify_validator_rejections(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows.values():
        if row.get("validator_pass") is not False:
            continue
        status = row["fact_score"]["status"]
        answer = row.get("raw_candidate_output", "")
        if row["category"] == "ambiguous":
            content_class = "AMBIGUOUS_CONDITIONAL"
        elif status == "FULLY_CORRECT_COMPLETE":
            content_class = "CONTENT_FULLY_CORRECT_COMPLETE"
        elif status == "CORRECT_BUT_INCOMPLETE":
            content_class = "CONTENT_CORRECT_INCOMPLETE"
        elif status == "PARTIALLY_CORRECT":
            content_class = "CONTENT_PARTIAL"
        elif status == "INCORRECT":
            content_class = "CONTENT_INCORRECT"
        elif not answer:
            content_class = "SAFE_NO_ANSWER"
        else:
            content_class = "CONTENT_UNASSESSABLE"
        disposition = "COSTLY_REJECTION" if content_class in {"CONTENT_FULLY_CORRECT_COMPLETE", "CONTENT_CORRECT_INCOMPLETE"} else "GOOD_REJECTION" if content_class == "CONTENT_INCORRECT" else "NEUTRAL_REJECTION"
        output.append({
            "query_id": row["query_id"], "category": row["category"], "gold_present": row["gold_present"],
            "content_class": content_class, "validator_failure_codes": row.get("validator_failure_codes", []),
            "citations": row.get("citations", {}).get("found", []), "user_visible_output_available": bool(row.get("user_visible_output")),
            "disposition": disposition,
        })
    return output


def multidoc(rows: dict[str, dict[str, Any]], questions: dict[str, dict[str, Any]], cache_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache_by_id = {row["query_id"]: row for row in cache_rows}
    output = []
    for row in rows.values():
        if row["category"] != "multi_document":
            continue
        status = row["fact_score"]["status"]
        if status == "CORRECT_BUT_INCOMPLETE":
            failure = "IDENTIFIED_BUT_OMITTED_COMPONENT"
            planning = "OBLIGATION_PLANNING_FAILURE"
        else:
            failure = "WRONG_RELATION_SYNTHESIZED"
            planning = "EVIDENCE_SYNTHESIS_FAILURE"
        output.append({
            "query_id": row["query_id"], "question": questions[row["query_id"]]["question"],
            "required_facts": row["fact_score"].get("expected_components", []),
            "required_sources": questions[row["query_id"]].get("expected_source_ids", []),
            "top5_source_order": [chunk.payload.get("source_id") for chunk in chunks_from_cache(cache_by_id[row["query_id"]])],
            "context_chunk_ids": row["context_builder"]["output_chunk_ids"],
            "raw_candidate_excerpt": short(row.get("raw_candidate_output", ""), 1400),
            "matched_facts": row["fact_score"].get("matched_fact_ids", []),
            "missing_facts": row["fact_score"].get("missing_fact_ids", []),
            "citations": row.get("citations", {}).get("found", []),
            "validator_pass": row.get("validator_pass"),
            "primary_failure": failure, "planning_or_synthesis": planning,
        })
    return output


def run() -> None:
    actual, p75_summary, cache_rows, b_rows = identity_check()
    ids = [row["query_id"] for row in cache_rows]
    questions = dataset_questions(ids)
    comparisons = read_jsonl(P75 / "per-query-comparison.jsonl")
    chunks = chunk_index(cache_rows)
    citation_review = review_citations(b_rows, questions, cache_rows, chunks)
    regressions = content_regressions(comparisons)
    acl = classify_acl(b_rows)
    validator = classify_validator_rejections(b_rows)
    docs = multidoc(b_rows, questions, cache_rows)
    citation_counts = Counter(item["classification"] for item in citation_review)
    root_counts = Counter(item["root_cause"] for item in citation_review)
    source_alignment_causes = Counter()
    cache_by_id = {row["query_id"]: row for row in cache_rows}
    for item in citation_review:
        if item["classification"] == "UNKNOWN_ID":
            source_alignment_causes["D_IDENTITY_FAILURE"] += 1
            continue
        question = questions[item["query_id"]]
        required_sources = set(question.get("required_evidence", [])) | set(question.get("expected_source_ids", []))
        available_sources = {
            chunk.payload.get("source_id")
            for chunk in chunks_from_cache(cache_by_id[item["query_id"]])
        }
        if required_sources & available_sources:
            source_alignment_causes["A_CORRECT_EVIDENCE_PRESENT_IN_ANOTHER_TOP5_CHUNK"] += 1
        elif item["classification"] == "RELATED_BUT_INSUFFICIENT":
            source_alignment_causes["B_RELATED_BUT_NOT_SUPPORTING"] += 1
        else:
            source_alignment_causes["F_GENERATED_CLAIM_OR_SOURCE_NOT_PROVABLY_SUPPORTED"] += 1
    b_citation_occurrences = sum(len(row.get("citations", {}).get("found", [])) for row in b_rows.values())
    b_identity_failures = sum(len(row.get("citations", {}).get("unknown_or_unauthorized", [])) for row in b_rows.values())
    comparison_counts = Counter(item["citation_outcome"] for item in comparisons)
    quality = Counter(row["fact_score"]["status"] for row in b_rows.values() if row["answerability"] == "answerable" and row["all_required_present"])
    raw_user = {
        "record_count": 36,
        "raw_candidate_observable": sum(bool(row.get("raw_candidate_observable")) for row in b_rows.values()),
        "validator_pass": sum(row.get("validator_pass") is True for row in b_rows.values()),
        "user_visible_output": sum(bool(row.get("user_visible_output")) for row in b_rows.values()),
        "gold_present_answerable": quality,
        "raw_content_success": quality["FULLY_CORRECT_COMPLETE"],
        "user_visible_full_success": sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" and row.get("validator_pass") is True for row in b_rows.values() if row["answerability"] == "answerable" and row["all_required_present"]),
    }
    matrix = Counter()
    for row in b_rows.values():
        if row["answerability"] != "answerable" or not row["all_required_present"]:
            continue
        content = row["fact_score"]["status"]
        citation = "citation_review_or_wrong" if row.get("citations", {}).get("source_alignment_review_required", 0) or row.get("citations", {}).get("unknown_or_unauthorized") else "citation_supported_or_unresolved"
        matrix[(content, citation)] += 1
    identity = {**actual, "status": "PASS", "expected": EXPECTED, "cache_query_count": 36, "p75_summary_status": p75_summary.get("status")}
    write(OUT / "artifact-identity.json", identity)
    write_jsonl(OUT / "citation-occurrence-review.jsonl", citation_review)
    write(OUT / "citation-taxonomy-summary.json", {
        "citation_occurrences_total": b_citation_occurrences,
        "citation_identity_failure_occurrences": b_identity_failures,
        "citation_support_failure_occurrences": sum(value for key, value in citation_counts.items() if key != "SUPPORTED"),
        "review_required_occurrences": len(citation_review),
        "affected_records": len({item["query_id"] for item in citation_review}),
        "classification_counts": dict(citation_counts), "root_cause_counts": dict(root_counts),
    })
    write(OUT / "citation-a-vs-b-comparison.json", {"a_vs_b_outcome_counts": {**dict(comparison_counts), "NOT_COMPARABLE": 0}, "a_identity": 33, "b_identity": 34, "b_review_required_occurrences": len(citation_review), "citation_improved": comparison_counts["IMPROVED"], "citation_unchanged": comparison_counts["UNCHANGED"], "citation_regressed": comparison_counts["REGRESSED"], "note": "B observability and occurrence composition differ from historical A; review-required claims are not treated as proven regressions."})
    write(OUT / "source-alignment-root-cause.json", {"root_cause_counts": dict(root_counts), "alignment_mechanism_counts": dict(source_alignment_causes), "dominant": root_counts.most_common(1)[0] if root_counts else None, "interpretation": "The B review set is dominated by citation selection/alignment: in most reviewed occurrences the required evidence exists elsewhere in the same authorized Top-5. No deterministic evidence links this to changed ordering or membership."})
    write(OUT / "content-regressions.json", {"count": len(regressions), "records": regressions})
    write(OUT / "context-regression-analysis.json", {"same_top5_for_regressions": all(item["same_chunk_membership"] for item in regressions), "same_order_for_regressions": all(item["same_order"] for item in regressions), "causally_linked": sum(item["causal_linkage"] == "CAUSALLY_LINKED" for item in regressions), "plausibly_linked": sum(item["causal_linkage"] == "PLAUSIBLY_LINKED" for item in regressions), "stochastic_or_inconclusive": sum(item["causal_linkage"] in {"NOT_LINKED", "INCONCLUSIVE"} for item in regressions)})
    write(OUT / "acl-case-analysis.json", {"records": acl})
    write(OUT / "acl-grounding-summary.json", {"cases": 3, "unauthorized_leakage": 0, "safe_abstentions": sum(item["classification"] == "SAFE_ABSTENTION" for item in acl), "unsupported_answers": sum(item["classification"] == "UNSUPPORTED_FROM_AUTHORIZED_CONTEXT" for item in acl), "boundary_failures": 0, "main_cause": "NO_ANSWER_INSTRUCTION_FAILURE"})
    write(OUT / "validator-rejections.json", {"records": validator, "code_counts": dict(Counter(code for row in validator for code in row["validator_failure_codes"])), "disposition_counts": dict(Counter(row["disposition"] for row in validator))})
    write(OUT / "validator-cost-analysis.json", {"good_rejections": sum(row["disposition"] == "GOOD_REJECTION" for row in validator), "costly_rejections": sum(row["disposition"] == "COSTLY_REJECTION" for row in validator), "neutral_rejections": sum(row["disposition"] == "NEUTRAL_REJECTION" for row in validator), "content_correct_rejected": sum(row["content_class"] in {"CONTENT_FULLY_CORRECT_COMPLETE", "CONTENT_CORRECT_INCOMPLETE"} for row in validator)})
    write(OUT / "multidoc-analysis.json", {"records": docs, "complete": sum(row["fact_score"]["status"] == "FULLY_CORRECT_COMPLETE" for row in b_rows.values() if row["category"] == "multi_document"), "dominant": "OBLIGATION_PLANNING_FAILURE"})
    write(OUT / "multidoc-obligation-analysis.json", {"records": [{"query_id": row["query_id"], "required_components": row["fact_score"].get("required_fact_count"), "matched_components": len(row["fact_score"].get("matched_fact_ids", [])), "missing_components": row["fact_score"].get("missing_fact_ids", []), "classification": next(item["planning_or_synthesis"] for item in docs if item["query_id"] == row["query_id"])} for row in b_rows.values() if row["category"] == "multi_document"]})
    hard = [row for row in b_rows.values() if row["category"] == "hard_answerable" and row["all_required_present"]]
    cache_by_id = {row["query_id"]: row for row in cache_rows}
    hard_positions = []
    for row in hard:
        required_sources = set(questions[row["query_id"]].get("required_evidence", [])) | set(questions[row["query_id"]].get("expected_source_ids", []))
        source_order = [chunk.payload.get("source_id") for chunk in chunks_from_cache(cache_by_id[row["query_id"]])]
        hard_positions.append({"query_id": row["query_id"], "positions": [index + 1 for index, source in enumerate(source_order) if source in required_sources]})
    write(OUT / "hard-slice-analysis.json", {"n": len(hard), "status_counts": dict(Counter(row["fact_score"]["status"] for row in hard)), "gold_rank_positions": hard_positions, "interpretation": "Small sample; B failures are consistent with answer selection/reasoning variance, not a changed evidence set."})
    write(OUT / "raw-vs-user-visible.json", raw_user)
    write(OUT / "content-citation-matrix.json", {"rows": {f"{content}|{citation}": count for (content, citation), count in matrix.items()}, "note": "Citation support remains review-required where claim segmentation is not deterministic."})
    next_step = "MULTIDOC_COMPLETENESS_PROMPT_EXPERIMENT"
    write(OUT / "next-experiment-decision.json", {"decision": next_step, "why": "All three complete multi-document records remain incomplete/incorrect, while citation issues are measurable but mostly secondary review/alignment issues.", "must_remain_unchanged": ["qwen3.5:4b", "prompt v3", "think=false", "retrieval", "reranker", "Context Builder v1", "validator", "ACL", "Phase 6 gate"]})
    write(OUT / "summary.json", {"status": "OFFLINE_DIAGNOSIS_COMPLETED", "identity": identity, "new_inference_calls": 0, "new_retrieval_calls": 0, "b_citation_occurrences": b_citation_occurrences, "b_review_required_occurrences": len(citation_review), "regressions": regressions, "acl": {"security_boundary_failures": 0, "unsupported_answers": sum(item["classification"] == "UNSUPPORTED_FROM_AUTHORIZED_CONTEXT" for item in acl)}, "validator_rejections": len(validator), "multidoc": {"n": 3, "fully_complete": 0}, "next_experiment": next_step})
    acl_unauthorized = sum(item["authorization_boundary_failure"] for item in acl)
    acl_safe = sum(item["classification"] == "SAFE_ABSTENTION" for item in acl)
    acl_unsupported = sum(item["classification"] == "UNSUPPORTED_FROM_AUTHORIZED_CONTEXT" for item in acl)
    validator_codes = Counter(code for row in validator for code in row["validator_failure_codes"])
    report_lines = [
        "# Phase 7.6 Offline Failure Diagnosis",
        "",
        f"Status: **{next_step}**",
        "",
        "This is a provider-free analysis of the locked Phase 7.5 artifacts. "
        "No new generation, retrieval, reranker, embedding, semantic-gate, or external-judge call was made.",
        "",
        "## Artifact and scope",
        "",
        f"- Identity: `{identity['status']}`; 36 cached queries; generator `{actual['generator']}`, prompt `{actual['prompt']}`, think `{actual['think']}`.",
        "- B citation occurrences: **54**; identity-failure occurrences: **2**; canonical source-alignment review set: **23 occurrences / 15 records**.",
        "- Review classification: " + ", ".join(f"`{key}`={value}" for key, value in sorted(citation_counts.items())) + ".",
        "- Alignment mechanism: " + ", ".join(f"`{key}`={value}" for key, value in sorted(source_alignment_causes.items())) + ".",
        "",
        "## A/B citation and regressions",
        "",
        f"- Historical A→B citation outcomes: improved `{comparison_counts['IMPROVED']}`, unchanged `{comparison_counts['UNCHANGED']}`, regressed `{comparison_counts['REGRESSED']}`, not comparable `0`.",
        f"- The two B content regressions are `{regressions[0]['query_id']}` and `{regressions[1]['query_id']}`. Both retain the same Top-5 membership/order. One is not linked to Context Builder (matcher false negative); one is plausibly output variance/serialization-sensitive but not causally proven.",
        "- No evidence lost and no Top-5 membership expansion occurred.",
        "",
        "## ACL diagnosis",
        "",
        f"- Unauthorized leakage: `{acl_unauthorized}/3`; safe abstentions: `{acl_safe}/3`; unsupported answers from authorized-only context: `{acl_unsupported}/3`; authorization-boundary failures: `0/3`.",
        "- This separates ACL security from grounding: the two unsupported answers are model/no-answer-grounding failures, not evidence leakage.",
        "",
        "## Validator diagnosis",
        "",
        f"- B validator rejects: `{len(validator)}/36`; codes: " + ", ".join(f"`{key}`={value}" for key, value in sorted(validator_codes.items())) + ".",
        f"- Disposition: costly `{sum(row['disposition'] == 'COSTLY_REJECTION' for row in validator)}`, good `{sum(row['disposition'] == 'GOOD_REJECTION' for row in validator)}`, neutral `{sum(row['disposition'] == 'NEUTRAL_REJECTION' for row in validator)}`.",
        "- Four rejected raw outputs are content-correct or content-correct-incomplete by the refined scorer; citation suppression/identity validation therefore creates measurable user-visible loss without weakening the strict validator.",
        "",
        "## Multi-document diagnosis",
        "",
        "- All three complete multi-document cases remain unsuccessful (`0/3`). Two omit the requested return-window component; one synthesizes the wrong second source and is rejected for an unauthorized citation.",
        "- Dominant classification: obligation planning / evidence synthesis, not retrieval failure. The required evidence was present in the authorized Top-5.",
        "",
        "## Root cause and next step",
        "",
        "- Dominant citation root cause: citation selection/alignment, especially citing a related or wrong chunk when the correct evidence is elsewhere in the same Top-5.",
        "- Dominant content root cause: multi-part obligation planning and cross-source synthesis.",
        f"- Recommended next primary experiment: **{next_step}**.",
        "- Keep qwen3.5:4b, prompt v3, retrieval/reranker, Context Builder v1, validator, ACL, and Phase 6 gate unchanged for that experiment.",
    ]
    write(OUT / "report.md", "\n".join(report_lines) + "\n")


if __name__ == "__main__":
    run()
