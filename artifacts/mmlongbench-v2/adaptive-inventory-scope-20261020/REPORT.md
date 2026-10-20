# Inventory coverage and question-scope correction

Date: 20 October 2026.

This targeted development check covers six previously incorrect releases (476, 381,
399, 660, 638, 510) and two previously correct controls (477, 382). It is not a new
120-question aggregate benchmark. No embedding, retrieval, reranking, model, request,
token or time limits were changed. The generating workflow receives no gold answers
or reference-page overrides. The separate after-run reviewer is diagnostic, not an
acceptance oracle.

## First batch: validation regression

The first frozen batch (`live-eight`) abstained on all eight rows. Preventing the old
wrong releases did not establish a working correction: both correct controls also
regressed. The trace audit identified unnecessary validation and repair work:

- Row 477: native typography classified bold numeric level labels as sibling headings,
  making a valid seven-item inventory fail membership validation.
- Row 382: an optional native closure handle became mandatory; a scalar/vector mismatch
  sent already correct 1/0/1 source observations back toward source repair.
- Row 476: nine items passed original-image review, but the final scope reviewer demanded
  that image-only labels also appear in incomplete indexed text. Repair then discarded
  the already observed next-section boundary.
- Row 399: the checker located the named rosters, but a generic missing-coverage route
  took precedence over the explicit entity-inventory requirement. A second arithmetic
  extraction and its budget stop failed to complete the count workflow.
- Row 381: the inspected summary actually omits Quiz #7, which appears on physical
  page 10. Independent review initially missed the omission and instead objected to
  scalar/vector presentation. The summary title is not a completeness certificate.
- Rows 638, 660 and 510: location, range and geographic-binding uncertainty no longer
  produced the prior unsupported answer. An abstention alone does not certify source
  absence or resolve an ambiguous question.

## Responsibility boundaries

Parser typography and structural handles are optional observation aids. Missing or
ambiguous native metadata does not itself invalidate original-image evidence. Native
checks retain concrete observed counterexamples rather than demanding one proof shape.
Original-source input review still checks membership and coverage.

Application code can apply a uniquely reviewed count-operation correction when source
inputs and coverage are independently supported and there are no input objections.
It preserves the original review, source items and resulting execution receipt without
another collector call. Distinct counts still require supported entity identity.

Already located image rosters can be recollected under the entity-inventory contract
without another selector or fresh-source search. A real missing-source gap still needs
more evidence. Native catalogs can surface literal question-matching lines from the
middle of admitted pages within their existing bounds; they remain location hints.

Exact, locally reexecuted count candidates now use the existing semantic scope projection
also used for arithmetic. Final scope sees independently checked source items, boundaries
and original source IDs. It checks question compatibility rather than redoing extraction
against a parser known to omit image labels. Changed, unchecked or stale candidates do
not receive this projection. The final receipt still binds the full answer and evidence.

## Validation

- Full suite: 2,242 passed, 4 skipped, 5 deselected.
- Ruff passed; mypy passed for 157 source files.
- Regression coverage includes bold numeric rows, optional closure metadata, source-bound
  omissions, sibling membership, exact count projection, tampered/unchecked candidates,
  operation-only completion without extra model calls and middle-of-page catalog hints.

The second batch uses a frozen application/harness hash snapshot in local
`relaxed-eight/selection.json`. Rows run sequentially: 477, 382, 476, 399, 381, 638,
660, 510. Raw captures, spans, result JSON, logs and source renders remain local and ignored.


## Intermediate batch audit

The first relaxation restored both controls, but did not complete the correction.
`relaxed-eight` produced correct answers for 477 and 382, failed to publish verified
answers for 476 and 399, released the incorrect six-quiz answer for 381, produced an
empty response for 638, and abstained on 660 and 510. These are retained as failures,
not counted as successes from the original-image reviewer's proposed answer.

The captured collector actually returned all nine USB functions and the correct 4+3
rosters. Optional object/closure descriptions exceeded a newly introduced 40-character
limit, causing the SDK to discard the complete output before a quantity checkpoint.
Row 382 had an accepted, completed quantity record but emitted an empty legacy count
claim for the inspected zero-item category, triggering `COUNT_EMPTY` and an unnecessary
finalizer. These are application contract defects, not missing source values.

The compatibility correction expands optional locator text capacity, omits empty legacy
count claims while preserving checked zero contributions, and fills the existing
three-page count window for contiguous one- or two-page selections. It also exposes
bounded numbered-label location hints and switches the same selected pages to original
images when indexed text omits an observed numbered label. No document-specific names,
expected counts or reference-page routing rules are encoded.

The final targeted batch (`final-six`) remeasures 476, 399, 381, 382, 477 and 638
sequentially with a new frozen source/harness snapshot. It retains the same model,
reasoning settings and hard budgets. Rows 660 and 510 retain their preceding measured
abstentions; neither is automatically reclassified as verified source absence.


## Source handoff follow-up

`final-six` released the correct USB count (9; 47.37 s, five requests) and coffee-level
count (7; 84.09 s, nine requests), but abstained on 399, 381, 382 and 638. The following
trace defects remained after the first compatibility corrections:

- 399: the numeric collector returned 4 and 3 as derived headcounts with names in its
  witnesses. It was using an arithmetic input contract, so the literal numeric verifier
  correctly did not certify these as printed numeric operands. The extraction method
  needed an explicit inventory handoff, not a weaker arithmetic verifier.
- 381: a complete source-range reference exceeded an optional 1,500-character quote
  capacity and was discarded before input review. The selected partial inventory still
  needed more source coverage; removing this storage defect is not itself proof of seven.
- 382: complete 1/0/1 groups and the computed total 2 were accepted, but final scope
  demanded Unit 6 evidence in incomplete indexed excerpts despite a successful original-
  image input receipt. Its repair then dropped the previously inspected Unit 4 page.

The follow-up admits the actual bounded native PDF observations as original source units,
separately from generated proofs. It preserves long original references without copying
or shortening them into the optional witness slot. A typed `value_origin` lets the
application hand derived numeric counts to the inventory contract using the known source
window. Unsupported printed operands still cannot execute; the local verification failure
is checkpointed. The after-run reviewer and the release checker still have distinct roles.

`evidence-handoff-six` remeasures 399, 381, 382, 476, 477 and 638 sequentially with its
own frozen source/harness snapshot and the same hard budgets. Earlier failures and the
intermediate wrong six-quiz release remain recorded above.


## Measured handoff results

| Row | Published result | Main-run time | Model requests | Review outcome |
| --- | --- | --- | --- | --- |
| 399 | 7 = 4+3 people | 51.08 s | 6 | Source-supported; original category rosters counted. |
| 382 | 2 = 1+0+1 quizzes | 61.76 s | 7 | Source-supported; arithmetic-to-inventory handoff and original native evidence exercised. |
| 476 | 9 USB functions | 44.67 s | 5 | Source-supported; five entries on page 56, four on 57, next section on 58. Firmware update is service-only. |
| 477 | 7 quality levels | 44.74 s | 6 | Source-supported control. |
| 381 | Abstained | 43.62 s | 5 | Partial inventory; a boundary gap incorrectly reused the same view and exhausted its checking reserve. |
| 638 | Abstained | 42.60 s | 4 | The top prompt example is not evidence for the requested lower figure; source/interpretation adjudication remains. |

All times/requests exclude the separate diagnostic reviewer. Cost accounting has no
configured price for this model in these captures, so USD cost is unknown, not zero.

The subsequent `coverage-row381` attempt stopped after a fresh but still incomplete
window; its second checker also cited an old page outside the current image window.
It did not recover a source-complete result and is not recorded as a success. The trace
confirms that general multi-window accumulation/closure is still incomplete.

The document-window follow-up adds a typed document/subset scope declaration and
application-owned improvement of an eligible numbered inventory's bounded source window.
It keeps authorization, source version, scope validation and the original page/request/
token/time ceilings. Ordinary line geometry is omitted from model views, but every
native source line and the complete original observation remain preserved. Boundary gaps
request fresh evidence; representation-only handoffs can reuse the already known source.

`document-window-pair` remeasures 381 followed by subset control 382 sequentially. The
control checks that the new document-wide acquisition policy does not widen the question
from Units 4/5/6 to the entire course. Its source/harness hashes are frozen locally.


## Final document-window checks

| Row | Published answer | Main-run time | Model requests | Source scope |
| --- | --- | --- | --- | --- |
| 381 | **7 quizzes** | 67.33 s | 5 | Selector declared `document`; physical pages 10/15/16 cover the detailed seventh quiz and summary entries 1–6. Text selection was promoted to original images because the indexed excerpt omitted native numbered labels. |
| 382 | **2 quizzes** | 42.57 s | 5 | Selector declared `bounded_object`; the Units 4/5/6 subset remained authoritative. Summary pages 15/16 supply the two relevant quiz entities. No document-wide window override. |

Both input reviews accepted complete inventories, application count execution completed,
and final scope passed. Each used planner, source selector, collector, independent input
checker and scope validator once, with no answer-finalizer retry. The document-window
policy was available; on 381 the selector itself chose its complete suggested window.
The automatic preference's source/version/authorization/subset guards are covered offline.

Latest targeted dispositions are therefore five source-supported answers (381, 382, 399,
476, 477) and three unresolved abstentions (638, 660, 510). The latter three are not
promoted to verified refusals or source absence. The earlier wrong releases, initial
regression and failed recovery attempts remain part of this report.

This promotes three previously unresolved ledger rows (381/399/476): **74 supported
answers, one qualified interpreted calculation, four verified refusals and 41 unresolved
outcomes across the same 120 distinct attempted questions**. It does not recalculate the
frozen 120-question matcher score or claim a new end-to-end full-set result.

Remaining limitations: independent semantic/visual judgments can still err; inventories
that cannot fit a complete source view in three pages need reusable partial-coverage
accumulation and closure across windows. This change provides bounded source acquisition,
original-source handoff and correct local execution rather than certifying arbitrary
long-document inventory completeness. No further runtime edits were made during the
final measured pair.
