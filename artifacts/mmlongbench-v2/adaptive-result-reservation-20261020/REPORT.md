# Checked-result admission and finalization handoff

Date: 20 October 2026. Builds on the [unit arithmetic measurement](../adaptive-unit-arithmetic-20261020/REPORT.md).
No embedding, retrieval model, reranker, overall context budget, model setting, token
limit or request limit changes. Raw evidence capacity is repartitioned inside the existing total.

## Application changes

Adaptive wiring reserves one quarter of the existing evidence budget, capped at 6,000
tokens, before initial source admission. Ordinary chunks, page views and native text
cannot consume this reservation. Only checked proof publication after independent
review and successful deterministic execution uses it, retaining all witnesses,
lineage, units, numeric receipts, conversion and result. The total remains bounded;
oversized proofs fail atomically. ACL/source filters and whole-block admission apply
to both paths. Legacy non-adaptive sessions retain their previous allocation.

Completed results are checkpointed before proof admission. Admitted proofs let finalization
reuse the exact application candidate and run its required verification, avoiding another
answer-writing call. This does not establish truth by calculation alone. Admission spans
separate remaining ordinary-source capacity from total result-admission capacity.

Tradeoff: raw source accumulation has less capacity. Arbitrary proof size or many
completed records cannot be guaranteed to fit. We do not evict sources, shorten quotes,
increase limits or certify an unadmitted image transcription.

## First frozen sequential measurement

`live-three`: **1086, 380, 382**, sequential, gpt-6-luna with the unchanged harness,
budgets and role efforts. Application/harness hashes stayed unchanged. No gold labels
or reference-page overrides enter generation. Separate reviewers run afterward.

| Row | Released result | Main time | Main requests | Actual boundary |
| --- | --- | --- | --- | --- |
| 1086 | Abstention | 53.16 s | 8 | Checker suggests canonical notation for valid comma-grouped numbers. The correction guard throws before source-context repair can proceed. |
| 380 | No verified answer | 89.27 s | 9 | Correct image-checked calculation/proof is admitted. Final scope disputes the income binding based on indexed source text. |
| 382 | **2 quizzes** | 45.57 s | 5 | Checked count proof is admitted and published successfully. |

Sequential wall time including startup/reviews: **280.96 seconds**. Reservation alone
does not recover the arithmetic release cases. This failed intermediate is preserved.
The separate reviewer marks the cautious refusals as supported; that does not make these
successful numeric answers and does not certify absence in the source.

## Handoff corrections

An unusable notation suggestion no longer destroys an already valid printed value.
The application keeps the original format/value when the proposed format cannot parse
it. Equivalent formats may change metadata only; a valid alternative that changes the
numeric interpretation still raises the existing ambiguity guard. If neither parses,
normal failure remains. This does not change an unknown/mismatched input review into
acceptance: original source-context objections still require independent repair/review.

Arithmetic semantic projections now carry the same explicit image-input authority
already used for counts, plus the original image bindings (document/version/pages).
The final checker is told to assess source relationships and interpretation without
requiring independently checked image data to also appear in indexed/OCR text.
Concrete conflicting source bindings remain rejection grounds. Exact local reexecution,
conversion-receipt equality and positive scope/release checks remain mandatory.

`handoff-three` repeats 1086, 380, 382 sequentially after these changes under another
frozen source snapshot. That batch also does not recover the two arithmetic releases:

| Row | Released result | Main time | Main requests | Finding |
| --- | --- | --- | --- | --- |
| 1086 | No verified answer | 73.76 s | 10 | Checker accepts input scale, but literal proof lacks source scale context and execution is withheld. Subsequent repair/finalization cannot release. |
| 380 | Abstention | 79.74 s | 9 | Income remains unavailable in the supplied page view; incomplete source review correctly blocks execution. |
| 382 | **2 quizzes** | 46.81 s | 5 | Count control retained. |

Sequential wall time with startup/reviews: **298.30 seconds**. Source hashes remained
unchanged. Do not treat reviewer approval of a cautious refusal as numeric recovery.

## Complete page admission without duplicate expansion

The page-opening path previously admitted returned chunks, then admitted a second
concatenated page view containing the same text. Fragments could consume capacity
before the full heading/value view arrived. It now constructs one complete page view
from the authorized returned chunks and admits that once. Original chunk IDs remain
in lineage; original text is not summarized or cut. Tenant, source, version, page,
authorization and visibility checks run before combining any text, so a permitted
parent cannot launder a denied child into context. Partial/scan-limited reads remain
partial and are not cached as complete. Oversized complete views can still be rejected.

`page-pair` remeasures **1086 then 380**, sequentially, after the page-admission change.
The count path is unchanged by this acquisition helper and its two successful control
runs remain recorded separately. The first two batches are not rewritten.

## Offline checks

Tests cover full raw capacity with a protected original-image proof, state roundtrip
and finalization without another answer model, rejected input review, oversized and
duplicate proofs, tenant/source authorization and the unchanged total ceiling. The
notation regression retains a valid comma-grouped source display and its million scale
without promoting an unknown source review. Existing tests retain rejection of
numerically different interpretations, invalid corrections and stale/tampered results.

Raw JSON, captures, spans, logs and source hashes remain local/ignored. Only this
Markdown report is tracked. gpt-6-luna pricing is not configured; cost is unknown.
Historical distinct-question coverage remains 120; repeated controls add no questions.


## Page-pair outcome and acquisition regression

The frozen `page-pair` snapshot stays unchanged. Row **380 recovers**:
**8,367,277,000 rupees**, 63.81 seconds, six main requests. Correct source readings,
scale factors and result are stored; the checked proof is admitted and the final answer
released. Separate review supports it. Total pair wall time with startup/reviews is
187.41 seconds.

Row **1086 still abstains**, 56.01 seconds and ten requests. Its collection failure is
an implementation regression in the new page-view handoff: paragraph separators split
the complete view into 21 support IDs, exceeding PageAcquisition's three-ID contract.
It fails before extraction; later generic text calculation lacks unit context, and
scope review rejects the million-unit answer. This is not a successful reserved-proof
test and is not concealed by the reviewer's support for a cautious refusal.

The correction uses the existing complete-page reading convention: paragraph separator
blank lines become single line breaks, preserving every word and source line while
keeping a page reading as one support unit. No quote is shortened or summarized. The
regression test includes separated paragraphs, verifies both values survive, and checks
that denied child text remains absent. A new frozen `page-unit-row1086` run measures
only 1086 after that correction; prior outcomes remain preserved.


## Final single-row confirmation

`page-unit-row1086` releases **13,929 million dollars**, **75.66 seconds, nine main
requests** (103.05 seconds including startup and separate review). Application/harness
hashes remain unchanged. The path is planner → initial answer → text selection/extraction/
review → image selection/extraction/review → final scope validation. The first input
review cannot establish scale; the image repair independently establishes it. The
application computes `(15803*1000000 - 1874*1000000)/1000000 = 13929`, admits the full
checked proof, and releases the prepared candidate. There is **no finalizer answer-writing
call**. Separate review supports the released answer; its supplied reference image is
still not the full target balance-sheet context, so the earlier independent manual source
checks remain relevant rather than treating reviewer approval alone as original-source proof.

This confirms publication recovery for 1086. The final page-unit normalization was
remeasured only on 1086; 380's successful six-request result is the preceding frozen
pair, not a claim of a final same-snapshot two-row pass. The two successful count controls
are likewise their recorded snapshots. Historical coverage remains **78 supported /
2 qualified / 4 verified refusals / 36 unresolved**, across the same 120 questions.

Remaining optimization: the text pass can still omit financial-statement scale context
and require a selected image repair; 1086 retains two selection/extraction/review passes.
We do not skip source selection from an untyped assumption about the missing context.
The fix removes proof-admission loss and duplicate page-view charging, not every
possible extra call or every scope/interpretation failure.

Final validation: **2,317 passed, 4 skipped, 5 deselected** (50.80 seconds); Ruff and
mypy pass on 159 application files. `git diff --check` passes. No new standalone
benchmark score is inferred from these targeted reruns.
