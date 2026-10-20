# Original-page context and resumable acquisition coverage

Date: 20 October 2026. Builds on the [protected-proof follow-up](../adaptive-result-reservation-20261020/REPORT.md).
The existing embedding model, index, reranker, data ingestion, model profile and shared
request/token/time/tool limits are unchanged. No benchmark gold values enter generation.

## Implementation

- Text quantity collection attaches literal native context from exactly the selected,
  authorized, immutable PDF pages before its first extraction/checker pass. Page lines
  preserve headings, units, period and footnotes when present. The new context carries
  physical-page support IDs and limited/line-count receipts; it is not an LLM summary.
  No title, unit or period is inherited from another page. Native reading order can
  still need image review; source/context/operation acceptance remains independent.
- Source-scale literal verification includes those authorized context sources, so a
  value's row and its separately quoted unit heading can support one checked operation.
  Existing explicit context has priority; full slots or evidence limits can still block
  additional context. Nothing is truncated to force admission.
- Page reads follow only reader-issued forward cursors within the existing shared
  tool/time limits. Typed PageReadCheckpoint records retain source/version/page,
  authorized chunks, visited offsets, next offset, scan-limit status and stop reason.
  A resumed request continues from that cursor. Cached chunks are reauthorized, and
  model context sees only coverage metadata plus admitted evidence, not buffered text.
- Grounded missing-object searches retain source/version/query/cursor receipts. A
  repeated identical gap advances past prior matches, retaining earlier candidates.
  Invalid cursors, scan limits or exhausted searches do not certify answer absence.
- These records establish acquisition progress, not automatic whole-document inventory
  closure. Independent semantic review remains required. A three-page image window
  cannot certify all figures in a 21-page guidebook.

## First frozen sequential measurement

`live-four`: **1086, 1017, 730, 662**, sequential. All application Python files and
unchanged harness were hashed before/after; the snapshot remains unchanged. Same
gpt-6-luna role settings, ten main requests, 120,000 tokens and 240 seconds. Separate
reviewers run after generation, outside the generator's context.

| Row | Released result | Main time | Main requests | Finding |
| --- | --- | --- | --- | --- |
| 1086 | **13,929 million dollars** | 51.27 s | 6 | Original page context establishes the scale in the first collection/checker pass. Prior selected confirmation needed nine requests and 75.66 s. |
| 1017 | Abstention | 88.03 s | 9 | Balance-sheet inputs and context survive; repair finds generic lease-accounting prose, not all required liability amounts. |
| 730 | Abstention | 30.42 s | 5 | Selected source does not establish Boeing's tweet count. This is not a newly certified document-wide absence. |
| 662 | Abstention | 85.62 s | 8 | Partial waveform inventory survives; selected windows do not establish all pages of the guide. |

The 1086 observation is a three-request reduction in this comparison, not a repeated
causal latency estimate. Its arithmetic and published amount remain source-correct.
No new distinct question or historical success is added by rerunning it. Failure rows
are not counted as successes merely because a reviewer approves cautious abstention.

## Remaining gap routing and follow-up

1017's first repair query concatenates all missing-evidence prose with the whole debt
question. It reselects a balance sheet and generic accounting discussion. When the
operation is independently supported and a question-grounded need exists, gap search
now targets the first named missing operand, scoped by the need's entity and period.
This avoids re-searching the full known calculation. The original question still governs
independent collection/review, and no expected value or document-specific term is inserted.
Without those typed conditions the existing question-grounded query remains available.

`missing-input-row1017` remeasures only 1017 under another frozen source snapshot.
Its result is recorded below after completion; the first four-row outcome is preserved.

## Coverage limitations

The page cursor and local search cursor defects are implemented and tested. The
21-page visual inventory still needs a multi-window semantic inventory/closure path;
this implementation does not claim that simple reader exhaustion solves it. Partial
windows and missing roles remain unresolved under the unchanged budget. Likewise a
bounded source lacking Boeing data is not automatically a document-wide absence proof.

Raw JSON, spans, captures, logs, PDF renders and source snapshots remain local/ignored;
only this Markdown report is tracked. gpt-6-luna pricing is not configured, so API cost
is unknown rather than zero. Historical coverage remains 120 distinct questions unless
a separately source-verified unresolved row is promoted below.


## Single-row follow-up: 1017

`missing-input-row1017` releases **USD 11,407 million**, **103.09 seconds, ten main
requests**. The application/harness source snapshot stays unchanged. The published
operation is `799 + 6692 + 222 + 2642 + 72 + 980 = 11407`.

The successful run does **not** exercise the new narrow gap-query path: its source
selector returns available=false, collection creates no quantity record, and the
general reader searches for the missing lease fields. The lease note becomes visible;
there are no quantity gap-search receipts. Thus this is source-supported answer
recovery, not proof that the gap-query change caused that recovery.

The trace reaches the correct six-input expression by request five. Two reader
outputs combine action=answer with text_calculation and fail the existing exclusive
action contract. A search repeats; the first finalizer also uses an overly broad
source locator and requires a second finalizer. Breakdown: one need planner, one initial
answer, one quantity selector, four readers, two finalizers and one scope validator.
There is no independently stored quantity computation in this path; answer arithmetic
is checked by the normal deterministic calculation validation. CALL-001 records the
remaining protocol/efficiency defect; ten requests are not intrinsic to the arithmetic.

Original COSTCO_2021_10K.pdf physical page 53, Note 6, independently prints 2021
current operating leases **222**, current finance leases **72**, long-term operating
leases **2642**, long-term finance leases **980**, total **3916**. The balance sheet
on physical page 38 prints current long-term debt **799** and noncurrent long-term
debt **6692**. The total is 7491+3916=11407 million. Separate after-run review agrees
with the source readings and released answer.

## Final validation and disposition

- **2,327 passed, 4 skipped, 5 deselected** (44.67 seconds); Ruff and mypy pass on
  160 application files; git diff --check passes.
- Tests exercise source/header/period handoff before first extraction, local exact
  magnitude conversion with original context, cursor continuation and checkpoint
  roundtrip, tool-budget stops, invalid/stalled cursors, foreign source exclusion,
  retained gap-search candidates and exhausted-search non-absence semantics.
- Historical totals: **79 supported / 2 qualified / 4 verified refusals / 35 unresolved**
  across 120 distinct questions. Only 1017 is a new historical source-supported answer.
- PROV-001 and COVER-001 are partially improved, not closed. Multi-window visual
  accumulation/closure, document-wide absence receipts, relationship joins and mixed
  action inefficiency remain open. Initial unsuccessful measurements remain preserved.
