# Typed collection routing and scope repair

Date: 20 October 2026.

## Changes and boundaries

A failed fast answer no longer dispatches numeric collection merely because fast mode
is enabled. Typed count/calculation needs own dispatch. The existing fast call can
identify a numeric lookup or source-list capability without another routing request.
Compatible lookup constraints and the correct need ID reach the collection tool.
Unknown and prose tasks continue bounded research.

Application-owned collection receipts retain status, need, record and source IDs.
An unresolved collection no longer automatically terminates research. Checkpointed
failed drafts cannot certify a repeated answer against unchanged evidence. Independent
facts, checked calculations and newly acquired sources remain available to finalization,
including after the tool budget closes. Scope-rejected quantity proofs are excluded
from the checked-result context.

Grounded scope objections distinguish missing source or contradiction from an existing-
source relationship, interpretation, unit transformation or presentation correction.
Existing-source repairs reuse authorized evidence and skip the selector. They still
undergo independent input review, application execution and final scope validation.
Unknown, mixed or invalid diagnostics retain freshness. This is dispatch, not an
implementation of the separate missing unit-conversion capability.

New spans: `research.collection.route`, `research.collection.resume` and
`quantity.repair.route`. No global prompt tightening, expected values, benchmark row
routing, embedding/index changes, retrieval changes or reranker changes were introduced.

## Validation

- Full offline suite: **2,259 passed, 4 skipped, 5 deselected** (42.22 seconds).
- Ruff passed; mypy passed for 157 application files; `git diff --check` passed.
- Tests cover prose routing, numeric lookup with retained constraints, failed-review
  continuation, blocked unchanged-source guesses, independent fact preservation,
  finalization after tool-budget exhaustion, all four same-source repair classes,
  missing/mixed/invalid diagnostics and independent rejection of a local repair.
- Two intermediate test-suite runs exposed mistakes in new test fixtures/assertions;
  both were corrected before the clean full run. They were not live production failures.

## Frozen sequential live regression

Rows: **508, 511, 517, 520, 214, 380, 637, 382, 477**, in that order.
All nine completed with saved results and separate after-run reviews. The complete
application Python tree and harness SHA256 snapshot remained unchanged throughout.
Local `live-nine/selection.json` records the hashes. Each generator run used gpt-6-luna,
fast path and evidence needs, 10 requests, 120,000 tokens and 240 seconds, with the
existing role-specific reasoning profile. Gold labels/reference pages were available
only to the separate after-run reviewer. No question received a source override.

| Row | Released result | Main time | Main requests | Assessment |
| --- | --- | --- | --- | --- |
| 508 | Abstention | 48.81 s | 6 | No numeric collection; search/read continuation. Source absence is not certified by this run. |
| 511 | Start new search | 64.00 s | 8 | Recovered through scoped original-image extraction, without numeric collection. Manually verified on physical PDF page 17. |
| 517 | Abstention | 52.99 s | 6 | No numeric selection/execution. Repeated text searches still fail to inspect the relevant map. |
| 520 | Abstention | 48.92 s | 9 | No numeric collection; source attribution remains unresolved rather than certified absent. |
| 214 | No verified answer | 113.85 s | 9 | Original image gives a checked 16-point calculation, but the question's 2018-start premise is not established. REQUEST_RESERVE and finalization failure remain recorded. |
| 380 | Abstention | 106.36 s | 9 | Income operand still missing; lakh-to-rupee output conversion also remains open. REQUEST_RESERVE. |
| 637 | 1 complete example | 64.74 s | 5 | Recovered; original physical page 5 / printed 6985 shows one complete example in the top figure. |
| 382 | 2 quizzes | 58.53 s | 5 | Correct control retained. |
| 477 | 7 quality levels | 49.92 s | 5 | Correct control retained. |

The four previously misrouted prose/qualitative cases (508/511/517/520) make no numeric
collection calls. Only 511 produces a new supported answer among those four. Row 637
also publishes a correct answer, while both controls remain correct. The other five
target outcomes stay unresolved; no abstention is promoted solely for matching a
Not-answerable label.

The live target rows do **not** exercise the new `existing_scope` repair branch: 637
succeeds without repair; 214 asks for genuinely unestablished premise evidence; 380
still lacks an income operand. Local repair reuse is verified offline, not claimed as
proven by these live rows. The nine runs are not a paired causal estimate of every
individual code change.

## Source and reviewer audit

- **511:** original `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf`, physical page 17, visibly
  contains an orange button labeled **Start new search**. The runtime selects that page
  and records image-checked extraction. The after-run reviewer did not receive that
  target page and therefore declined to certify it. Manual inspection resolves the
  review-packet gap without changing the run or trusting the benchmark label.
- **637:** original `2023.acl-long.386.pdf`, physical page 5 / printed 6985. The top
  Figure 2 has one complete claim/program example, followed by an ellipsis and an
  input-claim placeholder. The lower Figure 3 is a different object.
- **214:** the captured image operands are 65 and 49, producing 16.000; the earlier fast
  draft 46 minus 39 is not source-correct for strong disapproval. The label 7.0 is not
  used to override this extraction. The extra 2018-start condition remains unresolved.
- **380:** the second collection locates shareholders' funds, but not income. This is
  a source-acquisition gap as well as the separately tracked scale conversion issue.
- A reviewer's `answer_supported` flag is not used as a success score: it sometimes
  evaluates the source answer rather than the system's actual released abstention.

Main runs total **608.12 seconds, 62 model requests and 384,120 input/output tokens**.
The sequential wall time including startup and the nine separate reviews is 897.74
seconds. These timings include retrieval in each main run. The configured price table
has no gpt-6-luna entry; API cost is unknown, not zero. Review usage remains separately
recorded. Raw captures, result JSON, spans, logs and page renders remain local/ignored.

## Ledger and remaining work

Rows 511 and 637 move from unresolved to supported. The historical ledger now contains
**76 supported answers, one qualified calculation, four verified refusals and 39
unresolved outcomes across the same 120 unique questions**. Frozen full-set matcher
scores are unchanged. This is a targeted rerun, not a fresh 120-row score.

Next source-acquisition work should address modality selection for qualitative maps,
whole-page table context when indexed fragments are insufficient, and the already
tracked deterministic unit conversions. Source-scoped absence receipts, broader
inventory accumulation and remaining visual/population semantics also remain open.
