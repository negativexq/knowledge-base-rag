# Adaptive issue audit

Audited on 20 October 2026 against main `2c659dc` plus documentation-only changes.
This is a code-and-trace audit, not a new paid benchmark run. Application and trace
harness hashes still match the completed frozen runs. No runtime fixes are included.

## Conclusion

The issue list mixed product defects, strict audit incompleteness, reference
ambiguities and historical bugs already contained by code. It also missed concrete
repair failures visible in `ResearchState.needs`. The highest-confidence execution
failures are in application orchestration and contracts, not evidence that the
embedding model itself is defective.

The current 55-question cohort contains **26 `QUANTITY_REVIEW_UNRESOLVED` stops**,
five no-progress stops, one tool-limit stop, one ModelRetry research error and 22
normal stops. Eight rows retain explicit application ValueError codes in their
collection failure: 214, 366, 380, 636, 637, 1016, 1070 and 1072. A further three
collection failures are schema/native output errors: 393, 520 and 1015. These
categories overlap broader semantic issues; do not sum issue-family counts.

The 46 unresolved ledger rows are **not 46 proven implementation bugs**. They also
include incomplete absence verification and disputed task/population definitions.
The shared matcher still reports 84/120 overall and 25/55 in the current cohort;
this audit changes diagnosis, not those recorded answers or scores.

## A1 / REPAIR-001 — immutable meaning is implemented as exact string equality

**Priority P0. Confirmed live and offline in 366, 1016, 1070.**

[app/llm/quantity_review.py:282](../app/llm/quantity_review.py#L282) rejects a repair if interpretation or expression text differs,
even when the objection concerns source inputs. The model is nevertheless asked
to regenerate those operation fields in the collector schema. This creates a
contract that requests mutable text and then demands byte-identical output.

Offline replay with saved model outputs reproduces
`REPAIR_CHANGED_UNTARGETED_STRUCTURE` in all three rows:

| Row | Changed operation fields | Controlled offline result |
| --- | --- | --- |
| 366 | interpretation wording only | Restoring original operation text allows merge; execution then exposes the separate named-function failure in A8. |
| 1016 | interpretation wording only; an extra “the” | Restoring original operation text allows merge and deterministic execution yields **10314**. No new extraction or model call. |
| 1070 | interpretation wording and redundant formula parentheses | Expression ASTs are identical. Restoring original fields allows merge, but the replacement still reports incomplete issuer evidence; release is not thereby justified. |

**Fix boundary:** application-owned operation fields should not be regenerated for
an operand-only repair. Use an explicit input patch contract and carry the accepted
operation unchanged. A genuine operation objection needs a separate operation
repair path. Do not solve this by accepting arbitrary changed formulas or disabling
source review. The offline result is diagnostic, not a successful live rerun.

## A2 / REPAIR-002 — preserved text operands fail a new global image contract

**Priority P0. Confirmed live and offline in 1072.**

[app/llm/quantity_review.py:296](../app/llm/quantity_review.py#L296) preserves all untargeted operands from the original draft.
In a text-to-image repair, these operands retain their original text locators.
Then [app/llm/quantities.py:865](../app/llm/quantities.py#L865) requires every operand to have a current image page and
nonempty witness. Locally valid evidence becomes invalid under the new record's
global modality, even though the fresh collector returned all required locations.

Saved output replay: fresh image-bound pages are **[40, 39, 39]**. After repairing
only operand 0, merge produces **[40, null, null]**, exactly matching the saved
pending record. The application raises `QUANTITY_ITEM_PAGE_INVALID` before review.
This is not proof the model confused the page order.

**Fix boundary:** preserve accepted value receipts with their original source
locators, while keeping the fresh observation's locators distinct. Validation must
support that per-operand provenance or deliberately rebind and recheck every
operand when switching representation. Do not overwrite accepted values merely
to make all operands look like image observations.

## A3 / PAGE-001 — required comparison evidence is silently removed as context

**Priority P0. Confirmed live and offline in 641.**

The selector requests image pages **[7, 8]**, with comparison-chart support E1.S74
in the context role (physical range 6–7) and answer-table inputs on page 8.
[app/llm/quantities.py:685](../app/llm/quantities.py#L685) filters requested images against input-role page ranges only.
The collector receives **[8]**, exactly as in the saved quantity receipt, and
reports that the recall comparison chart is absent.

The scope restriction is intentional, but dropping a requested, authorized image
silently loses information. Metadata context and visual comparison inputs need
separate roles; a comparison operand cannot be treated like a textual heading.

**Fix boundary:** validate required evidence roles before collection. Promote an
authorized page needed for visual comparison into a bounded input role, or return
an explicit role/page mismatch for deterministic re-selection. Do not remove ACL,
version checks or the page budget. Record requested, retained and excluded pages
with typed reasons.

## A4 / FLOW-001 + ROUTE-001 — quantitative fallback intercepts other tasks

**Priority P0. Confirmed dispatch and termination paths; semantic examples 511,
517 and 520.**

[app/llm/adaptive.py:1875](../app/llm/adaptive.py#L1875) dispatches `collect_quantities` after a failed fast answer even
when there is no quantitative need. `collection_need` is then empty. The exposed
read, select and lookup contracts contain numeric operands, so text inside a box
and qualitative map comparison can become null/unreadable numeric drafts.

After one such draft exists, [app/llm/adaptive.py:1938](../app/llm/adaptive.py#L1938) creates an abstaining candidate or
closes research. The general search/read/inspect/extract graph therefore does not
automatically get a chance to solve that task. [app/llm/adaptive.py:1703](../app/llm/adaptive.py#L1703) also abstains early
when only unaccepted quantity records exist. Correctly separating finalization
from research does not recover observations that never reached an accepted type.

**Fix boundary:** dispatch by evidence/result type, not simply a failed fast answer.
Retain narrow numeric tools and expose the existing textual/visual extraction path
for compatible tasks. Return typed missing-evidence/tool-incompatibility results to
the bounded policy rather than treating every unsuccessful quantity draft as the
terminal answer. This does not require an extra answer-generation loop.

## A5 / REPAIR-003 — every final-scope objection demands fresh source pixels

**Priority P1. Exact guards confirmed in 214, 380 and 637.**

[app/llm/quantity_review.py:319](../app/llm/quantity_review.py#L319) maps every scope diagnostic to `scope_research`.
[app/llm/quantities.py:631](../app/llm/quantities.py#L631) then requires a fresh source view. For an already inspected image,
renaming the support or moving it between roles correctly does not count as fresh.
But not every objection needs new evidence: an output-unit transformation or a
printed/physical page relationship can concern evidence already present.

Row 380 needs the lac-to-rupee transformation; row 637 has a completed count but
lacks a release-visible page-label relationship. Both stop with
`REPAIR_REUSED_INSUFFICIENT_SOURCE`. Row 214 has an actually questionable premise;
it must not be forced to release merely because arithmetic succeeds.

**Fix boundary:** distinguish missing evidence, interpretation, presentation,
provenance and actual question mismatch before selecting repair. Keep the freshness
guard for an actual missing-source search. Do not require it for application-owned
unit conversion or verified binding propagation. Do not simply delete the guard.

## A6 / INV-001 + MEMBER-001 + SCOPE-001 — approval checks the subset too easily

**Priority P0 for incorrect releases; semantic failures confirmed by original-page
audits in 476, 381, 399, 660, 638 and 510; incomplete direct answer in 831.**

[app/llm/quantities.py:306](../app/llm/quantities.py#L306) verifies flags, duplicate positions and item lengths, but closure
and category membership are model assertions. A complete page is accepted as a
complete inventory; a multi-column continuation is assigned to the wrong heading;
a true pin/function fact is accepted outside the requested port range. Direct
answer validation in 831 checks emitted statements without covering omitted tasks.

**Fix boundary:** separate item evidence, sibling-heading/column membership,
requested-object constraints and closure receipts. Coverage must accumulate across
bounded source windows. The final judge must assess both support of emitted claims
and completeness against the requested scope. Keep exact-count gold values out of
runtime. Correct successful counts do not disprove the false-closure defect.

## A7 / PROV-001 + NUM-001 + UNITS-001 — source context and transformations split

**Priority P1. Observed live; code confirms the missing responsibility boundary.**

[app/llm/quantities.py:757](../app/llm/quantities.py#L757) supplies text context separately from selected inputs. Immutable
document identity is checked by the application, but verified company/title,
period and unit relationships are not a uniform typed evidence packet available
to every semantic check. A filename alone must not become proof of company identity.
[app/llm/quantity_state.py:234](../app/llm/quantity_state.py#L234) carries source/version/physical page but no verified visible
printed-page relationship, contributing to 637's release objection.

Numeric exception containment and accounting notation fixes are already present;
the original NUM-001 conversion-crash gap must not be described as still unfixed.
However, model-declared notation still rejects grouped displays in 1016/1021.
[app/llm/quantity_numbers.py:104](../app/llm/quantity_numbers.py#L104) applies scale/sign output conversion only to scalar reads;
arithmetic depends on a correctly written formula. In 380, values in lacs are
subtracted while the result is labelled rupees without multiplication by 100000.
A later semantic validator catches the mismatch, but execution itself does not
provide dimensional validation for that output claim.

**Fix boundary:** keep original display and explicit notation; preflight invalid
notation cheaply. Carry verified table header/entity/period links, source numeric
units, output units and application-owned transformations distinctly. Do not infer
locale or silently apply absolute value. Do not force all unresolved questions
through OCR when the defect is provenance or a calculation transform.

## A8 / CALC-001 — function identifiers are treated as missing operands

**Priority P1. Latent second failure reproduced offline for row 366.**

[app/llm/quantities.py:325](../app/llm/quantities.py#L325) treats every AST Name as a sourced operand. With the saved
`abs(forecast_growth - achieved_growth)` expression, merge recovery exposes
`QUANTITY_UNKNOWN_OPERAND`: `abs` is treated as an operand name. Generic offline
examples reproduce this for abs, min, max and mean. The quantity evaluator also
does not support those calls; a separate fact-calculation path has different
capabilities. This is a capability/dispatch mismatch, not a recommendation to
execute arbitrary Python.

**Fix boundary:** declare operation-local arithmetic capabilities before expensive
collection/review. Either supply bounded explicitly allowed operators or select
an already compatible deterministic operator. Distinguish unsupported function
from an actually missing sourced operand. Do not claim this was the original live
stop in 366: the live stop was REPAIR-001 first.

## A9 / OBS-001 + EVAL-001 — diagnosis omitted available evidence

**Priority P1. Confirmed audit/observability gap.**

[app/llm/agent_observability.py:189](../app/llm/agent_observability.py#L189) deliberately exports exception class only, keeping arbitrary messages
and source content out of telemetry. That privacy boundary is useful. But
[app/llm/adaptive.py:1922](../app/llm/adaptive.py#L1922) stores the exact application error in local typed state. Earlier
reports inspecting only spans incorrectly left 1070's guard unspecified.
**Correction: 1070 is `REPAIR_CHANGED_UNTARGETED_STRUCTURE`; 366 and 1016 are the
same guard. 1072 is `QUANTITY_ITEM_PAGE_INVALID`; 636 is
`QUANTITY_REFERENCE_TOO_LARGE`.** The last is a local 1500-character witness bound
at [app/llm/quantities.py:454](../app/llm/quantities.py#L454), not missing model capability.

[scripts/experiments/run_adaptive_trace.py:373](../scripts/experiments/run_adaptive_trace.py#L373) chooses reviewer images from benchmark reference pages.
Unanswerable rows frequently have no reference pages, so their reviewers may see
no original images. Wrong or incomplete reference pages also miss needed inputs.
The reviewer has additionally approved wrong membership/location/constraint joins
in 399, 660 and 638, and offered a different task in 636. It is not independent
proof just because it returns true.

**Fix boundary:** emit allowlisted application domain codes, not raw exception
messages, in spans and typed failure records. Audit state, captures, image bindings
and source pages together. Build review coverage from actual inspected source
objects plus independent relevant pages; keep benchmark labels out of the
reviewer's correctness decision. Calibrate false acceptance and false rejection
against manually checked examples. Update the report diagnosis when new evidence
is found instead of discarding the failed run.

## Other issues that must stay separate

- **STOP-001:** source-scoped mismatch and incomplete search currently end as
  no-progress/tool-limit abstentions; they need distinct verified terminal states.
- **COMPOSE-001:** 206/225/219 need approximate weighted headcounts; 216 has a
  Democratic versus Dem/Lean Dem population mismatch. A gold integer does not
  establish an exact observed headcount. 1015 also needs an explicit EBITDA plan.
- **COVER-001:** 662/663/1017 have incomplete multi-page evidence. Do not raise the
  page ceiling before implementing accumulated coverage and typed missing roles.
- **INTERPRET-001 / COUNT-001 / SRC-001:** 366, 732, 1075, 658, 663 and 661 include
  metric, counting-unit or source-annotation adjudication. Keep these separate
  from mechanically reproduced code failures; no target answer should be forced.
- **VIS-001:** 635's blue-versus-grey acceptance is still a semantic visual defect,
  not explained by the repair failures above.

## Repair order and acceptance criteria

1. Fix REPAIR-001 with operand-only patches, then REPAIR-002 with preserved
   per-operand locators. Offline controls must show meaning-preserving repairs pass
   while unrequested formulas, values and source identities remain rejected.
2. Fix PAGE-001 and typed missing-evidence/dispatch results. Verify required
   authorized visual pages survive handoff within existing budgets; textual and
   spatial tasks must avoid incompatible numeric contracts.
3. Fix repair-kind dispatch and context propagation. Same-page transformation or
   printed-page binding must not require pretending a new source was discovered.
4. Address false-closure/membership/constraint acceptance before broadening release
   coverage. Add original-source controls for multi-page continuation, sibling
   headings, top/bottom location and incompatible entity/range conditions.
5. Add safe domain-code telemetry and evaluator coverage checks alongside each
   change. Remeasure the exact failed cases and frozen prior controls; keep the
   earlier pipeline comparison and both false refusals and wrong releases visible.

Do not start by globally weakening the judge, increasing model effort, adding
unbounded calls, changing embeddings or adding per-document rules. The audit
replays demonstrate application defects without any new paid model calls.

## Why the existing tests did not establish safety here

The targeted-merge test in
[tests/test_quantity_review.py](../tests/test_quantity_review.py#L69) preserves
literal operation fields in its fixtures and correctly rejects an actual addition-
to-multiplication change. It does not exercise equivalent interpretation wording,
redundant parentheses or text-to-image locator preservation. Those controls must
be added alongside the correction, without deleting the real-operation guard.

The failed-review test in the same file explicitly prohibits reader/finalizer
regeneration after an unresolved numeric review. That is a useful anti-guessing
control, but it does not show that nonnumeric tasks dispatch correctly or that a
bounded evidence-recovery route is compatible with the policy. The scope-repair
test mocks collection, so it does not exercise the actual freshness and merge
checks that fail in these live cases. A passing test suite therefore establishes
its tested contracts, not the missing transitions exposed by the captured runs.

## Verification and artifacts

Offline replay uses saved drafts/receipts and current pure application functions.
It verifies three exact merge failures, an equivalent expression AST, the 1072
locator failure, the 641 page removal and four generic named-function failures.
Raw diagnostics live in ignored
`artifacts/mmlongbench-v2/adaptive-issue-audit-20261020/` (offline-replay and
cohort-diagnostics JSON). No runtime or test files were modified; no paid requests
or benchmark reruns were made. The current register is
[adaptive-open-issues.md](adaptive-open-issues.md).

## Repair and evidence handoff implementation

The follow-up [implementation report](../artifacts/mmlongbench-v2/adaptive-repair-handoff-20261020/REPORT.md)
records operand-only source repairs, per-entry mixed text/image provenance and
preservation of explicitly requested authorized visual context pages. These changes
address REPAIR-001, REPAIR-002 and PAGE-001. The historical failures and audit scores
above remain unchanged; new live checks are recorded separately in that report.

The [numeric authority follow-up](../artifacts/mmlongbench-v2/adaptive-quantity-authority-20261020/REPORT.md)
adds live evidence for notation-metadata correction and semantic-only checking of
reexecuted application arithmetic. It restores 1021's correct quotient despite
another false arithmetic objection from the separate after-run reviewer, and
records the remaining relationship-context investigation for 641. Historical audit
scores above remain frozen.


## Inventory and scope handoff follow-up

The [targeted follow-up](../artifacts/mmlongbench-v2/adaptive-inventory-scope-20261020/REPORT.md)
recovers 476 (9), 399 (4+3=7) and 381 (7), with control checks on 382/477. It also records
an initial eight-abstention regression and intermediate failures rather than hiding them.

Optional native IDs/typography and copied-quote capacities no longer veto independently
supported image inputs. Complete source references survive without shortened quotations.
Checked zero-item groups retain their computational contribution without invalid legacy
empty-count claims. Numeric collection declares whether a value is printed or counted;
application code can hand an already located roster to the inventory tool. Source review
and final scope share original native PDF evidence, distinct from generated result proofs.

Document-wide numbered inventories can use an authorized, same-version three-page window
with strictly greater observed identifier coverage. This changes source acquisition,
not the answer or coverage verdict, and does not apply to bounded/unknown subset scopes.
Full native observations stay in state; compact model views preserve all literal lines.
A boundary gap requires new evidence instead of rereading the same partial view.

Remaining work includes partial-coverage accumulation beyond one bounded window, broader
semantic/visual acceptance checks and adjudication of 638/660/510. Those abstentions are
not automatically certified as correct source absence. Frozen aggregate scores remain
unchanged; the historical distinct-question ledger now records 74 supported answers,
one qualified calculation, four verified refusals and 41 unresolved outcomes.
