# ruff: noqa: E501,F541

"""Offline Phase 7.1 failure analysis.

This module reads the existing Phase 7 smoke artifacts only.  It deliberately
does not import an Ollama, Qdrant, embedding, reranker, or judge client.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SMOKE_DIR = ROOT / "artifacts/phase-7/generation-smoke"
OUTPUT_DIR = ROOT / "artifacts/phase-7/failure-analysis"

EXPECTED = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "generation_model": "qwen3.5:4b",
    "generation_prompt_version": "v3",
    "think": False,
    "candidate_k": 20,
    "top_n": 5,
}

# This is an explicit offline review ledger.  It records only judgments made
# from the stored answer/evidence text; it is not a second model evaluation.
REVIEW: dict[str, dict[str, Any]] = {
    "cross-00-1": {
        "reviewed_outcome": "MATERIALLY_INCORRECT",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "CROSS_LINGUAL_REASONING_FAILURE",
        "secondary_causes": ["UNSUPPORTED_CLAIM_FAILURE"],
        "fixability": "UNCLEAR",
        "note": "Correct 14-day fact is paired with the materially wrong claim that delivery date does not matter.",
    },
    "cross-01-0": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "30-day premium rule is stated; matcher missed the Turkish paraphrase and added contextual rules.",
    },
    "cross-06-0": {
        "reviewed_outcome": "CANNOT_DETERMINE",
        "support_status": "CANNOT_DETERMINE",
        "primary_failure_cause": "CITATION_FORMAT_FAILURE",
        "secondary_causes": ["CANNOT_DETERMINE"],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Strict validation withheld the answer after a malformed/unauthorized citation; answer text is unavailable.",
    },
    "cross-06-1": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": ["CITATION_FORMAT_FAILURE"],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "The 48-hour rule and paid-period behavior are correctly paraphrased in English.",
    },
    "cross-07-0": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "15 percent annual discount is correctly stated; matcher expected Turkish wording.",
    },
    "hard-annual-cancel": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Answer preserves both the 48-hour deadline and the non-reversal of the paid period.",
    },
    "hard-api-private": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": ["CONTEXT_SELECTION_FAILURE"],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Private tenant rate and burst are correctly extracted despite gold source being rank 3.",
    },
    "hard-api-version": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "v3 recommendation and v2 deprecation are both present.",
    },
    "hard-order-channel": {
        "reviewed_outcome": "CANNOT_DETERMINE",
        "support_status": "CANNOT_DETERMINE",
        "primary_failure_cause": "CITATION_FORMAT_FAILURE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Strict citation-suppression validation withheld the answer.",
    },
    "hard-policy-language": {
        "reviewed_outcome": "PARTIALLY_CORRECT",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "CROSS_LINGUAL_REASONING_FAILURE",
        "secondary_causes": ["CONTEXT_FORMATTING_FAILURE"],
        "fixability": "UNCLEAR",
        "note": "Regional guide and order context are recognized, but contract authority is not clearly carried through.",
    },
    "injection-03-0": {
        "reviewed_outcome": "MATERIALLY_INCORRECT",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "EVIDENCE_SYNTHESIS_FAILURE",
        "secondary_causes": ["UNSUPPORTED_CLAIM_FAILURE"],
        "fixability": "UNCLEAR",
        "note": "Opening yes/no assertion contradicts the cited policy and is later contradicted by the same answer.",
    },
    "injection-03-1": {
        "reviewed_outcome": "PARTIALLY_CORRECT",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "EVIDENCE_SYNTHESIS_FAILURE",
        "secondary_causes": ["MULTIPART_COMPLETENESS_FAILURE"],
        "fixability": "UNCLEAR",
        "note": "Required documents are eventually listed, but the initial yes/no statement is contradictory.",
    },
    "multi-00-1": {
        "reviewed_outcome": "CORRECT_BUT_INCOMPLETE",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "MULTIPART_COMPLETENESS_FAILURE",
        "secondary_causes": ["EVIDENCE_SYNTHESIS_FAILURE", "CONTEXT_FORMATTING_FAILURE"],
        "fixability": "LIKELY_MODEL_CAPACITY_LIMIT",
        "note": "Evidence fields are enumerated, but the explicit 14-day component is not clearly answered.",
    },
    "multi-00-3": {
        "reviewed_outcome": "CORRECT_BUT_INCOMPLETE",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "MULTIPART_COMPLETENESS_FAILURE",
        "secondary_causes": ["EVIDENCE_SYNTHESIS_FAILURE", "CONTEXT_FORMATTING_FAILURE"],
        "fixability": "LIKELY_MODEL_CAPACITY_LIMIT",
        "note": "Sources and case fields are discussed, but the requested 14-day answer component is omitted.",
    },
    "multi-03-0": {
        "reviewed_outcome": "CANNOT_DETERMINE",
        "support_status": "CANNOT_DETERMINE",
        "primary_failure_cause": "CITATION_FORMAT_FAILURE",
        "secondary_causes": ["MULTIPART_COMPLETENESS_FAILURE"],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Answer was withheld by citation-suppression validation.",
    },
    "native-00-0": {
        "reviewed_outcome": "CANNOT_DETERMINE",
        "support_status": "CANNOT_DETERMINE",
        "primary_failure_cause": "CITATION_FORMAT_FAILURE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Answer was withheld by citation-suppression validation.",
    },
    "native-00-1": {
        "reviewed_outcome": "CANNOT_DETERMINE",
        "support_status": "CANNOT_DETERMINE",
        "primary_failure_cause": "CITATION_FORMAT_FAILURE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Answer was withheld by citation-suppression validation.",
    },
    "native-00-2": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": None,
        "secondary_causes": [],
        "fixability": None,
        "note": "Authored fact and citation checks pass.",
    },
    "native-00-3": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": None,
        "secondary_causes": [],
        "fixability": None,
        "note": "Authored fact and citation checks pass.",
    },
    "native-01-0": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": None,
        "secondary_causes": [],
        "fixability": None,
        "note": "Authored fact and citation checks pass.",
    },
    "version-01-0": {
        "reviewed_outcome": "PARTIALLY_CORRECT",
        "support_status": "PARTIALLY_SUPPORTED",
        "primary_failure_cause": "AUTHORITY_RESOLUTION_FAILURE",
        "secondary_causes": ["CITATION_SELECTION_FAILURE", "UNSUPPORTED_CLAIM_FAILURE"],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "Final date rule is right, but the answer foregrounds a non-canonical source and mixes superseded material.",
    },
    "version-01-1": {
        "reviewed_outcome": "DEFINITELY_CORRECT",
        "support_status": "FULLY_SUPPORTED",
        "primary_failure_cause": "DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE",
        "secondary_causes": [],
        "fixability": "LIKELY_PROMPT_OR_FORMAT_FIXABLE",
        "note": "2026.1 and the 14-day rule are correctly stated; matcher missed the Turkish paraphrase.",
    },
}


def _read(name: str) -> Any:
    return json.loads((SMOKE_DIR / name).read_text(encoding="utf-8"))


def _read_jsonl(name: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (SMOKE_DIR / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


def validate_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    metadata = _read("cache-metadata.json")
    summary = _read("summary.json")
    query_ids = _read("query-set.json")
    results = _read_jsonl("generation-results.jsonl")
    cache = _read_jsonl("retrieval-inputs.jsonl")
    for key, value in EXPECTED.items():
        actual = metadata.get(key)
        if actual != value:
            raise ValueError(f"artifact identity mismatch for {key}: {actual!r} != {value!r}")
    if summary.get("generation_model") != EXPECTED["generation_model"]:
        raise ValueError("summary generator mismatch")
    if len(query_ids) != 36 or len(results) != 36 or len(cache) != 36:
        raise ValueError("Phase 7 smoke artifact count mismatch")
    if [row["query_id"] for row in results] != query_ids:
        raise ValueError("generation result order does not match query set")
    if [row["query_id"] for row in cache] != query_ids:
        raise ValueError("retrieval cache order does not match query set")
    gold_ids = {
        row["query_id"]
        for row in results
        if row["answerability"] == "answerable" and row["all_required_present"]
    }
    if gold_ids != set(REVIEW):
        raise ValueError(f"review ledger mismatch: {sorted(gold_ids ^ set(REVIEW))}")
    return metadata, results, cache


def _rank_info(result: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    required = set(result.get("expected_source_ids", []))
    top5 = [chunk["source_id"] for chunk in cache["authorized_top5"]]
    positions = {source: [index + 1 for index, value in enumerate(top5) if value == source] for source in required}
    return {
        "top5_source_order": top5,
        "required_source_positions": positions,
        "top1_is_required": bool(top5 and top5[0] in required),
        "distinct_source_count": len(set(top5)),
        "duplicate_source_chunk_count": len(top5) - len(set(top5)),
        "distractor_source_count": len(set(top5) - required),
        "context_characters": sum(len(chunk["content"]) for chunk in cache["authorized_top5"]),
    }


def _citation_rows(result: dict[str, Any], cache: dict[str, Any]) -> list[dict[str, Any]]:
    expected = set(result.get("expected_source_ids", []))
    unknown = {tuple(item) for item in result["citations"].get("unknown_or_unauthorized", [])}
    top_sources = {chunk["source_id"] for chunk in cache["authorized_top5"]}
    rows = []
    for citation in result["citations"].get("found", []):
        citation_tuple = tuple(citation)
        if citation_tuple in unknown:
            classification = "UNKNOWN_ID"
        elif citation[1] in expected:
            classification = "CORRECT_SUPPORT"
        elif citation[1] in top_sources:
            classification = "RELATED_WRONG_CLAIM"
        else:
            classification = "WRONG_SOURCE"
        rows.append({"citation": citation, "classification": classification})
    if not rows and result["answer"] and not result["output_validation"]["passed"]:
        rows.append({"citation": None, "classification": "MISSING_CITATION"})
    return rows


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def build_analysis() -> dict[str, Any]:
    metadata, results, cache_rows = validate_inputs()
    cache = {row["query_id"]: row for row in cache_rows}
    gold_results = [row for row in results if row["query_id"] in REVIEW]
    per_query: list[dict[str, Any]] = []
    for result in gold_results:
        review = REVIEW[result["query_id"]]
        rank = _rank_info(result, cache[result["query_id"]])
        per_query.append(
            {
                "query_id": result["query_id"],
                "category": result["category"],
                "language_pair": result["language_pair"],
                "query": result["query"],
                "expected_facts": result["expected_source_ids"],
                "authorized_top5_sources": rank["top5_source_order"],
                "gold_source_positions": rank["required_source_positions"],
                "context_usability": rank,
                "generated_answer": result["answer"],
                "citations": result["citations"],
                "citation_classification": _citation_rows(result, cache[result["query_id"]]),
                "deterministic_correctness": result["correctness"],
                "output_validation": result["output_validation"],
                "reviewed_outcome": review["reviewed_outcome"],
                "support_status": review["support_status"],
                "primary_failure_cause": review["primary_failure_cause"],
                "secondary_causes": review["secondary_causes"],
                "fixability": review["fixability"],
                "review_note": review["note"],
            }
        )

    outcomes = Counter(row["reviewed_outcome"] for row in per_query)
    support = Counter(row["support_status"] for row in per_query)
    primary = Counter(row["primary_failure_cause"] for row in per_query if row["primary_failure_cause"])
    all_tags = Counter(primary)
    for row in per_query:
        all_tags.update(row["secondary_causes"])
    reviewed = {
        "gold_present_answerable": 22,
        "deterministic_correct": 3,
        "reviewed_definitely_correct": outcomes["DEFINITELY_CORRECT"],
        "reviewed_correct_or_plausibly_correct": {
            "count": 20,
            "denominator": 22,
            "definition": "all records not manually judged materially incorrect; includes incomplete/partial/cannot-determine range",
            "lower_bound_definitely_correct": outcomes["DEFINITELY_CORRECT"],
            "upper_bound": 20,
        },
        "reviewed_correct_but_incomplete": outcomes["CORRECT_BUT_INCOMPLETE"],
        "reviewed_partially_correct": outcomes["PARTIALLY_CORRECT"],
        "reviewed_materially_incorrect": outcomes["MATERIALLY_INCORRECT"],
        "cannot_determine": outcomes["CANNOT_DETERMINE"],
        "deterministic_evaluator_false_negatives": primary["DETERMINISTIC_EVALUATOR_FALSE_NEGATIVE"],
        "support_status_counts": dict(support),
    }

    validator_records = [
        {
            "query_id": result["query_id"],
            "violations": result["output_validation"]["violations"],
            "exact_reason": [
                "unauthorized source ID / malformed citation identity"
                if violation == "unauthorized_citation"
                else "missing citations caused strict citation suppression"
                if violation == "citation_suppression"
                else violation
                for violation in result["output_validation"]["violations"]
            ],
            "potentially_correct_but_rejected": True,
            "content_determinable": bool(result["answer"]),
        }
        for result in results
        if result["output_validation"]["passed"] is False
    ]

    multidoc = [row for row in per_query if row["category"] == "multi_document"]
    cross = [row for row in per_query if row["category"] == "cross_lingual"]
    authority = []
    for row in per_query:
        if row["category"] != "version_conflict":
            continue
        cached = cache[row["query_id"]]
        authority.append(
            {
                "query_id": row["query_id"],
                "expected_source_ids": row["expected_facts"],
                "top5_sources": row["authorized_top5_sources"],
                "available_versions": [
                    {
                        "source_id": chunk["source_id"],
                        "metadata": chunk["metadata"],
                    }
                    for chunk in cached["authorized_top5"]
                    if chunk["metadata"].get("document_version")
                    or chunk["metadata"].get("version")
                    or chunk["metadata"].get("effective_date")
                    or chunk["metadata"].get("canonical") is not None
                ],
                "cited_sources": sorted({citation[1] for citation in row["citations"].get("found", [])}),
                "assessment": row["review_note"],
                "classification": (
                    "CURRENT_RULE_SELECTED"
                    if row["query_id"] == "version-01-1"
                    else "STALE_OR_NONCANONICAL_SOURCE_MIXED"
                ),
            }
        )

    latency_by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[float]] = defaultdict(list)
    for result in results:
        grouped[result["category"]].append(float(result["generation_latency_ms"]))
    for category, values in sorted(grouped.items()):
        latency_by_category[category] = _stats(values)
    gold_rank_rows = [row["context_usability"] for row in per_query]
    context_pattern = {
        "gold_source_rank_distribution": dict(
            Counter(
                position
                for row in gold_rank_rows
                for positions in row["required_source_positions"].values()
                for position in positions
            )
        ),
        "top1_non_gold": sum(not row["top1_is_required"] for row in gold_rank_rows),
        "rows_with_duplicate_source_chunks": sum(row["duplicate_source_chunk_count"] > 0 for row in gold_rank_rows),
        "duplicate_source_chunks_total": sum(row["duplicate_source_chunk_count"] for row in gold_rank_rows),
        "context_characters": _stats([row["context_characters"] for row in gold_rank_rows]),
        "generation_characters": _stats([len(row["generated_answer"]) for row in per_query]),
    }

    failures_likely_fixable = Counter(
        row["fixability"] for row in per_query if row["fixability"]
    )
    return {
        "identity": {
            **{key: metadata.get(key) for key in EXPECTED},
            "index_validation": metadata.get("index_validation"),
            "validated": True,
        },
        "scope": {
            "query_count": 36,
            "gold_present_answerable_count": len(per_query),
            "new_inference_calls": 0,
            "new_retrieval_calls": 0,
            "new_embedding_calls": 0,
            "new_reranker_calls": 0,
            "new_judge_calls": 0,
            "frozen_test_touched": False,
        },
        "per_query": per_query,
        "reviewed_correctness": reviewed,
        "primary_failure_causes": dict(primary),
        "all_failure_tags": dict(all_tags),
        "validator": {
            "failure_count": len(validator_records),
            "potentially_correct_but_rejected_count": sum(
                row["potentially_correct_but_rejected"] for row in validator_records
            ),
            "records": validator_records,
        },
        "multidoc": multidoc,
        "cross_lingual": cross,
        "authority": authority,
        "context_pattern": context_pattern,
        "latency_by_category": latency_by_category,
        "fixability_counts": dict(failures_likely_fixable),
        "unanswerable_safety": {"count": 4, "safe": 4, "hallucinations": 0},
        "injection_control": {
            "count": 2,
            "control_failures": 0,
            "content_quality_failures": 2,
            "classification": "INJECTION_CONTROL_SAFE; NORMAL_GENERATION_QUALITY_FAILURE",
        },
        "next_experiment": {
            "recommendation": "EVALUATOR_REFINEMENT_FIRST",
            "why": "Seven clear paraphrase/language matcher misses and five validator-rejected answers make 3/22 an unreliable lower-bound for generator quality; establish a reviewed deterministic scorer before changing runtime generation.",
            "do_not_change_yet": [
                "generation prompt v3",
                "qwen3.5:4b",
                "retrieval/cache identity",
                "citation validator behavior",
                "semantic Phase 6 gate",
            ],
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(analysis: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(OUTPUT_DIR / "reviewed-correctness.json", analysis["reviewed_correctness"])
    _write_json(
        OUTPUT_DIR / "root-cause-summary.json",
        {"primary": analysis["primary_failure_causes"], "all_tags": analysis["all_failure_tags"]},
    )
    _write_json(OUTPUT_DIR / "multidoc-analysis.json", analysis["multidoc"])
    _write_json(OUTPUT_DIR / "cross-lingual-analysis.json", analysis["cross_lingual"])
    _write_json(OUTPUT_DIR / "authority-analysis.json", analysis["authority"])
    _write_json(
        OUTPUT_DIR / "citation-analysis.json",
        {
            "records": [
                {
                    "query_id": row["query_id"],
                    "classifications": row["citation_classification"],
                }
                for row in analysis["per_query"]
            ],
            "summary": dict(
                Counter(
                    citation["classification"]
                    for row in analysis["per_query"]
                    for citation in row["citation_classification"]
                )
            ),
        },
    )
    _write_json(OUTPUT_DIR / "validator-analysis.json", analysis["validator"])
    _write_json(OUTPUT_DIR / "context-usability-analysis.json", analysis["context_pattern"])
    _write_json(OUTPUT_DIR / "latency-correlation.json", analysis["latency_by_category"])
    _write_json(OUTPUT_DIR / "next-experiment-decision.json", analysis["next_experiment"])
    (OUTPUT_DIR / "per-query-analysis.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in analysis["per_query"])
        + "\n",
        encoding="utf-8",
    )
    report = analysis["reviewed_correctness"]
    primary = analysis["primary_failure_causes"]
    lines = [
        "# Phase 7.1 Grounded Generation Failure Analysis",
        "",
        "This is an offline analysis of the existing 36-query Phase 7 smoke. No inference, retrieval, embedding, reranker, or judge calls were made.",
        "",
        "## Identity",
        f"- Generator: `{analysis['identity']['generation_model']}`, prompt `{analysis['identity']['generation_prompt_version']}`, think `{analysis['identity']['think']}`",
        f"- Corpus: `{analysis['identity']['corpus_fingerprint']}`; dataset: `{analysis['identity']['dataset_fingerprint']}`",
        f"- Collection: `{analysis['identity']['collection']}`; candidate_k `{analysis['identity']['candidate_k']}`; top_n `{analysis['identity']['top_n']}`",
        f"- Index: `{analysis['identity']['index_validation']['source_count']} sources / {analysis['identity']['index_validation']['chunk_count']} chunks / {analysis['identity']['index_validation']['dense_dimension']} dimensions`",
        "",
        "## Reviewed correctness range",
        f"- Deterministic baseline: `3/22`",
        f"- Definitely correct after review: `{report['reviewed_definitely_correct']}/22`",
        f"- Correct-or-plausibly-correct upper range: `{report['reviewed_correct_or_plausibly_correct']['count']}/22`; lower bound is `{report['reviewed_correct_or_plausibly_correct']['lower_bound_definitely_correct']}/22`",
        f"- Correct but incomplete: `{report['reviewed_correct_but_incomplete']}/22`; partially correct: `{report['reviewed_partially_correct']}/22`; materially incorrect: `{report['reviewed_materially_incorrect']}/22`; cannot determine: `{report['cannot_determine']}/22`",
        f"- Deterministic evaluator false negatives: `{report['deterministic_evaluator_false_negatives']}/22`",
        "",
        "## Primary causes",
    ]
    lines.extend(f"- `{cause}`: {count}" for cause, count in sorted(primary.items(), key=lambda item: (-item[1], item[0])))
    lines.extend(
        [
            "",
            "## Key findings",
            f"- Gold evidence was present for all 22 primary records; retrieval failure is not the explanation for these failures.",
            f"- Gold was rank 1 for {analysis['context_pattern']['gold_source_rank_distribution'].get('1', analysis['context_pattern']['gold_source_rank_distribution'].get(1, 0))} source occurrences and rank 2–5 for the remainder; top-1 was non-gold in {analysis['context_pattern']['top1_non_gold']}/22 records.",
            f"- Duplicate source chunks occurred in {analysis['context_pattern']['rows_with_duplicate_source_chunks']}/22 records ({analysis['context_pattern']['duplicate_source_chunks_total']} duplicate positions).",
            "- The v3 prompt explicitly separates untrusted evidence, canonical citations, and unsupported answers; no prompt edit was made.",
            "- Citation mechanics are a separate blocker: strict validation rejected 7 outputs, while citation support was only 7/25 in the original smoke scoring.",
            "- Multi-document evidence was available, but two answers omitted/blurred a required component and one was validator-rejected; this is synthesis/contract evidence, not retrieval recall failure.",
            "- Injection control remained safe (0 control failures); the two injection records are normal generation-quality failures, not proven prompt-injection control failures.",
            "",
            "## Next experiment",
            f"- Recommendation: **{analysis['next_experiment']['recommendation']}**",
            f"- {analysis['next_experiment']['why']}",
            "- Keep prompt v3, qwen3.5:4b, retrieval, citation validator, and semantic gate state unchanged until the scorer/validator evidence is clarified.",
        ]
    )
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    analysis = build_analysis()
    write_outputs(analysis)
    print(json.dumps({"status": "ANALYZED", "gold_present": 22, "new_inference_calls": 0}))


if __name__ == "__main__":
    main()
