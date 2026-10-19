# Open adaptive workflow issues

Recorded on 19 October 2026. The issue families below track open work and partial fixes; implemented changes
and measured outcomes are identified explicitly. Three disjoint ten-row batches used one frozen runtime. The second added NUM-001;
the third reproduced numeric/type failures and added a counting-unit finding.

## INV-001: Page completion is mistaken for inventory completion

**Observed case:** row 476, USB data-exchange functions. The application published
five instead of nine. Original physical page 56 contains five functions; page 57
continues with four more. The collector marked the group complete based on the
last item, blank page area and footer. Independent input/coverage review accepted
that boundary. With no coverage objection, source-gap completion was not invoked.

**General failure:** the application can execute an item count without a separate,
source-grounded receipt establishing closure of the requested inventory. A page
boundary does not establish a category or section boundary. Accurately transcribed
items can therefore form an incomplete but incorrectly accepted whole-list answer.

**Proposed correction:** retain item observations separately from inventory
closure. Record the requested source object, inspected ranges and actual boundary
evidence. Inspect a bounded continuation when closure remains unknown, using the
same shared budgets and preserving extracted items. A new section/category heading,
explicit source end marker or source-stated total can support closure; footer/blank
space alone cannot. Do not add document-specific page or expected-count rules.

**Acceptance evidence:** offline tests for a same-section page continuation, an
actual next-section boundary, an inventory ending before a page footer, and a
budget stop with preserved partial observations. Recheck the failure and additional
unseen inventories; a single corrected case is not generalization evidence.

## ROUTE-001: Textual key matching is routed as numeric conditional lookup

**Observed case:** row 508, geographic market for EPS Code AR03. The initial
source was Alabama page 7 and the proposed value Mobile belonged to AL03. The
collector used the numeric conditional-lookup contract, inserting string codes
and names into numeric operands and comparison choices. Input review rejected
the binding and operation. Repair then failed the output contract with
`UnexpectedModelBehavior: Exceeded maximum output retries (0)`.

Direct post-run inspection of original physical page 8 confirms the Arkansas
listing contains AR01 (Little Rock) and AR02 (Northern Arkansas), then changes
to New Mexico. The final abstention is source-consistent, but the error-terminated
workflow is not recorded as a clean supported refusal.

**General failure:** textual key-to-value matching and numeric conditional lookup
lack a sufficiently clear dispatch/type boundary. A structurally valid draft can
still route strings through a numeric comparison plan. A missing match, an
unreadable entry and a failed tool output are also distinct terminal conditions.

**Proposed correction:** separate source key matching, numeric extreme selection,
and comparison-driven value lookup by their input/output types. Check operation
compatibility before dispatch and numeric validity before computation; keys such as
catalog codes remain strings. Represent source-grounded no-match, incomplete
inspection and tool failure separately. Preserve exact entity/key bindings and
authorized source scope. Do not add code-prefix, state-name or benchmark-row rules.

**Acceptance evidence:** matching and absent textual keys, near-identical keys,
numeric-looking identifiers, numeric comparisons, conditional value joins and
malformed tool results. Verify ordinary direct lookups still use the fast path.

## NUM-001: Noncanonical or missing numeric input aborts before review checkpoint

**Observed cases:** rows 471 and 1026 in the
[second frozen ten-question batch](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md).
Row 471 supplied `Not stated; yellow is not listed` as the value of a numeric read
operand and marked it complete. Row 1026 supplied the accounting display `(495)`
as its numeric value. Decimal conversion raised `InvalidOperation` in both runs.
The first refusal is consistent with the original milk-nozzle legend, while the
second question is answerable: Costco reported approximately USD 495 million spent.

**General failure:** source-display strings, canonical numeric values and absence
of a value are not sufficiently separated in the read contract. Provisional
execution occurs after the checker returns but before its assessment is saved.
Only `ValueError` is handled locally, so a Decimal exception skips the review
checkpoint and the possible interpretation/source-repair route. In row 1026 the
checker had already identified the signed equity reduction versus positive
spending-magnitude distinction, but the assessment was not retained in the typed
receipt when numeric conversion failed. The original draft and raw model outputs
remain available.

**Implemented correction:** distinguish readable numeric values, source-grounded
absence, unreadability and tool failure; preserve the original display while
validating a separate canonical number. Save independent review before provisional
execution, and record numeric-conversion failure as typed data rather than losing
the review. Accounting sign normalization must not silently decide whether the
question requests signed movement or spending magnitude. Keep source checking,
interpretation and arithmetic as separate responsibilities.

**Acceptance evidence:** ordinary and parenthesized numeric displays, unavailable
values, incompatible numeric strings, checker objections followed by conversion
failure, and successful extraction surviving finalization after an execution
error. No expected amount, color or document-specific rule belongs in runtime code.

**Measured status:** partially corrected. The [four-row recheck](../artifacts/mmlongbench-v2/adaptive-numeric-four-20261019/REPORT.md)
finishes 471 and 388 with accepted typed absence and no execution exception.
1025 preserves its accepted assessment but rejects the valid `000s` spelling;
1026 rejects accounting parentheses under canonical separator notation and then
stops on a checker `ModelAPIError`, before any returned assessment. These two
new boundary defects were corrected in the follow-up. Accounting sign
handling is now independent of separator notation, common thousand-unit spellings
are supported, and identical explicitly scaled source/output units resolve default
multipliers deterministically without changing the displayed unit. The [separate frozen pair](../artifacts/mmlongbench-v2/adaptive-numeric-pair-20261019/REPORT.md)
publishes 495 million dollars and 1,358,000 shares, with independent original-PDF
support. The live share-count draft uses `thousand shares`; `000s` itself is
verified offline, not isolated by that successful live run. The previous checker
API error did not recur; its cause is not established. All four original NUM-001
examples have successful outcomes across two revisions. Wider numeric/routing
stability remains unproven. No previously successful live
controls have been rerun; offline contracts do not establish zero regressions.

## VIS-001: A requested visual condition can be falsely accepted

**Observed case:** row 635, grey-background execution-function names. The released
Fact Checker answer is incorrect: original Figure 1 has blue Fact Checker, pink
QA Model and green Logical Reasoner boxes. The collector described blue as
“pale gray-blue” and independent input review accepted it. The after-run reviewer
had no image because the reference-page list is empty. Direct original-page
inspection identified the mismatch. See the
[three-row report](../artifacts/mmlongbench-v2/adaptive-evidence-completion-20261019/REPORT.md).

**Status:** open semantic visual-condition defect. Row 475 is a successful control:
the same runtime rejected a green-bar time as unsupported for a red-bar question.
One correct rejection does not prove reliable color-condition checking.

## COUNT-001: Merged-table counting unit and membership need adjudication

**Observed case:** row 658 in the
[third ten-row report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md).
The published answer is four N-associated part names; the reference is two. The
automatic original-page reviewer agrees with four, but direct source inspection
shows two explicit N entries and merged/grouped part/package cells. Counting
prefix entries and counting named parts are different operations, and the
membership implied by the merged layout is not conclusively established by this
audit. Neither automatic reviewer agreement nor the reference value settles it.

**Status:** unresolved verification finding, not a confirmed arithmetic defect or
an assertion that the benchmark label is wrong. Establish the requested counting
unit and original-table membership before adding this row to the success ledger.
Do not introduce an expected count into the runtime.

## SRC-001: Waveform baseline is not explicitly annotated

**Observed case:** row 661, reference answer 0.0 V for the P2.7 ENABLE waveform
baseline. The trace does not explicitly annotate that voltage. A later proposed
VSS interpretation was not independently established. See the
[unseen-ten report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md).

**Status:** source-evidence limitation requiring adjudication, not proof that a
model must be forced to output the reference. Keep it separate from reproduced
execution failures and from reliable source-supported answers.

## Reproduction across the last thirty questions

The [three-batch comparison](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md)
uses 30 disjoint questions with identical runtime hashes. NUM-001 occurs in rows
471, 1026, 1025 and 388. In 1025, `(1,358)` produced a canonical-number ValueError;
its draft and review survived, but execution failed. In 388, `Not mentioned` was
used as a complete numeric-read value and raised Decimal `InvalidOperation`
before review checkpointing. Its person-name request also overlaps ROUTE-001.
The same type/representation family thus spans four source objects; its exception
handling paths are not identical. INV-001 remains confirmed only by row 476;
several other complete inventory counts passed without fixing that defect.

There are **five distinct unresolved questions/workflows**: 476, 508, 635, 658
and 661. Rows may overlap issue families; do not sum per-family
counts as if they were disjoint. Rows 220, 475, 471 and 388 are clean correct refusals,
tracked separately in the question ledger.

## Evidence and measurement policy

The [frozen ten-question report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md)
retains both failures. The [question ledger](adaptive-solved-questions.md) tracks
historical source-supported answers and unresolved workflows separately.
Subsequent runs must retain unsuccessful attempts, freeze code/settings during
each batch and avoid turning gold values or reference pages into runtime rules.
Raw JSON, captures, source renders and spans remain local and ignored.
