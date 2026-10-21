# Numeric read presentation and proof handoff

## Result

Row 642 now publishes `["64.4", "62.5", "62.2"]`, grounded in Figure 4 on physical page 7. The checked source values are 64.35 (HOVER 2-hop), 62.23 (3-hop), and 62.46 (4-hop). Numeric ordering precedes display rounding. The stored benchmark label `[64.3, 62.4, 62.2]` does not match ordinary rounding of the original printed values; it is never supplied to generation or used to change the source reading.

## Defects and correction

The previous route selected a text list for numeric scores. Its application executor sorted whole labels alphabetically, undoing numeric order. Text lists also prohibit numeric precision. The existing typed `read` operation now accepts question-planned numeric order, retaining source numbers and labels separately. The application performs a stable Decimal sort over comparable converted values and rounds only the published display. Equal values and values that round alike are retained. Unknown readings and incompatible units cannot execute a numeric sort. Text lists retain their existing alphabetical behavior.

The first live batch exposed a second handoff defect: source collection and application sorting succeeded, but the generated proof contained only full-precision values. Local critical-value validation rejected the rounded display before semantic scope could run. The proof now contains both full-precision application results and deterministic presented values. This does not relax numeric validation: an offline forged nearby value is still rejected. Exact checked read candidates also pass their operation metadata and reviewed original images to the existing semantic scope call; source bindings and question conditions still require approval.

No embedding, retrieval, reranking, global budget, model effort or extra judge stage changes are involved. No question IDs, source scores or gold labels are encoded in runtime logic.

## Sequential measurements

All rows ran sequentially with `--fast-path --evidence-needs`, unchanged budgets and no paid reviewer. Application and harness hashes were frozen within each batch. Raw captures and spans remain ignored; the first unsuccessful attempt is retained locally.

| Batch | Row | Outcome | In-run seconds | Requests | Retries |
|---|---:|---|---:|---:|---:|
| Initial typed read | 642 | Correct prepared values withheld by local critical-value validation | 130.17 | 9 | 1 |
| Initial controls | 634 | Correct blue-background list: Fact Checker | 64.96 | 7 | 0 |
| Initial controls | 387 | Correct concise answer: Rick Scott | 34.27 | 3 | 0 |
| Initial controls | 1079 | Correct ratio: 0.627 | 47.34 | 6 | 0 |
| Display receipt correction | 642 | Correct source answer: [64.4, 62.5, 62.2] | 94.04 | 6 | 0 |
| Display receipt correction | 1076 | Correct cash amount: USD 1,874 million | 26.84 | 3 | 0 |

The final 642 route is planner → initial answerer → quantity selector → image collector → independent quantity checker → semantic scope. Application sorting, rounding and local validation require no model call. No repeated extraction, part repair or finalizer generation is needed. Scope independently verifies ProgramFC, F1, gold evidence and the 80M/FLAN-T5-small binding on the supplied original page. Process time including startup is 108.16 seconds; in-run time is 94.04 seconds. API dollar cost is unavailable because model prices are not configured.

These are five distinct previously tested questions, not new benchmark coverage. Historical totals remain 100/120 accepted outcomes, including qualified calculations; this targeted recovery does not raise the count. The three initial controls precede the small display-receipt addition; 1076 is a direct-answer control and does not exercise quantity collection. Offline tests cover scalar and vector read behavior directly.

## Verification and limits

Before the display-receipt addition, the full suite passed: 2,416 passed, four skipped, five deselected; Ruff and mypy passed. After that addition, 68 relevant numeric/authority/visual-scope tests and Ruff passed. Tests cover stable ties, duplicate rounded values, explicit decimal-comma notation, incompatible units, unreadable values, unchanged scalar/source-order reads and text lists, question-plan handoff without recollection, and local acceptance/rejection of generated numeric displays.

This resolves PRESENT-001 for the measured case. It is not a guarantee of arbitrary chart extraction or list completeness. Labels and full-precision values remain in typed state and proof receipts for semantic review. Global quality metrics remain historical question coverage, not a fresh 120-row rerun.
