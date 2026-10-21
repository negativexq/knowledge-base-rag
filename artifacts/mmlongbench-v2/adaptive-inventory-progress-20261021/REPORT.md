# Document inventory: final implementation and measured outcome

Date: 21 October 2026. Branch: `fix/checked-inventory-progress`, based on main `43d2f98`.

## Final outcome

Row 662 now publishes **9 waveform figures**, on physical PDF pages **["11", "12", "13", "16", "18", "20"]**, with successful validation. Independent original-PDF inspection agrees. The frozen sequential control, row 382, retains the correct answer **2 quizzes**. This promotes one existing question: historical coverage is **101/120 (84.2%)**, comprising 81 source-supported answers, two qualified calculations, 18 correct refusals and 19 unresolved outcomes. This is a historical ledger, not a fresh full-suite benchmark.

## Final workflow

The existing need planner identifies document-wide counting. A single selector sees a labeled overview of every page and native location hints; it records inspect/exclude/uncertain decisions for every page and the counting unit. The application dispatches bounded windows without repeated selection. Narrow low-effort extraction returns only local occurrences and source witnesses. Typed state checkpoints each window before checking, preserves successful extraction across interruption and deduplicates source occurrences without merging equal labels on different figures.

One independent medium-effort review checks the supplied detail images and whole-source overview, separating local input accuracy, local coverage, whole-source coverage and operation. Only complete supported results become a count. The application computes both the total and unique ascending physical-page list. Final semantic scope remains independent and receives original images plus the actual published count/page list. Arithmetic execution checks remain active; no completeness requirement is bypassed.

The final count projection fixes an application handoff error: hiding the computed count from semantic coverage made the judge report an absent count/page list despite their presence in the prepared answer. Count answers now remain visible while execution proof is handled in code. Arithmetic projection is unchanged.

The overview route is bounded to at most 36 pages and one authorized immutable source. Larger documents, 636 and 663 have not been newly validated. Checked observations alone never certify whole-document completeness.

## Final frozen sequential measurement

Unchanged embedding, retrieval, reranking, index and global budgets: ten model requests, 120,000 tokens, 240 seconds. Extractor uses the existing low-effort role; planning and review use medium. No paid after-run judge. All application and harness hashes remain unchanged throughout this pair.

| Row | Result | In-run seconds | Process seconds | Requests | Input/output tokens |
| --- | --- | ---: | ---: | ---: | --- |
| 662 | Correct: 9 figures; six distinct pages; validation passes | 104.89 | 118.05 | 6 | 60,248 / 5,678 |
| 382 | Correct: 2 quizzes; validation passes | 110.06 | 125.20 | 8 | 80,997 / 6,682 |

662 uses two extraction windows, one combined quantity check and one final scope check, with no repair or retry. Its 104.89 seconds are approximately 48% below the first accumulation attempt's 201.83 seconds, but the control is slower than before. These are single development observations, not a causal latency estimate. API dollar cost is unavailable because model prices are not configured.

### Remaining latency

| 662 step | Seconds |
| --- | ---: |
| Need planning | 5.23 |
| Whole-source page planning | 38.57 |
| Two narrow extractions combined | 7.81 |
| Quantity/coverage review | 16.22 |
| Final scope review | 21.98 |

Page planning and the two reviews consume approximately 73% of end-to-end time. Extraction is no longer the main bottleneck. Review responsibilities should be separated precisely before removing any duplicate model work; independent source coverage must remain checked. Smaller typed payloads and compact planning output are candidates for measurement, not established savings.

382 still follows two selector/collector/checker cycles: selectors total 21.06 seconds, collectors 41.41 seconds, quantity checks 22.83 seconds, final scope 12.14 seconds. Replanning and repeated collection are the main opportunity in that path. Its previous first-phase control was 68.71 seconds / five calls; correctness passes but latency regresses in this observation.

## Retained unsuccessful attempts

| Attempt | Row 662 outcome | In-run seconds | Requests |
| --- | --- | ---: | ---: |
| Initial accumulation | Six findings retained; no whole-source closure; abstention | 201.83 | 9 |
| Planned windows | Nine findings found; contradictory local output contract blocks operation | 127.60 | 9 |
| Narrow windows | Nine findings approved; application span crashes on overview page metadata | 74.13 | 5 |
| Verified windows | Correct prepared result hidden from semantic coverage; repair loop ends without publication | 148.52 | 9 |
| Visible answer, final | Correct count and page list published | 104.89 | 6 |

The contract contradiction, overview span handling and count projection are corrected generically. Failed results remain local, alongside final spans and captures; only this Markdown report is intended for version control.

## Final verification

Full suite: **2,434 passed, four skipped, five deselected** (52.09 seconds). Ruff passes; mypy passes for 166 source files. Tests cover checked accumulation, conflict/source/version/visibility boundaries, local versus global completeness, interrupted review resumption without retranscription, application count/page output, original-image semantic scope and normal/compact verification. No source or budget change was made during the final pair.

## Historical first-phase report

The following is retained as the original unsuccessful first-stage observation; its unresolved status and totals are historical and superseded above.

# Checked inventory progress: first implementation and measurement

Date: 21 October 2026. Branch: `fix/checked-inventory-progress`, based on main `43d2f98`.

## Outcome

The application now retains independently checked count occurrences across windows in typed `ResearchState.inventories`. Pending observations cannot erase or become checked findings. A sequential 662/382 measurement demonstrates six retained checked occurrences across two windows in 662 and the unchanged correct count of two quizzes in 382. **662 is still unresolved**, and latency is unacceptable: 201.83 in-run seconds / 220.79 process seconds. No accepted-question count is increased.

This delivers the accumulation and checkpoint part of the [inventory loss audit](../../../docs/adaptive-inventory-loss-audit.md), not the complete document-inventory workflow. Remaining-page planning, bounded deterministic continuation and combined count/page-list publication remain open. No completeness check was relaxed, no expected answer was encoded and no budget was increased.

## Implementation

- Each count window keeps its own draft, bindings and independent review. A separate typed progress record contains window statuses and references to independently supported source occurrences. It is an application data structure, not an LLM summary.
- The accumulator groups only the same need, source and immutable version. Equal labels on different source occurrences remain distinct. Repeated identical source locators are deduplicated; contradictory readings at the same locator are excluded and recorded as conflicts. Semantic aliases are not guessed.
- The initial draft is checkpointed as pending before checking. Supported inputs are accumulated independently of global coverage. A failed or interrupted later window does not overwrite previous checked findings.
- Model context resolves references against current visible authorized sources and current review status. Checked partial occurrences and observed positive pages are exposed separately from complete quantities. Pending drafts are represented as pending windows, not verified facts. A bounded view explicitly reports omitted occurrences.
- `quantity.inventory.progress` spans expose checked-item count, pending-window count, conflict count, physical pages and the explicit lack of whole-source completion. No raw source content is put into spans.
- For image-backed inventory calls, the model still receives every native source line and line ID but not duplicate font/box metadata for hundreds of OCR glyphs. Original page images remain unchanged; full native geometry and text remain in state for deterministic membership checks. Text-only inventory behavior is unchanged.

This is not yet a resumable global page queue. A pending checker result is preserved; automatic resumption of that checker is not implemented by this change. Neither accumulated observations nor search exhaustion certify guide-wide completeness.

## Frozen sequential measurement

Same model profile and budgets: ten main requests, 120,000 tokens, 240 seconds, unchanged role efforts. Rows run sequentially with `--fast-path --evidence-needs`; no paid after-run judge. All application Python files and harness hashes remain unchanged during the pair. Raw results, spans, captures and source freeze stay local/ignored.

| Row | Result | In-run seconds | Process seconds | Requests | Input/output tokens |
| --- | --- | ---: | ---: | ---: | --- |
| 662 | Safe abstention; six checked occurrences retained, full scope incomplete | 201.83 | 220.79 | 9 | 81,080 / 9,463 |
| 382 | Correct: two quizzes | 68.71 | 83.42 | 5 | 48,944 / 3,453 |

In 662 the first window is pages 11, 14, 17: three waveform diagrams on page 11. The second is pages 5, 13, 16: two waveforms on 13 and one on 16. Both reviews support the extracted inputs and reject whole-guide completeness. The accumulator keeps all six, with no pending window or collision. Positive observed pages are 11, 13 and 16. Pages 12, 18 and 20 are still missing from image inspection. Unlike the audited preceding attempt, the second checker actually runs; there is no TOKEN_RESERVE stop before that review.

The second reviewer also objects that the new draft omits the old page-11 items. This exposes an interface mismatch: source-local checking still receives the previous whole-draft repair contract, although application state now accumulates windows separately. A dedicated window-coverage contract must separate checking new observations from closing global scope. Re-showing every old image is not the intended solution.

After the narrow collection ends, one generic reader searches again. The finalizer sees the partial findings and safely abstains. The run stops at REQUEST_RESERVE. A subsequent search finds a section spanning pages 20–21, but no remaining image/check budget is used to inspect its actual waveform page. No final count or exhaustive page list is claimed.

### Row 662 timing

| Model step | Seconds |
| --- | ---: |
| Need planner | 15.86 |
| First source selection | 18.61 |
| First collection | 22.03 |
| First independent check | 26.87 |
| Second source selection | 19.64 |
| Second collection | 14.90 |
| Second independent check | 39.76 |
| Generic reader | 3.09 |
| Finalizer | 14.03 |

Model calls total approximately 174.8 seconds. The remaining in-run time includes retrieval, rendering and application work; process time additionally includes startup. This single pair is not a causal latency comparison: the selected windows and model reasoning differ from earlier runs. The accumulation fix does not solve latency. API dollar cost is unavailable because model prices are not configured.

## Next work, before another long paid run

1. Replace global-repair semantics for document counts with explicit local-window input/coverage checks. Preserve the independent completeness check at the correct scope.
2. Plan candidate source pages once, retain uninspected/uncertain candidates and let the application dispatch bounded windows. A location catalog must not be treated as proof that excluded pages contain nothing relevant.
3. Carry accepted windows forward without a new selector or repeated transcription. Budget checks must account for the complete collect/check unit before starting a new window.
4. Only after source scope and counting unit are independently established, derive count and the distinct ascending page list from the same checked inventory in code. No general finalizer should be needed to rephrase an already complete result.
5. Remeasure 662 and the count control sequentially after this flow is concrete. Do not raise global budgets or force an incomplete inventory through validation.

## Verification

The initial accumulation implementation passed the full suite (2,423 passed, four skipped, five deselected). The subsequent image-payload reduction and per-checkpoint span integration passed 103 focused inventory/routing/provenance/fast-path tests. Ruff and mypy pass. The final full suite passes **2,424 tests**, with four skipped and five deselected (55.53 seconds). Tests cover disjoint windows, repeated labels on different pages, repeated source occurrences, conflicting readings, pending/rejected windows, source/version/need isolation, hidden/stale sources, JSON state roundtrip and a real collection/checker budget-stop sequence. Every original source line remains in the compact image payload; geometry stays in raw state.

Historical coverage remains **100/120 accepted outcomes, 20 unresolved**. README is unchanged.
