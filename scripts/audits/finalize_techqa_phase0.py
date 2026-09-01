"""Render the artifact-only TechQA Phase 0 forensic report."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/ragbench/canonical/techqa-phase0-forensics"


def read(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def main() -> None:
    integrity = read("source-integrity.json")
    contract = read("output-contract-accounting.json")
    critical = read("critical-summary.json")
    section = read("sectionaware-summary.json")
    latency = read("latency-attribution.json")
    decision = read("decision.json")
    next_action = read("next-action.json")
    target = read("sectionaware-target.json")
    report = f"""# TechQA Phase -1 / Phase 0 Forensics

## Integrity

- Dataset: RAGBench TechQA, pinned revision `{integrity['revision']}`, test split.
- DEBUG50 sample: `{integrity['debug_sample_hash']}`.
- HOLDOUT50: `{integrity['holdout_sample_hash']}`, frozen identity-only and untouched.
- Provider/retrieval/inference calls in this task: all zero.

## Holdout

The holdout was selected mechanically from the pinned test split after first-row-per-ID deduplication, excluding DEBUG50, with `random.Random(4242)` and first 50 eligible rows. Intersection is zero; no holdout content was used for tuning or forensic analysis.

## Structured output / state contract

Native Responses API `json_schema` with `strict=true` was already enabled. All 11 target raw payloads were syntactically valid JSON and provider responses were completed; all 11 were `abstain=true` with non-empty `answer_parts`. The provider schema permits that combination, while the application parser rejects it. Thus the dominant issue is an under-modeled application answer/abstain state machine, not a JSON/provider integration gap.

Provider schema state machine encoded: **NO**. A future conditional/discriminated schema is feasible, but was not changed here.

## Accounting

| Stage | Count |
|---|---:|
| Raw provider complete | {contract['raw_provider_complete']}/50 |
| Valid JSON | {contract['valid_json']}/50 |
| Native schema valid (artifact evidence) | {contract['provider_schema_valid']}/50 |
| Application contract valid | {contract['application_contract_valid']}/50 |
| Answer parts present | {contract['answer_parts_present']}/50 |
| support_ids field present | {contract['support_ids_field_present']}/50 |
| Non-empty support IDs | {contract['support_ids_non_empty']}/50 |
| Support identity valid | {contract['support_identity_valid']}/50 |
| Critical valid | {contract['critical_valid']}/50 |
| Citation resolved | {contract['citation_resolved']}/50 |
| Visible | {contract['visible']}/50 |

`24` visible differs from `14` fully-valid support-ID visible because the renderer preserves valid answer parts from queries with rejected sibling parts or critical-value failures. The latter is the stricter all-parts/all-checks count, not the partial-survival visibility count.

## Critical values

- Affected: {critical['affected']}; blocking: {critical['blocking']}; non-blocking: {critical['non_blocking_controls']}.
- Relation totals: {critical['relation_totals']}.
- Artifact-only primary labels: {critical['labels']}.
- Current scope: {critical['current_scope']}.
- Recommended forensic scope: {critical['recommended_scope']}.

## SectionAware offline replay

The BGE-all → current-SectionAware-not-all target contains {target['actual']} queries. The replay applies the same 1200-word budget proxy to persisted BGE Top5 text; strict-anchor mode reserves anchors first and does not add expansion after the reservation. It does not access Qdrant or hidden source text.

| Mode | Target ALL | Target mean recall | Annotated ALL | Annotated mean recall |
|---|---:|---:|---:|---:|
| Current persisted | {section['target']['current']['all']}/10 | {pct(section['target']['current']['mean_recall'])} | {section['annotated_subset']['current']['all']}/38 | {pct(section['annotated_subset']['current']['mean_recall'])} |
| Anchors only | {section['target']['anchors_only']['all']}/10 | {pct(section['target']['anchors_only']['mean_recall'])} | {section['annotated_subset']['anchors_only']['all']}/38 | {pct(section['annotated_subset']['anchors_only']['mean_recall'])} |
| Strict anchor preserving | {section['target']['strict_anchor_preserving']['all']}/10 | {pct(section['target']['strict_anchor_preserving']['mean_recall'])} | {section['annotated_subset']['strict_anchor_preserving']['all']}/38 | {pct(section['annotated_subset']['strict_anchor_preserving']['mean_recall'])} |

All ten target anchor sets exceed the 1200-word proxy budget, so the offline result supports an anchor-feasibility/relation follow-up rather than claiming expansion eviction. Preregistered gate: `{section['gate']}`.

## Latency

The largest measured non-Luna stage is `{latency['largest_measured_non_luna_stage']}`. E2E wall-clock is not persisted as a separate per-query timestamp, so unattributed overhead and explained fraction are reported as not measurable rather than fabricated.

## Decision

- Primary availability bottleneck: `{decision['primary_availability_bottleneck']}`.
- Secondary bottleneck: `{decision['secondary_bottleneck']}`.
- Single next action: **{next_action['action']}**.
- Expected future inference for that action: `{next_action['expected_next_inference']}`.
- DEBUG50 is development-only; HOLDOUT50 is frozen for the future architecture verdict.
- TechQA findings are specific to the Luna/OpenAI canonical provider path and do not transfer automatically to Qwen/Ollama.

No production behavior was changed.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"report": str(OUT / "report.md"), "decision": decision, "next_action": next_action["action"]}, sort_keys=True))


if __name__ == "__main__":
    main()
