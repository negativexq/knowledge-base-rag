# Numeric authority and relationship evidence

## Implementation

This follow-up addresses the four remaining blockers in the
[prior repair regression](../adaptive-repair-handoff-20261020/REPORT.md).

- An independent source reviewer may correct an invalid numeric notation declaration
  in the existing input-check request. Corrections identify the operand and notation;
  they cannot alter the source display, formula, unit or an already valid interpretation.
  The application reparses and checkpoints the corrected receipt before execution.
- A tentative ambiguous numeric reading may remain in the checkpoint with its numeric
  display, but cannot execute. Lookup entity binding is a separate typed field. A
  readable cell with an unknown join cannot execute until independently verified.
- A grounded relationship objection can trigger one bounded same-document/version
  search without an extra model stage. Candidate definition passages travel as context,
  not replacement numeric inputs or presumed aliases. Joins still require source review.
- Exact application-owned arithmetic candidates receive a semantic-only final scope
  projection. The application reexecutes the named-input formula and compares the whole
  candidate before using this path. The model sees the checked inputs, formula, unit,
  interpretation and original sources, but not the computed result or generated result
  proof text. It must still establish source/entity/period/unit/formula compatibility.
  Changed answers, stale results and ordinary model-written claims retain full checks.
- A clearly declared, independently reviewed conventional operation is distinguished
  from a claim that the source reports or defines a metric. It may be used when the
  question leaves the convention open; explicit source/question definitions and material
  contradictions remain binding. The chosen interpretation stays visible in the answer.

Release receipts remain bound to the full original answer and source payload. Scope
projection does not auto-approve any claim or bypass positive scope witnesses.
Embedding, retrieval, reranking, model effort and request/token/time budgets are unchanged.

## Verification

**2,218 tests passed, 4 optional skipped, 5 deselected.** Ruff and mypy passed
(155 application source files). Seventeen new tests cover notation repair, rejected
reinterpretations, retained ambiguity, blocked unknown joins, relationship search,
exact candidate identity, reexecution, semantic rejection and original-answer receipt
fingerprints. New tests are included in `make test-adaptive`.

## Live sequential remeasurement

Rows: 1016, 1072, 641, 1021, 1086. Existing gpt-6-luna trace settings: fast path,
evidence needs, ten answer requests, 120,000 tokens and 240 seconds. Independent
after-run review is separate. Runtime hashes are frozen before the first row and
checked before each following row. Raw diagnostics remain local and ignored in
`live-five/`. All five initial runs completed: **four answers, one abstention**.

| Row | Initial published result | Main seconds / requests | Finding |
| --- | --- | --- | --- |
| 1016 | 10314.000 million | 51.19 / 6 | Existing source checker corrects invalid notation for operands 0/1. The application calculates the correct total; final scope accepts. No image repair needed in this run. |
| 1072 | 26.304% under declared ROCE formula | 57.12 / 6 | Source inputs and arithmetic accepted; chosen operating-income / ending-capital convention is displayed. Equivalent unrounded ratio is approximately 0.263042. This is a declared calculation, not a source-reported ROCE metric. |
| 641 | Abstention | 86.80 / 7 | Relationship search runs, but context packing evicts the explicitly selected page-5 authority; QUANTITY_PAGE_OUTSIDE_SOURCE stops repair before the next extraction. |
| 1021 | 0.715 ratio | 64.58 / 10 | Correct quotient published. A legitimate company-identity objection first obtains source context; semantic scope then accepts without a competing LLM arithmetic result. |
| 1086 | 13929.000 million USD | 83.44 / 9 | Source-image repair and semantic-only final scope accept the correct assets-minus-cash calculation. |

### Required-context priority follow-up

The failed 641 remeasurement exposed a packing defect: optional search hits plus
retained closure paragraphs could evict the selector's explicit context seed while
its requested image page stayed selected. Required seeds now reserve their slots
and characters first; optional passages fill remaining space within six units and
6,000 characters. Oversized required context fails with a distinct typed error,
without rendering outside authorization or silently dropping the required seed.
A new regression test reproduces full old closure plus an oversized search hit.
Targeted follow-up: only row 641 will be rerun after validation.

### Independent reviewer adjudication

For 1021, the after-run reviewer again claims that 29441/41190 rounds to 0.716.
Decimal arithmetic gives 0.714760864287448… → **0.715**; its negative verdict is
incorrect and retained only as a raw diagnostic. For 1086, the reviewer again lacks
the actually used balance-sheet pages; earlier manual source verification remains
applicable. For 1072, the reviewer confirms the inputs and conditional formula but
notes that the PDF does not define ROCE. The chosen interpretation must remain
explicit; different source-mandated conventions cannot be silently substituted.


### Definition-context follow-up

The context-priority rerun saves both drafts without page/schema exceptions but
still abstains: 112.60 seconds, 9 main requests. The same relationship remains
unresolved. It selects generic result sections instead of the admitted dataset
definition paragraph. This is evidence selection failure, not established absence.

A bounded local context selector now uses contrasted labels from grounded objections
to surface same-snapshot definition/subset passages. It supplies candidates to the
source selector and checker without asserting equivalence, adding model calls or
changing retrieval/index scores. The general rule includes passages establishing
*differences* as well as aliases; foreign versions, hidden and unauthorized units
are excluded. A saved-trace replay locates E1.S60, the actual dataset definition.
When such admitted context exists, it avoids a redundant document search. The
second targeted row-641 rerun is recorded under `row641-definition-context/`.

### Typed routing and presentation follow-up

The definition-context rerun also abstains (90.88 seconds, seven main requests):
the reviewer describes the same missing relationship but emits `evidence_kind=unspecified`.
That optional model tag prevented local definition selection; the selector then marks
a plausible source unavailable. This is a routing-contract defect, not proof of absence.

Lookup relationship recovery now dispatches from the operation and grounded binding/
missing-input objection, including unspecified evidence tags. When a new admitted
same-snapshot definition passage is available, application code retains the known
input window and supplies that context directly to collection and independent review,
without an extra selector or search call. It never approves the join itself. New
regression coverage checks this exact dispatch boundary using unrelated synthetic labels.

Numeric read/lookup contracts also carry nullable requested output precision. The
application rounds the published display while preserving source values and receipt
precision. This closes the generic presentation gap where a source cell's precision
would otherwise override the question's decimal-place request.

## Final observed status

The typed-relationship row-641 rerun completes without schema/page/selection errors:
**84.05 seconds, seven model requests, two tool attempts, no diagnostic retry**.
The `quantity.source.relationship` span records application dispatch; its context
receipt includes E1.S60. No redundant source-selection call or document search is
made for this repair. Extraction and independent checking both receive the admitted
dataset definition.

The result remains an abstention. The reviewer now explicitly acknowledges that
FEVEROUS-S is the selected subset of FEVEROUS but does not accept that Table 3's
FEVEROUS header reports that same experimental population. Native text from the
original PDF page 5 confirms the sentence-only subset description. This supplies
important contextual evidence, not a universal parent/subset equivalence rule.
The remaining issue is semantic population/scope adjudication; it is not absence
of the numeric cell, loss of context, a schema crash or a page authority failure.
No benchmark-specific equivalence was added and the case is not marked solved.

Latest outcomes for the five target questions: three source-supported answers
(1016, 1021, 1086), one explicitly interpreted calculation (1072), one unresolved
lookup (641). The first five-row batch remains the frozen comparison; subsequent
641 attempts and their failures are retained separately, not substituted silently.
The history contains eight main executions in total: the five-row batch plus three
641 follow-ups, each with a separate after-run review. USD cost is unavailable
because the model has no configured pricing receipt.

The historical ledger now contains **71 source-supported answers, one qualified
interpreted calculation, four verified refusals and 44 unresolved outcomes across
120 unique questions**. Frozen full-set/cohort matcher scores have not been
recomputed with this development follow-up.
