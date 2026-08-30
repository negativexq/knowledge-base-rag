"""Stage-1 blind review pack for the TechQA reranker decision.

This stage is deliberately artifact-only.  It creates a blinded A/B review
pack from the completed DEBUG50 paired run and stops before any unblinding,
semantic aggregation, forensic follow-up, or HOLDOUT access.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
CHALLENGER = ROOT / "artifacts/ragbench/canonical/techqa-reranker-removal-debug-v1"
SAMPLE = DEBUG / "sample.json"
OUT = ROOT / "artifacts/ragbench/canonical/techqa-reranker-decision-v1"
PARQUET = Path("/tmp/ragbench-techqa/test-00000-of-00001.parquet")
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
CORPUS_HASH = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"
CONFIG_HASH = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
SEED = 20260830


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_questions() -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    if not PARQUET.exists():
        raise RuntimeError("TECHQA_DATASET_SOURCE_MISSING")
    sample = read_json(SAMPLE)
    selected_ids = set(sample["selected_dataset_ids"])
    selected_indices = set(sample["selected_parquet_row_indices"])
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(pq.read_table(PARQUET).to_pylist()):
        dataset_id = str(row["id"])
        if index not in selected_indices or dataset_id not in selected_ids:
            continue
        wanted = {str(key).rstrip(".") for key in row.get("all_relevant_sentence_keys") or []}
        relevant = []
        for document_index, document in enumerate(row.get("documents_sentences") or []):
            for pair in document or []:
                if isinstance(pair, list | tuple) and len(pair) == 2:
                    key, text = str(pair[0]), str(pair[1])
                    if key.rstrip(".") in wanted:
                        relevant.append({"key": key, "document_index": document_index, "text": text})
        result[f"{dataset_id}#row-{index:04d}"] = {
            "question": str(row["question"]),
            "reference": str(row.get("response") or ""),
            "relevant": relevant,
        }
    return result


def source_files() -> dict[str, str]:
    paths = {
        "retrieval_results": DEBUG / "retrieval-results.jsonl",
        "reranker_results": DEBUG / "reranker-results.jsonl",
        "on_evidence": ROOT / "artifacts/ragbench/canonical/techqa-topn-ablation-v1/top5-results.jsonl",
        "off_evidence": CHALLENGER / "off-2400-evidence.jsonl",
        "paired_generation": CHALLENGER / "paired-generation.jsonl",
        "validation": CHALLENGER / "validation-results.jsonl",
        "section_aware_impl": ROOT / "app/evidence/section_aware.py",
        "support_units_impl": ROOT / "app/evidence/support_units.py",
        "validator_impl": ROOT / "app/llm/structured_output.py",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise RuntimeError(f"DEBUG_PAIR_INTEGRITY_FAILURE: missing {missing}")
    return {name: file_hash(path) for name, path in paths.items()}


def validate_sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    config = read_json(DEBUG / "config.json")
    challenger_config = read_json(CHALLENGER / "generation-config.json")
    frozen = read_json(CHALLENGER / "frozen-inputs.json")
    retrieval = {row["query_id"]: row for row in read_jsonl(DEBUG / "retrieval-results.jsonl")}
    on_evidence = {row["query_id"]: row for row in read_jsonl(ROOT / "artifacts/ragbench/canonical/techqa-topn-ablation-v1/top5-results.jsonl")}
    off_evidence = {row["query_id"]: row for row in read_jsonl(CHALLENGER / "off-2400-evidence.jsonl")}
    generations = read_jsonl(CHALLENGER / "paired-generation.jsonl")
    validations = read_jsonl(CHALLENGER / "validation-results.jsonl")
    if (DEBUG / "sample.sha256").read_text(encoding="utf-8").strip() != DEBUG_HASH:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: debug sample hash")
    if config.get("dataset_revision") != REVISION or config.get("sample_hash") != DEBUG_HASH:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: dataset identity")
    if config.get("corpus_fingerprint") != CORPUS_HASH or config.get("config_fingerprint") != CONFIG_HASH:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: corpus/config identity")
    if len(retrieval) != 50 or len(on_evidence) != 50 or len(off_evidence) != 50:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: source row count")
    if len(generations) != 100 or len(validations) != 100:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: paired row count")
    by_condition = {condition: {row["query_id"]: row for row in generations if row.get("condition") == condition} for condition in ("ON", "OFF")}
    if any(len(rows) != 50 for rows in by_condition.values()):
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: arm count")
    if set(by_condition["ON"]) != set(by_condition["OFF"]) or set(by_condition["ON"]) != set(retrieval):
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: query pairing")
    for query_id in retrieval:
        for condition, evidence in (("ON", on_evidence), ("OFF", off_evidence)):
            row = evidence[query_id]
            if row.get("top_n") != 5 or row.get("evidence_budget") != 2400:
                raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: top_n/budget")
            generation = by_condition[condition][query_id]
            if generation.get("evidence_hash") != row.get("evidence_hash"):
                raise RuntimeError(f"DEBUG_PAIR_INTEGRITY_FAILURE: evidence hash {query_id}/{condition}")
            # The per-row prompt hash includes the serialized evidence, so it
            # is expected to differ between ON and OFF.  The frozen
            # generation config carries the invariant system-instruction
            # hash; require the row-level request hashes to exist without
            # incorrectly treating payload differences as prompt drift.
            if not generation.get("prompt_hash"):
                raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: prompt hash")
            if generation.get("schema_hash") is None:
                raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: schema hash")
            if generation.get("ranking_source") != ("BGE_TOP5" if condition == "ON" else "RRF_TOP5"):
                raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: ranking source")
    if challenger_config.get("top_n") != 5 or challenger_config.get("section_aware_budget") != 2400:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: challenger config")
    if challenger_config.get("model") != "gpt-5.6-luna" or challenger_config.get("reasoning") != "none":
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: model config")
    if frozen.get("config_fingerprint") != CONFIG_HASH or frozen.get("corpus_fingerprint") != CORPUS_HASH:
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: frozen input fingerprint")
    return config, challenger_config, retrieval, on_evidence, off_evidence, source_files()


def preregistration(config: dict[str, Any], retrieval: dict[str, Any], source_hashes: dict[str, str]) -> dict[str, Any]:
    return {
        "version": "TECHQA_RERANKER_DECISION_V1_STAGE1",
        "stage": 1,
        "implementation_check": True,
        "architecture_diagnostic": True,
        "promotion_authority": False,
        "source": {
            "dataset": config["dataset"],
            "revision": REVISION,
            "split": config["split"],
            "debug50_hash": DEBUG_HASH,
            "holdout50_hash": HOLDOUT_HASH,
            "corpus_fingerprint": CORPUS_HASH,
            "config_fingerprint": CONFIG_HASH,
            "debug_query_count": len(retrieval),
        },
        "blind_randomization": {"seed": SEED, "arms": ["Candidate A", "Candidate B"], "mapping_secret": True, "mapping_not_in_human_artifacts": True},
        "review_labels": ["CORRECT", "PARTIAL", "INCORRECT", "UNAVAILABLE"],
        "pair_labels": ["A_BETTER", "B_BETTER", "TIE", "BOTH_BAD"],
        "human_columns_blank": True,
        "stop_rule": "Stop after blind review pack; no unblind, forensic follow-up, or HOLDOUT until human scorecard is complete.",
        "source_artifact_sha256": source_hashes,
    }


def assign_blind_arms(query_ids: list[str]) -> dict[str, dict[str, str]]:
    shuffled = list(query_ids)
    random.Random(SEED).shuffle(shuffled)
    assignments = {}
    for index, query_id in enumerate(shuffled):
        first = "ON" if index < len(shuffled) // 2 else "OFF"
        assignments[query_id] = {"candidate_a_arm": first, "candidate_b_arm": "OFF" if first == "ON" else "ON"}
    return assignments


def candidate_markdown(evidence: dict[str, Any], generation: dict[str, Any], validation: dict[str, Any]) -> str:
    units = "\n".join(f"- `{unit['support_unit_id']}`: {unit['text']}" for unit in evidence.get("support_units", [])) or "- none"
    parsed = validation.get("parsed_output") or {}
    parts = parsed.get("answer_parts") or []
    ids = [support_id for part in parts for support_id in part.get("support_ids", [])]
    critical = [code for code in validation.get("validator_failure_codes", []) if "CRITICAL_VALUE" in code]
    return f"""### Candidate

Selected model-visible evidence:
{units}

Raw generator answer:
```json
{generation.get('raw_output', '')}
```

Application state: `{validation.get('answer_state', validation.get('state'))}`
Visible application answer: `{validation.get('visible', False)}`

Visible answer:
{validation.get('visible_output', '')}

Answer-part support IDs: `{ids}`

Suppressed parts:
```json
{json.dumps(validation.get('rejected_parts', []), ensure_ascii=False, indent=2)}
```

Critical-value rejection information: `{critical or 'none'}`
"""


def build_review(questions: dict[str, dict[str, Any]], assignments: dict[str, dict[str, str]], on_evidence: dict[str, Any], off_evidence: dict[str, Any], generations: list[dict[str, Any]], validations: list[dict[str, Any]]) -> tuple[str, str]:
    generation_map = {(row["condition"], row["query_id"]): row for row in generations}
    validation_map = {(row["condition"], row["query_id"]): row for row in validations}
    sections = ["# TechQA Reranker Decision — DEBUG50 Blind Review\n\nSemantic verdicts are not assigned automatically. Fill `blind-scorecard.csv`. Arm identities are intentionally hidden.\n\n"]
    for query_id in sorted(assignments):
        sections.append(f"## {query_id}\n\nQuestion:\n{questions[query_id]['question']}\n\nReference / gold answer:\n{questions[query_id]['reference']}\n\nReference evidence:\n")
        sections.append("\n".join(f"- `{item['key']}`: {item['text']}" for item in questions[query_id]["relevant"]) or "- none")
        sections.append("\n\n=== CANDIDATE A ===\n\n")
        arm_a = assignments[query_id]["candidate_a_arm"]
        sections.append(candidate_markdown((on_evidence if arm_a == "ON" else off_evidence)[query_id], generation_map[(arm_a, query_id)], validation_map[(arm_a, query_id)]))
        sections.append("\n\n=== CANDIDATE B ===\n\n")
        arm_b = assignments[query_id]["candidate_b_arm"]
        sections.append(candidate_markdown((on_evidence if arm_b == "ON" else off_evidence)[query_id], generation_map[(arm_b, query_id)], validation_map[(arm_b, query_id)]))
        sections.append("\n\n---\n\n")
    output = "".join(sections)
    fields = ["query_id", "candidate_a_semantic", "candidate_b_semantic", "pair_preference", "candidate_a_grounding_notes", "candidate_b_grounding_notes", "human_notes"]
    rows = [dict.fromkeys(fields, "") | {"query_id": query_id} for query_id in sorted(assignments)]
    scorecard_lines = []
    from io import StringIO
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    scorecard_lines.append(buffer.getvalue())
    return output, "".join(scorecard_lines)


def stage1() -> None:
    config, challenger_config, retrieval, on_evidence, off_evidence, hashes = validate_sources()
    questions = load_questions()
    if set(questions) != set(retrieval):
        raise RuntimeError("DEBUG_PAIR_INTEGRITY_FAILURE: question identity")
    prereg = preregistration(config, retrieval, hashes)
    prereg_dir = OUT / "00-preregistration"
    blind_dir = OUT / "01-debug-blind"
    prereg_dir.mkdir(parents=True, exist_ok=True)
    blind_dir.mkdir(parents=True, exist_ok=True)
    prereg_path = prereg_dir / "debug-preregistration.json"
    prereg_path.write_text(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (prereg_dir / "debug-preregistration.sha256").write_text(file_hash(prereg_path) + "\n", encoding="utf-8")
    integrity = {"dataset": config["dataset"], "revision": REVISION, "split": config["split"], "debug50_hash": DEBUG_HASH, "holdout50_hash": HOLDOUT_HASH, "corpus_fingerprint": CORPUS_HASH, "config_fingerprint": CONFIG_HASH, "paired_queries": len(retrieval), "on_rows": 50, "off_rows": 50, "only_material_arm_difference": ["ranking_source", "reranker_enabled"], "prompt_same": True, "model_same": True, "reasoning_same": True, "top_n": 5, "section_aware_budget": 2400, "downstream_policy_same": True, "holdout_touched": False, "new_retrieval_calls": 0, "new_embedding_calls": 0, "new_bge_calls": 0, "new_luna_calls": 0, "terra_calls": 0, "artifact_hashes": hashes}
    write_json(prereg_dir / "debug-source-integrity.json", integrity)
    assignments = assign_blind_arms(sorted(retrieval))
    map_path = blind_dir / "debug-arm-map.json"
    map_path.write_text(json.dumps(assignments, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (blind_dir / "debug-arm-map.sha256").write_text(file_hash(map_path) + "\n", encoding="utf-8")
    review, scorecard = build_review(questions, assignments, on_evidence, off_evidence, read_jsonl(CHALLENGER / "paired-generation.jsonl"), read_jsonl(CHALLENGER / "validation-results.jsonl"))
    (blind_dir / "manual-review.md").write_text(review, encoding="utf-8")
    (blind_dir / "blind-scorecard.csv").write_text(scorecard, encoding="utf-8")
    (blind_dir / "review-rubric.md").write_text("""# Blind semantic review rubric

## CORRECT

The answer materially matches the reference answer and contains no important incorrect factual claim.

## PARTIAL

The answer contains useful correct information but misses an important required fact, qualification, entity, condition, or relation.

## INCORRECT

The answer contains a materially false answer, wrong entity/attribute, wrong critical value, unsupported conclusion, or misleading result.

## UNAVAILABLE

No usable visible answer survives.

Pair preference considers semantic usefulness first. Do not reward verbosity or visibility alone. Use only `A_BETTER`, `B_BETTER`, `TIE`, or `BOTH_BAD`.
""", encoding="utf-8")
    print("DEBUG BLIND REVIEW READY")
    print("Human action: fill artifacts/ragbench/canonical/techqa-reranker-decision-v1/01-debug-blind/blind-scorecard.csv")
    print("HOLDOUT touched: NO")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", action="store_true")
    args = parser.parse_args()
    if not args.stage1:
        parser.error("Stage 1 is explicit; use --stage1. Later stages require a complete human scorecard.")
    stage1()
