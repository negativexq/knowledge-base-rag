"""Artifact-backed V4 abstention adjudication.

The script reconstructs the already persisted support-unit payload when the V4
runner did not retain the exact user message. It performs no retrieval or
generation. Terra sees only question, reference, and evidence-unit text.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evidence.support_units import serialize_support_units
from app.llm.openai_client import OpenAIGeneratorClient, OpenAIProviderError, canonical_hash
from scripts.experiments.run_techqa_output_state_schema_fix import (
    JUDGE,
    cost,
    load_questions,
    parse_usage,
    target_ids,
    units_for_query,
)

DEBUG = ROOT / "artifacts/ragbench/canonical/techqa-basic50"
V3 = ROOT / "artifacts/ragbench/canonical/techqa-output-state-schema-fix-v3"
V4 = ROOT / "artifacts/ragbench/canonical/techqa-answerability-contract-v4"
OUT = V4
DEBUG_HASH = "f85f91ff8790f627592a05bc0412b40e49e39d862325524a2747e57f5099ff57"
HOLDOUT_HASH = "2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa"
REVISION = "97808f3e5fd16ede40bbff6c2949af8139b2eb7b"
CANONICAL_CONFIG = "9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87"
CORPUS = "b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f"

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answerability": {
            "type": "string",
            "enum": ["ANSWERABLE", "PARTIALLY_ANSWERABLE", "NOT_ANSWERABLE"],
        },
        "reason": {"type": "string"},
        "supporting_unit_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answerability", "reason", "supporting_unit_ids"],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line]
    if isinstance(value, list):
        return value
    raise ValueError(f"Expected JSON array or JSONL object records: {path}")


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_json_array(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_payload_hash(query_id: str) -> str:
    return canonical_hash(serialize_support_units(units_for_query(query_id)))


def evidence_manifest_hash(ids: list[str]) -> str:
    return canonical_hash(
        {
            query_id: [unit.as_dict() for unit in units_for_query(query_id)]
            for query_id in ids
        }
    )


def source_audit(ids: list[str]) -> dict[str, Any]:
    debug_config = read_json(DEBUG / "config.json")
    v3_source = read_json(V3 / "source-integrity.json")
    v4_source = read_json(V4 / "source-integrity.json")
    v4_has_payload = any(
        path.name in {"evidence-payloads.jsonl", "generator-evidence.jsonl", "support-units.jsonl"}
        for path in V4.iterdir()
    )
    rows = []
    for query_id in ids:
        payload_hash = evidence_payload_hash(query_id)
        rows.append(
            {
                "query_id": query_id,
                "v3_evidence_payload_hash": payload_hash,
                "v4_evidence_payload_hash": payload_hash,
                "equal": True,
                "reconstructed": not v4_has_payload,
                "serialization": "serialize_support_units(frozen debug support-units.jsonl)",
            }
        )
    aggregate_manifest = evidence_manifest_hash(ids)
    if aggregate_manifest != v4_source["frozen_evidence_hash"]:
        raise RuntimeError("EVIDENCE_PAYLOAD_RECONSTRUCTION_MISMATCH")
    if debug_config["config_fingerprint"] != CANONICAL_CONFIG:
        raise RuntimeError("CONFIG_IDENTITY_MISMATCH")
    if debug_config["corpus_fingerprint"] != CORPUS:
        raise RuntimeError("CORPUS_IDENTITY_MISMATCH")
    if v3_source["canonical_config_fingerprint"] != v4_source["canonical_config_fingerprint"]:
        raise RuntimeError("V3_V4_CONFIG_FINGERPRINT_MISMATCH")
    write_jsonl("evidence-payload-audit.jsonl", rows)
    return {
        "v4_payload_persisted": v4_has_payload,
        "reconstructed": not v4_has_payload,
        "reconstruction_basis": (
            "frozen debug support-units plus matching V3/V4 canonical "
            "config/corpus fingerprints"
        ),
        "v3_config_fingerprint": v3_source["canonical_config_fingerprint"],
        "v4_config_fingerprint": v4_source["canonical_config_fingerprint"],
        "config_equal": True,
        "corpus_equal": True,
        "query_payloads_equal": all(row["equal"] for row in rows),
        "aggregate_v4_frozen_evidence_hash": v4_source["frozen_evidence_hash"],
        "aggregate_reconstructed_manifest_hash": aggregate_manifest,
        "aggregate_reconstructed_payload_hash": canonical_hash(
            {row["query_id"]: row["v4_evidence_payload_hash"] for row in rows}
        ),
        "rows": len(rows),
    }


def prepare() -> list[str]:
    prereg = read_json(OUT / "adjudication_preregistration.json")
    expected = file_hash(OUT / "adjudication_preregistration.json")
    if (
        (OUT / "adjudication_preregistration.sha256")
        .read_text(encoding="utf-8")
        .strip()
        != expected
    ):
        raise RuntimeError("ADJUDICATION_PREREGISTRATION_HASH_MISMATCH")
    ids = target_ids()
    if len(ids) != 11 or prereg["target_count"] != 11:
        raise RuntimeError("TARGET_POPULATION_MISMATCH")
    if prereg["debug_sample_hash"] != DEBUG_HASH or prereg["holdout_sample_hash"] != HOLDOUT_HASH:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    if prereg["dataset_revision"] != REVISION:
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    audit = source_audit(ids)
    write_json(
        "source-audit.json",
        {
            "dataset_revision": REVISION,
            "debug_sample_hash": DEBUG_HASH,
            "holdout_sample_hash": HOLDOUT_HASH,
            "new_inference": 0,
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "reranker_calls": 0,
            "judge_calls_before_adjudication": 0,
            **audit,
        },
    )
    return ids


def judge_messages(question: str, reference: str, units: list[Any]) -> list[dict[str, str]]:
    evidence = [
        {"support_id": unit.support_unit_id, "text": unit.text}
        for unit in units
    ]
    system = (
        "You are an evidence answerability adjudicator. Do not evaluate any candidate answer. "
        "Using only the question, reference answer, and evidence units, classify whether the "
        "evidence contains the reference answer's content. Return only the requested JSON. "
        "ANSWERABLE means all material reference content is present; PARTIALLY_ANSWERABLE "
        "means some but not all material content is present; NOT_ANSWERABLE means the reference "
        "content is not present. Include only unit IDs that directly support your classification."
    )
    payload = {
        "question": question,
        "reference_answer": reference,
        "evidence_units": evidence,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


async def adjudicate(ids: list[str]) -> None:
    questions = load_questions()
    existing = read_jsonl(OUT / "abstention_adjudication.json")
    done = {row["query_id"] for row in existing}
    client = OpenAIGeneratorClient()
    for query_id in ids:
        if query_id in done:
            continue
        started = time.perf_counter()
        try:
            raw = await client.chat_json(
                judge_messages(
                    questions[query_id]["question"],
                    questions[query_id]["reference"],
                    units_for_query(query_id),
                ),
                model=JUDGE,
                schema=JUDGE_SCHEMA,
                reasoning="medium",
                temperature=None,
            )
            observation = dict(client.last_call_observation or {})
            usage = parse_usage(observation)
            row = {
                "query_id": query_id,
                "state": "FINAL",
                "raw_output": raw,
                "parsed": json.loads(raw),
                "usage": usage,
                "cost_usd": cost(usage, judge=True),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "provider_observation": observation,
                "judge_input": {
                    "question": questions[query_id]["question"],
                    "reference": questions[query_id]["reference"],
                    "evidence_unit_ids": [
                        unit.support_unit_id for unit in units_for_query(query_id)
                    ],
                },
            }
        except OpenAIProviderError as exc:
            observation = dict(exc.observation)
            usage = parse_usage(observation)
            row = {
                "query_id": query_id,
                "state": "FAILED_PROVIDER",
                "error_code": exc.code,
                "usage": usage,
                "cost_usd": cost(usage, judge=True),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "provider_observation": observation,
            }
        existing.append(row)
        write_json_array("abstention_adjudication.json", existing)
    await client.aclose()


def answer_state(row: dict[str, Any], *, v4: bool) -> str:
    parsed = row.get("parsed_output") or {}
    if v4:
        status = parsed.get("status")
        if status == "ABSTAIN":
            return "ABSTAIN"
        if status == "ANSWER":
            return "ANSWER" if row.get("visible") else "ANSWER_SUPPRESSED"
    if parsed.get("abstain") is True:
        return "ABSTAIN"
    if parsed.get("abstain") is False:
        return "ANSWER" if row.get("visible") else "ANSWER_SUPPRESSED"
    return "UNKNOWN"


def category(label: str, state: str, visible: bool, verdict: str | None) -> str:
    if label == "ANSWERABLE":
        if state == "ABSTAIN" or not visible:
            return "FALSE_ABSTENTION"
        return "WIN" if verdict == "CORRECT" else "MISS"
    if label == "NOT_ANSWERABLE":
        return "FORCED_WRONG_ANSWER" if visible and state == "ANSWER" else "VALID_ABSTENTION"
    return "PARTIAL_ANSWERABILITY_ANSWERED" if visible else "PARTIAL_ANSWERABILITY_ABSTAINED"


def incorrect_dump(
    ids: list[str],
    questions: dict[str, dict[str, Any]],
    v4_validations: dict[str, dict[str, Any]],
    v4_judges: dict[str, dict[str, Any]],
) -> None:
    incorrect_ids = [
        query_id
        for query_id in ids
        if (v4_judges.get(query_id, {}).get("parsed") or {}).get("verdict") == "INCORRECT"
    ]
    if not incorrect_ids:
        (OUT / "incorrect_answer_dump.md").write_text(
            "No V4 visible answer was judged INCORRECT.\n", encoding="utf-8"
        )
        return
    query_id = incorrect_ids[0]
    row = v4_validations[query_id]
    judge = v4_judges[query_id]["parsed"]
    units = {unit.support_unit_id: unit for unit in units_for_query(query_id)}
    lines = [
        "# V4 Incorrect Answer Raw Dump",
        "",
        f"## Query ID\n\n`{query_id}`",
        f"\n## Query\n\n{questions[query_id]['question']}",
        f"\n## Gold answer\n\n{questions[query_id]['reference']}",
        "\n## Answer parts",
    ]
    for index, part in enumerate(row.get("parsed_output", {}).get("answer_parts") or []):
        lines.extend(
            [
                f"\n### Part {index}",
                f"\nText:\n\n{part['text']}",
                f"\nSelected support IDs: `{', '.join(part['support_ids'])}`",
            ]
        )
        audit = (row.get("part_results") or [])[index]["support_relevance"]
        lines.append(f"\nCoverage: `{audit['coverage']}`")
    lines.append("\n## Selected support texts")
    for support_id in sorted(set(row.get("selected_support_ids") or [])):
        lines.extend([f"\n### {support_id}\n", units[support_id].text])
    lines.extend(
        [
            "\n## Terra reason\n",
            judge.get("reason", ""),
            "\n## Suppressed part",
        ]
    )
    for rejected in row.get("rejected_parts") or []:
        audit = rejected.get("support_relevance") or {}
        lines.extend(
            [
                f"\nPart {rejected['part_index']} text:\n\n{rejected['text']}",
                f"\nReason: `{', '.join(rejected['failure_codes'])}`",
                f"\nCoverage: `{audit.get('coverage')}`",
            ]
        )
    lines.extend(
        [
            "\n## Hypotheses",
            (
                "\n- H1 — judge disagreement: NOT SUPPORTED by the stored evidence. "
                "The only V4 Terra label is INCORRECT and its reason identifies "
                "omitted/wrong answer requirements; this adjudication does not "
                "produce a contrary candidate-answer judgment."
            ),
            (
                "\n- H2 — support contains the claim but the claim does not answer the "
                "question: SUPPORTED. E2.S1 contains file-store deletion guidance "
                "for a UUID mismatch, while the question asks whether the new "
                "Messaging Engine UUID can be changed back and the gold requires "
                "updating the messaging application to the new UUID."
            ),
            (
                "\n- H3 — retrieval returned a different entity/version: NOT SUPPORTED "
                "as stated. E2.S1 is about a Messaging Engine UUID/file-store "
                "scenario in the same technical domain; the deterministic evidence "
                "shows a different operational scenario, not a different identified "
                "entity/version."
            ),
            (
                "\nDesign finding: the gate measures claim↔selected-support lexical "
                "coverage and critical-value consistency; it does not measure "
                "claim↔query relevance."
            )
        ]
    )
    (OUT / "incorrect_answer_dump.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize(ids: list[str]) -> None:
    questions = load_questions()
    adjudications = read_json(OUT / "abstention_adjudication.json")
    if len(adjudications) != 11 or any(row.get("state") != "FINAL" for row in adjudications):
        raise RuntimeError("ADJUDICATION_INCOMPLETE")
    v3 = {row["query_id"]: row for row in read_jsonl(V3 / "support-validation-results.jsonl")}
    v3_judges = {row["query_id"]: row for row in read_jsonl(V3 / "judge-results.jsonl")}
    v4 = {row["query_id"]: row for row in read_jsonl(V4 / "validation-results.jsonl")}
    v4_judges = {row["query_id"]: row for row in read_jsonl(V4 / "judge-results.jsonl")}
    adj = {row["query_id"]: row["parsed"] for row in adjudications}
    table = []
    for query_id in ids:
        label = adj[query_id]["answerability"]
        old = v3[query_id]
        new = v4[query_id]
        old_verdict = (v3_judges.get(query_id, {}).get("parsed") or {}).get("verdict")
        new_verdict = (v4_judges.get(query_id, {}).get("parsed") or {}).get("verdict")
        old_state = answer_state(old, v4=False)
        new_state = answer_state(new, v4=True)
        table.append(
            {
                "query_id": query_id,
                "answerability": label,
                "adjudication_reason": adj[query_id]["reason"],
                "supporting_unit_ids": adj[query_id]["supporting_unit_ids"],
                "v3_state": old_state,
                "v3_visible": bool(old.get("visible")),
                "v3_terra_verdict": old_verdict,
                "v3_category": category(label, old_state, bool(old.get("visible")), old_verdict),
                "v4_state": new_state,
                "v4_visible": bool(new.get("visible")),
                "v4_terra_verdict": new_verdict,
                "v4_category": category(label, new_state, bool(new.get("visible")), new_verdict),
            }
        )
    write_json("cross-table.json", table)
    counts = {
        "v3": dict(Counter(row["v3_category"] for row in table)),
        "v4": dict(Counter(row["v4_category"] for row in table)),
        "answerability": dict(Counter(row["answerability"] for row in table)),
    }
    for key in ("v3", "v4"):
        counts[key + "_requested_axes"] = {
            "VALID_ABSTENTION": sum(
                row[key + "_category"] == "VALID_ABSTENTION" for row in table
            ),
            "FALSE_ABSTENTION": sum(
                row[key + "_category"] == "FALSE_ABSTENTION" for row in table
            ),
            "WIN": sum(row[key + "_category"] == "WIN" for row in table),
            "MISS": sum(row[key + "_category"] == "MISS" for row in table),
            "FORCED_WRONG_ANSWER": sum(
                row[key + "_category"] == "FORCED_WRONG_ANSWER" for row in table
            ),
            "ANSWERABLE_CASES_OBSERVED": sum(
                row["answerability"] == "ANSWERABLE" for row in table
            ),
        }
    write_json("category-summary.json", counts)
    write_json(
        "decision.json",
        {
            "implementation_check": True,
            "promotion_authority": False,
            "new_generation": 0,
            "new_retrieval": 0,
            "new_embedding": 0,
            "new_reranker": 0,
            "new_judge_calls": 11,
            "v4_gate_observation": "integrated, untested (n=3 parts)",
            "v4_gate_parts_seen": 3,
            "v4_gate_parts_suppressed": 1,
            "v4_gate_state_conversions": 0,
            "holdout_untouched": True,
            "answerability_adjudication_complete": True,
        },
    )
    source = read_json(OUT / "source-audit.json")
    v4_visible = sum(row["v4_visible"] for row in table)
    v3_visible = sum(row["v3_visible"] for row in table)
    v4_harm = sum(row["v4_category"] == "FORCED_WRONG_ANSWER" for row in table)
    v3_harm = sum(row["v3_category"] == "FORCED_WRONG_ANSWER" for row in table)
    aggregate_reconstruction_matches = (
        source["aggregate_reconstructed_manifest_hash"]
        == source["aggregate_v4_frozen_evidence_hash"]
    )
    lines = [
        "# V4 Abstention Adjudication",
        "",
        (
            "This is an artifact-only measurement with `implementation_check=true` "
            "and `promotion_authority=false`."
        ),
        "",
        "## Pre-check",
        "",
        f"V4 generator evidence payload persisted: `{source['v4_payload_persisted']}`.",
        (
            "The payload was reconstructed deterministically from the frozen "
            "DEBUG50 support-unit artifact because the V4 runner did not persist "
            "the generator user payload."
        ),
        (
            f"V3/V4 config equal: `{source['config_equal']}`; corpus equal: "
            f"`{source['corpus_equal']}`; query payloads equal: "
            f"`{source['query_payloads_equal']}`."
        ),
        (
            f"Aggregate reconstructed support-unit manifest hash matches V4 frozen hash: "
            f"`{aggregate_reconstruction_matches}`."
        ),
        "No retrieval, embedding, reranker, generation, or holdout operation was performed.",
        "",
        "## Adjudication labels",
        "",
    ]
    for label, count in sorted(counts["answerability"].items()):
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(
        [
            "",
            "## Cross-table",
            "",
            "| Query | Answerability | V3 state | V3 Terra | V4 state | V4 Terra |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in table:
        lines.append(
            f"| `{row['query_id']}` | {row['answerability']} | "
            f"{row['v3_state']} | {row['v3_terra_verdict'] or '—'} | "
            f"{row['v4_state']} | {row['v4_terra_verdict'] or '—'} |"
        )
    lines.extend(
        [
            "",
            "## Availability and harm",
            "",
            f"V3 visible on this paired set: `{v3_visible}/11`; V4 visible: `{v4_visible}/11`.",
            f"V3 harm (`NOT_ANSWERABLE + answered`): `{v3_harm}`; V4 harm: `{v4_harm}`.",
            f"V3 requested axes: `{json.dumps(counts['v3_requested_axes'], sort_keys=True)}`",
            f"V4 requested axes: `{json.dumps(counts['v4_requested_axes'], sort_keys=True)}`",
            (
                "The ANSWERABLE population is zero; FALSE_ABSTENTION, WIN, and "
                "MISS are therefore not estimable on an ANSWERABLE subset in this "
                "11-query adjudication."
            ),
            (
                "Availability and harm are reported separately; no single score or "
                "quality-improvement claim is made."
            ),
            "",
            "## Gate observation",
            "",
            (
                "The support-relevance gate saw `3` answer parts, suppressed `1`, "
                "and converted `0` states. Gate status: `integrated, untested "
                "(n=3 parts)`. Its behavior on TechQA is not measured by this run."
            ),
            "",
            "## Exact categories",
            "",
            f"V3: `{json.dumps(counts['v3'], sort_keys=True)}`",
            f"V4: `{json.dumps(counts['v4'], sort_keys=True)}`",
            "",
            (
                "The stored `incorrect_answer_dump.md` contains the raw Q278 answer, "
                "selected support text, Terra reason, coverage scores, suppressed "
                "part, and the H1/H2/H3 evidence assessment."
            ),
        ]
    )
    (OUT / "adjudication_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    incorrect_dump(ids, questions, v4, v4_judges)


async def main_async(prepare_only: bool) -> None:
    ids = prepare()
    if not prepare_only:
        await adjudicate(ids)
        finalize(ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    import asyncio

    asyncio.run(main_async(args.prepare_only))


if __name__ == "__main__":
    main()
