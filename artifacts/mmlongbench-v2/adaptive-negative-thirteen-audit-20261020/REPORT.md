# Audit of thirteen source-negative question outcomes

Date: 20 October 2026. Code inspection anchor: merged main `45402ee` / [PR 119](https://github.com/negativexq/knowledge-base-rag/pull/119).
This is a read-only source-and-trace audit. No model/API calls, benchmark reruns,
runtime fixes, prompt changes or new rejection rules are included.

## Conclusion

The thirteen selected outputs all abstain. They are not thirteen missing answers
that should be forced through validation. Source review supports withholding the requested
unqualified answer, with two product-policy distinctions:

| Source disposition | Rows | Count |
| --- | --- | --- |
| Requested entity, subject or period does not match the source evidence | 207, 209, 222, 365, 367, 1084 | 6 |
| Requested field, series, relationship or operand is not reported in the relevant source scope | 508, 520, 521, 728, 730 | 5 |
| Incorrect revision-date premise; the producer is available under an explicit correction | 384 | 1 |
| Underspecified market-opening request; clarification or scoped insufficiency is appropriate | 830 | 1 |
| **Total** | Each row appears once | **13** |

The six-plus-five group needs evidence-backed explanations with the right scope, not
invented answers or blanket early refusal. For 384, a useful response may identify the
producer of the available May 2016 revision while explicitly declining to identify it
as May 2018. Strict benchmark answerability and such a qualified product response are
separate policy choices. For 830, asking which market/date is preferable to inventing
opening hours or silently using closing time.

The 120-row archive has **20 exact `Not answerable` labels** plus **475**, whose label
also accepts 0/none. The earlier 21-question unanswerable cohort includes that mixed
case. Every row in this thirteen-question audit belongs to the twenty exact labels.
No label was used as source evidence or as an instruction to the runtime.

## Method and limits

- Read the latest completed saved result for each target row, including its exact
  question, source scope, ResearchState, tool events and source assessments. The ignored
  selection file preserves the exact local paths and labels. Selection was frozen before
  source review; no result is replaced or rerun during this audit.
- Read all native PDF text across nine pinned originals (239 pages). Two slide decks
  have no useful native text: a zero text match there is not absence evidence.
- Rendered original pages with PyMuPDF because Poppler is unavailable. Reviewed all
  25 social-metrics slides and all 23 Germanwings slides as contact sheets, with the
  corporate-tweet table inspected separately at full-page resolution. Inspected decisive
  identity/date/list pages from the other sources, including the GPI narrative and bankers.
- Local Tesseract OCR over all 68 pages of the GPI PDF and the two slide decks supplies
  cross-checks/location hints. OCR alone does not establish absence. Original visible
  titles, column labels, object boundaries and full-slide coverage support the conclusions.
- Source mismatch statements below are limited to these authorized documents and the
  requested fields. They are not claims that a company, statistic or version cannot exist
  elsewhere. No internet search was performed and no current-world facts are assumed.
- Saved calls total **96 main model requests / 742.74 main seconds** across the thirteen
  selected runs. These are archived observations, not costs of this audit or an estimate
  of achievable savings. Reviewer requests are separate; pricing is not configured.

## Per-question findings

Page numbers below are physical PDF pages; S1-S9 identify pinned originals in the source
manifest at the end. A safe abstention is not automatically a checked global absence.

| Row | Requested information | Source finding | Appropriate disposition | Saved stop / main calls |
| --- | --- | --- | --- | --- |
| 207 | 2022 survey / Trump ethics headcount | S1 pp. 3, 6: survey is April 25-May 1, 2018; the 2022 population is not supplied. | Source period mismatch | `NO_RESEARCH_PROGRESS` / 6 |
| 209 | 2018 confidence domains for Biden | S1 pp. 3-6: the named confidence object concerns Donald Trump. Substituting these domains for Biden changes the subject. | Source subject mismatch | `QUANTITY_REVIEW_UNRESOLVED` / 6 |
| 222 | Gap involving internet use by 80+ in 2022 | S2 p. 1 dates the report April 2014; pp. 3/8 give the older cohort and pp. 22-27 document 2013 survey work. The requested 2022 operand is not established. | Source period mismatch | `NO_RESEARCH_PROGRESS` / 9 |
| 365 | Apple Inc. bankers | S3 p. 8 explicitly labels the company Godfrey Phillips India Limited and its BANKERS section. These banks cannot be attributed to Apple. | Source entity mismatch | `TOOL_ATTEMPT_LIMIT` / 9 |
| 367 | Japan GDP forecast shortfall, 2002-2023 | S3 p. 1 explicitly discusses India and the year ended March 31, 2003. Its 6.7%/4.3% pair is not a Japan 2002-2023 time series. | Entity and period mismatch | `NO_RESEARCH_PROGRESS` / 7 |
| 1084 | AMCOR FY2020 interest coverage | S9 p. 1 names Best Buy Co., Inc.; other years occur in this report, including 2020. The issue is unsupported AMCOR attribution, not a publication-year shortcut. | Source entity mismatch | `NO_RESEARCH_PROGRESS` / 7 |
| 508 | EPS AR03 geographic market | S5 p. 8: the complete Arkansas subsection lists AR01 Little Rock and AR02 Northern Arkansas, followed by New Mexico. No AR03 mapping is listed. | Not reported in the closed relevant object | `NO_RESEARCH_PROGRESS` / 6 |
| 520 | Source for Google audience data | S6 pp. 9/24 use Google Analytics as a measurement tool. P. 10 credits eMarketer for Facebook audience data. Full 25-slide review finds no Google-audience source attribution. | Requested subject/relationship not reported | `RESEARCH_TURN_LIMIT` / 9 |
| 521 | Largest Amazon-user age range | S6 p. 10 is explicitly Facebook audience age data; Twitter and LinkedIn have their own sections. Full 25-slide review finds no Amazon audience age series. | Requested series not reported | `QUANTITY_REVIEW_UNRESOLVED` / 7 |
| 728 | Germanwings minus Boeing tweets | S7 p. 16 gives Germanwings 24, Lufthansa 12, Airbus 5; full 23-slide review finds no reported Boeing count. Preserve 24; do not substitute Airbus or zero for Boeing. | Required operand not reported | `QUANTITY_REVIEW_UNRESOLVED` / 8 |
| 730 | Boeing tweet count | S7 p. 16 contains the relevant corporate-tweet table without Boeing. Runtime instead inspects p. 19, an aggregate Germanwings hashtag chart. Offline full-source review supports no reported Boeing count; the runtime window alone does not. | Requested entity metric not reported | `No stop code; local checked not_found` / 5 |
| 384 | Producer of the May 2018 revision | S4 p. 2 explicitly says Version 1.3, Revised May 2016, Produced by Florida Department of Health. P. 1 says strategic plan 2016-2018, a different date field. | Premise correction / qualified answer option | `RESEARCH_ERROR:ModelRetry` / 8 |
| 830 | When will the market open? | S8 pp. 11/13 discuss a stock assignment and 4 p.m. Eastern closing time; they do not specify the requested opening time. Exchange, session and date are unspecified. | Clarification or scoped insufficiency | `NO_RESEARCH_PROGRESS` / 9 |

## Trace findings that change the diagnosis

### 728: preserve the valid operand

The source table on physical page 16 explicitly labels Germanwings **24** as Tweets.
The archived initial reasoning calls 24 merely corporate activity and questions whether
it is a tweet count. That objection is contradicted by the original table. The missing
operand is Boeing, not both companies. The safe response should preserve Germanwings 24
and explain that the Boeing count needed for the difference is not reported. It must
not substitute Airbus 5, the aggregate hashtag curve, or an assumed Boeing zero.

This is an input-preservation/diagnostic correctness defect even though final abstention
is appropriate. A valid partial fact must survive a missing-field decision.

### 730: a local not_found is not document-wide closure

The latest saved run has an accepted read record, complete=true, not_found and
absence_confirmed=true after inspecting only physical page 19. That page's near-500,000
curve concerns aggregate Germanwings-related tweets, not the corporate table on page 16.
The record therefore does not independently prove the question's broader source scope.
The full-source offline audit supports the refusal; it must not retroactively grant the
runtime coverage it did not have.

This is not a reason to force an extra scope call before any safe abstention. The generic
insufficient-evidence answer may stop safely. It is a reason not to promote that answer
to a source-wide absence certificate merely because local review accepted not_found.

### 384: distinguish plan period from revision date

The cover's 2016-2018 plan period is not the revision date. Page 2 supplies May 2016
and the producer together. An unconditional answer identifying a May 2018 revision
would be unsupported. A transparent response can instead say that the available revision
is May 2016 and name its producer, without silently rewriting the question. The saved
ModelRetry is an execution outcome, not the evidence explaining this distinction.

### 830: clarify the requested object

The source contains a market-closing instruction, so lexical market matches are not
empty. They do not answer an opening-time question. Without an exchange, session or
date, clarification is appropriate. Do not import common market hours from outside the
source, convert closing to opening, or call repeated failed searches a verified absence.

## Current implementation boundaries

1. [CollectionOutcome](../../../app/llm/research_state.py#L29) records ok/not_found/
   review_unresolved/error plus IDs. It does not itself retain a verified terminal reason,
   blocking question constraint and source-object closure certificate. A failed tool is
   appropriately not treated as a global research stop, but the stronger terminal evidence
   remains implicit in free-form needs/assessments.
2. [Review acceptance](../../../app/llm/quantity_review.py#L221) requires supported inputs,
   complete coverage and supported operation. The checker instructions already require
   whole-object inspection for not_found. A verbal coverage verdict can nevertheless
   refer to a wrongly selected local object, as in 730; no generic source-wide guarantee
   follows from that flag.
3. [Read execution](../../../app/llm/quantities.py#L310) allows a complete all-not_found
   read, and [absence promotion](../../../app/llm/quantities.py#L1580) stores its absence flag.
   [Candidate construction](../../../app/llm/quantities.py#L432) then produces abstention.
   These transitions need to preserve the exact inspected object/scope when describing
   absence, rather than imply more coverage than the recorded pages.
4. [Safe abstention/clarification](../../../app/llm/adaptive.py#L1655) returns without
   positive-answer scope checking. That is desirable for safe budget/error exits; making
   every abstention consume another LLM verification call would add cost and could itself
   block safe stopping. Do not confuse that shortcut with proof of factual absence.
5. [No-progress](../../../app/llm/adaptive.py#L2322) and
   [tool-limit](../../../app/llm/adaptive.py#L2206) exits bound the loop but are not factual
   dispositions. Six rows end with no progress, three with unresolved quantity review,
   one at tool limit, one with ModelRetry, one at research-turn limit and one with a local
   accepted absence. These statuses explain execution, not source answerability.

## Proposed correction: preserve evidence and finalize the right explanation

This is a design recommendation, not an implemented new early-rejection gate.

Use an application-owned typed disposition alongside existing observations and coverage:

| Kind | Evidence needed | Appropriate response |
| --- | --- | --- |
| source_conflict | Requested field/constraint and the contradictory source value, with source locations and correct object binding | Explain the exact entity/period/version mismatch. |
| not_reported_in_scope | The relevant object is identified; its boundaries/continuations and inspected scope establish the missing field | State that the requested value is not reported in that scope. Missing is not zero. |
| needs_clarification | A material requested field is unspecified, or a corrected-premise alternative requires an explicit choice | Ask the narrow clarification or offer an explicitly qualified alternative. |
| insufficient_evidence | Unread pages, partial/scan-limited reads, unresolved candidate sources, tool/time limits or failed execution | Say the value could not be verified in the inspected material; do not claim document-wide absence. |

Retain the question constraint, source field, immutable source identity, witness locations,
inspected/required scope, unresolved candidate locations, verified partial facts and review
status. A model may propose the semantic classification; the application must retain the
actual typed evidence and budget state. Reuse the existing independent assessment when
sufficient; do not add a mandatory LLM call to every question.

Before accepting a strong negative disposition, check that it does not discard a valid
answer or a known reachable candidate. A blocking contradiction must actually bind to
what the question requests. A publication year alone, file name, empty keyword search,
wrongly chosen table, parser omission or budget stop cannot supply that proof. Where
scope remains incomplete, continue the ordinary bounded acquisition path when useful;
on budget exhaustion, finalize insufficiency while retaining successful facts.

Finalization should generate a user-facing explanation from the retained evidence. For
example, when the requested year is 2020 and the only verified observation is 2013:

- Closed relevant scope: explain that this source provides 2013 data and does not report
  the requested 2020 value in that scope.
- Partial inspection: explain that 2020 could not be verified in the sections inspected
  and that the observed value belongs to 2013.
- If helpful, provide the 2013 value with its own year; never silently use it as 2020.

A report published in 2023 can contain 2020 observations. A valid negative about a missing
legend category does not require the missing category to appear first: validate the
identity and boundaries of the requested legend, not presence of the absent target.
A closed object may be sufficient; scanning every PDF page is not a universal requirement.

## Regression set required before a runtime change

| Control | Behavior that must survive |
| --- | --- |
| 380 | Missing income in the first excerpt must be found on the next statement page; no early absence. |
| 1017 | Missing current/finance leases must be found in Note 6; keep the known debt and lease operands. |
| 1086 | Missing unit context must trigger context acquisition, not rejection of valid assets/cash. |
| 517 | Parser omission of a qualitative map relationship must leave image inspection available. |
| 511 | A text button must remain answerable without a numeric-read contract. |
| 637 | Printed/physical page mismatch must use the correct mapping, not reject the question. |
| 388 | A governor on the cover does not answer a question scoped to the last page. |
| 471 | A complete known legend can establish a missing yellow category without requiring a yellow match. |
| 475 | A missing red bar remains scoped to the inspected chart; its special 0/none label must not make every missing numeric value zero. |
| Synthetic delayed match | An early 2013 table plus an unread 2020 continuation must not finalize absence. |
| Synthetic date fields | Publication year, observation year, forecast horizon and revision date remain distinct. |
| Synthetic budget stop | Preserve verified partial facts and return insufficiency, never an absence claim. |

These are required future checks, not runs performed during this audit. A change is not
successful merely because it refuses the thirteen negative labels more quickly; it must
retain answerable controls and show a calibrated false-refusal rate. No question IDs,
company names, years or benchmark labels should enter production decision rules.

## Disposition and accounting

- No supported unqualified answer was found for the requested thirteen cases.
  Source-scoped abstention/explanation is appropriate for the six-plus-five group;
  corrected-premise handling and clarification are separate for 384/830.
- No runtime behavior, prompt or strictness was changed by this audit. No benchmark
  rerun, new API expense or automatic promotion to verified-refusal status occurred.
- Historical coverage remains **79 supported / 2 qualified / 4 verified refusals /
  35 unresolved** across 120 questions. The thirteen are unresolved terminal-workflow
  outcomes inside that total, not thirteen required numeric-answer recoveries.
- Next implementation order: typed reason/evidence retention with correct scope; fix
  the 728 partial-input diagnostic and 730 object-binding weakness; final explanation/
  clarification; then sequential negative-plus-positive regression under frozen limits.
- Existing development work is merged in PR 119; this audit is a separate documentation
  artifact. Raw selection/OCR/renders remain local/ignored; only this report is intended
  for version control. The unrelated TechQA semantic-scores.csv is untouched.

## Original-source manifest

Pinned input root: `data/benchmarks/mmlongbench-doc/2ff6aa9237fc777b6627dc57a486e9225ac5fb86/documents/`.
Hashes identify the exact originals inspected, not regenerated PDFs.

| Source | File | Pages | SHA-256 |
| --- | --- | --- | --- |
| S1 | `05-03-18-political-release.pdf` | 17 | `a1d9fc716060605412a10127c4e158febc9e2ae13af04cbcf88bcc789c474d49` |
| S2 | `PIP_Seniors-and-Tech-Use_040314.pdf` | 27 | `11fc8671985f4a810ed635ba2df7ae29c2fc0632de230b2a02386b2fbad08103` |
| S3 | `afe620b9beac86c1027b96d31d396407.pdf` | 20 | `a7b0ae685a743a0acedd57477fd20e3ad0a09e15ec73203b83ea531facb4e5d9` |
| S4 | `e79deb02a0c0e87511080836c5d4347b.pdf` | 17 | `ca33492fafca0831b1a248f5ce5e8015cbe1f858100e8ebce55c7224f32a175e` |
| S5 | `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf` | 18 | `b38932583846e5de2daadcf65376621de643541ad2ec54f37ec205e4ebfc8b80` |
| S6 | `measuringsuccessonfacebooktwitterlinkedin-160317142140_95.pdf` | 25 | `8d5e3496c76816158c84abc2155284bae16f713c7501bf8da10e58a2bf871374` |
| S7 | `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` | 23 | `9304adb2d85ad6065e05f832a6f315ea4f74bb4c30080fd103a0a0e014ae7111` |
| S8 | `f8d3a162ab9507e021d83dd109118b60.pdf` | 17 | `f2eb17a3ad57b7cf547da596a67f71b00c00d4c7e93d03a5ad9ec2d16c5618dd` |
| S9 | `BESTBUY_2023_10K.pdf` | 75 | `7ca465d31a08be29e8c08d756644d33d818c7254a1215720f265227005cda696` |

## Selected archived runs

Local run roots (raw outputs remain ignored):

| Rows | Run root | Tracked report |
| --- | --- | --- |
| 207, 209, 222, 365, 367, 521, 728, 830, 1084 | adaptive-remaining-thirty-20261020/rowN | [Report](../adaptive-remaining-thirty-20261020/REPORT.md) |
| 384 | adaptive-unseen-fifteen-20261019/row384 | [Report](../adaptive-unseen-fifteen-20261019/REPORT.md) |
| 508, 520 | adaptive-routing-scope-20261020/live-nine/rowN | [Report](../adaptive-routing-scope-20261020/REPORT.md) |
| 730 | adaptive-context-coverage-20261020/live-four/row730 | [Report](../adaptive-context-coverage-20261020/REPORT.md) |
