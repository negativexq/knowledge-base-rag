# Ten unseen questions after numeric input recovery

Frozen sequential run on 19 October 2026, main revision `2c659dc`.
All ten rows were absent from the preceding 65-question adaptive ledger and all
local adaptive row profiles. Selection used question text and document identity,
not labels or reference pages. Rows were frozen before execution:
398, 730, 1014, 509, 227, 829, 379, 659, 1070, 831.

GPT-6 Luna, fast path, evidence needs, independent after-run review and the same
10-request / 120,000-token / 240-second limits were retained. Runtime hashes
matched before every question. No runtime edits, substitutions or reruns occurred.
Embeddings, retrieval and indexing were unchanged. Answers were inspected only
after all ten finished. This remains source-document-scoped evaluation.

**Outcome: seven source-supported answers, three unresolved outcomes.**

| Row | Published result | Main seconds / requests | Assessment |
| --- | --- | --- | --- |
| 398 | 5 appendices | 65.03 / 9 | Correct; rejected count-mode draft repaired before release. |
| 730 | Abstention | 81.36 / 7 | Label-compatible but incomplete inspection; no confirmed absence receipt. Not a verified refusal. |
| 1014 | USD 11,749 million | 59.93 / 9 | Correct: 6,692 + 2,642 + 2,415. Missing unit header recovered with image/context. |
| 509 | 4 Greater Houston markets | 37.82 / 5 | Correct: numbered markets 15 through 18, inclusive. |
| 227 | 56 percentage points | 34.57 / 6 | Source-supported: college-graduate 65+ cell-phone ownership 87% minus tablet ownership 31%. Label is 301; discrepancy retained. |
| 829 | 2 yellow-highlighted lines | 37.76 / 5 | Original first-page image supports two. Extra explanation/citations do not meet strict integer-only presentation. |
| 379 | 14 board memberships | 41.65 / 7 | Source-supported R.A. Shah entity/role/table binding. |
| 659 | Port 1, pin P1.1 / T2EX | 30.79 / 3 | Correct direct text lookup; no tool call. |
| 1070 | Abstention | 69.99 / 7 | Answerable; correct financial inputs found, identity review and repair remain unresolved. |
| 831 | Motivation interview/team activities | 25.65 / 3 | Published partial answer; other requested Quarter 3 activities omitted despite available evidence. |

## Remaining failures

**730 — incomplete search is not confirmed absence.** The first image collector
proposed 496753 from a Germanwings-wide chart while explicitly observing that it
was not attributed to Boeing. Independent review rejected that binding. Subsequent
inspection covered pages 20–21 without finding the requested source object, and
coverage stayed incomplete. No number was published. The reference is unanswerable,
but its empty reference-page list provides no original images to the separate
reviewer. Agreement with that label cannot certify a clean refusal or a complete
whole-document search. Record this as unresolved coverage, not a wrong number or
a proven document-wide absence.

**1070 — source identity and repair.** Consolidated gross-profit/revenue values
were extracted correctly: FY2022 11,640/51,761; FY2021 10,573/47,262. All four grouped
numeric displays normalized successfully. The checker could not establish Best
Buy identity from the isolated table rows. A subsequent selector retained the
same table and added context IDs E1.S46/E1.S3, but the repair span raised ValueError
before a replacement quantity record was produced. The span does not record the
exception message, so the exact guard is not established by that span alone.
Do not attribute this failure to Decimal conversion or assert an unproved specific
exception code. The recorded formula is FY2021 margin minus FY2022 margin, about
−0.12 percentage points. The label `0.12%` omits direction/unit semantics; no answer
was released, so this remains a workflow miss regardless of label adjudication.

**831 — supported statements can still form an incomplete answer.** The released
answer accurately describes motivation interview/team activities, but leaves out
supplier research/comparison, investigating a local small business and selecting
a frequently used product under the Quarter 3 scope. These tasks are present in
selected E2.S1 and the original-page review. Both answer and scope checks passed,
so this is an acceptance/coverage defect rather than demonstrated retrieval loss.
No tools were called. Broader scope coverage needs to apply to the direct path as
well as structured lists; this run does not implement that correction.

## Source checks and limits

Independent after-run review compares answers with original reference-page images.
It supports all seven published successful answers. For 227, the images show 87%
and 31% for college graduates age 65+, supporting 56 percentage points; the stored
label 301 is retained as a discrepancy, not used to override source values.
For 730, the reviewer sees no original images because reference pages are empty;
its trace-level support boolean is not treated as a verified absence.

The earlier numeric display/absence exception was not reproduced. This batch is
not proof of zero regressions. Successful financial reads, visual counts, entity
resolution and a direct pin/function lookup coexist with the failures above.
The correct appendix and market counts do not close the earlier USB-inventory
false-completeness defect.

Main time totals 484.55 seconds; sequential wall time including startup and separate reviews is 770.52 seconds. Main usage: 61 requests, 207,845 input tokens, 27,376 output tokens, 16,211 cached input tokens, 13 tool calls and 1 diagnostic retry. Dollar cost is unavailable because price metadata is not configured. Separate review usage is excluded. Raw results, captures, spans and frozen selection remain local and ignored.

## Issue audit addendum

Audit addendum, 20 October 2026: the later [code-and-state audit](../../../docs/adaptive-issue-audit.md) inspects `ResearchState.needs`, which retains the exact error omitted from content-free spans. Row 1070 raises `REPAIR_CHANGED_UNTARGETED_STRUCTURE`. Its replacement formula has the same AST but changed parentheses and interpretation text. The original statement about the span alone remains true; the exact guard is now established by state and offline replay. Issuer context is still unresolved, so successful merge alone would not certify release.
