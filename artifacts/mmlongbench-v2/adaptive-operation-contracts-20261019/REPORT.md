# Operation-specific extraction contracts: first paired recheck

## Outcome

**Six frozen rechecks: one source-correct financial calculation, one justified refusal, four unanswered questions.** No incorrect substantive answer was published, but the unanswered cases are not successes. The financial output omitted its percent sign despite computing a percentage explicitly; this presentation defect remains material to readability. This is not a full benchmark result.

The three previous failures (372, 661, 221) were followed by successful arithmetic, visual-list, and unanswerable controls (1020, 385, 220). Each row ran once, sequentially, with `gpt-6-luna`, fast path, evidence needs, original-source review, and the unchanged ten-request/120,000-token/240-second ceilings. The model settings, existing source-scoped index, embedding and retrieval configuration were unchanged. Main generation received no reference answer or benchmark reference pages. Runtime files were frozen before the first paid call; local selection and per-row profiles preserve hashes. No runtime changed during the six runs.

| Row | Published output | Baseline → recheck seconds | Baseline → recheck calls | Tools | App retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 372 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 63.84 → 61.60 | 7 → 9 | 1 | 1 |
| 661 | I could not obtain enough evidence to answer this question. | 85.91 → 76.98 | 10 → 7 | 2 | 0 |
| 221 | I could not obtain enough evidence to answer this question. | 58.50 → 70.97 | 8 → 8 | 2 | 0 |
| 1020 | 25.04 (calculation: (6692 + 2642 + 980) / 41190 * 100 = 25.04) [E3.S1] [E1.S16] [E1.S47] | 50.67 → 38.48 | 8 → 6 | 1 | 0 |
| 385 | I could not obtain enough evidence to answer this question. | 59.86 → 55.83 | 6 → 9 | 4 | 0 |
| 220 | I could not obtain enough evidence to answer this question. | 85.71 → 84.45 | 9 → 6 | 1 | 1 |

## What changed and what the runs demonstrated

Source selection chooses an operation in its existing model call. The application generates only that operation's native output schema: read, arithmetic, count, selection or list. Image extraction selects enumerated application-owned image handles, which resolve to immutable document versions and physical pages. Missing-list coverage can seek another source view and retain the list goal; ordinary slot repair remains separate. No extra planning call was introduced.

- **372:** The list schema worked, but the collector again selected three Audit Committee members. This time the input checker falsely accepted complete-company coverage. Final scope review correctly rejected the incomplete roster. The valid scope objection was stored but did not start another source search; the system instead repeated scope/finalization work. The new coverage-repair path was therefore not exercised by this real run. Company-wide original page 9 contains the five required names. This exposes a missing release-review-to-research handoff, not a reason to waive scope validation.
- **661:** The new direct-read image contract ran correctly, with image_2 bound to physical page 16. The model identified P2.7 ENABLE but explicitly marked the numeric value as unspecified and the draft incomplete. Review independently found no numerical scale on the trace. Repair attempted a source window exceeding the three-page bound and failed; no value was invented. The reference label is 0.0 V, supported only as a plausible interpretation using VSS=0 V elsewhere, not an explicitly annotated waveform voltage. This remains an unresolved reference-answer case; a defensible refusal is not counted as benchmark answer success.
- **221:** Extraction correctly returned 65% and 53%, subtraction, and image handles resolving to physical pages 16 and 17. The original cross-mode schema and printed-page-number failures disappeared. The checker then rejected a valid absolute difference as ambiguous because a relative percentage difference could also be imagined. Repair incorrectly reread sparse text and lost usable image evidence. The right general response is to evaluate and display a defensible explicit interpretation, preserve correct inputs, and reserve ambiguity for a material unresolved choice.
- **1020:** The application executed `(6692+2642+980)/41190*100 = 25.04` with a checked original-source receipt in six calls, versus eight baseline calls. No irrelevant count-mode rejection occurred. The released text lacked `%`; output-unit/interpretation metadata needs to reach rendering.
- **385:** The selector returned available=false without starting image collection. Subsequent extraction/search/inspection did not recover the strategy-map page. This regresses the previously successful three-heading question. Parser unreadability or missing layout must not be conflated with the availability of a plausible authorized region for visual inspection.
- **220:** The requested 2022 headcount remained unsupported by the 2014 report's 2013 survey, so the abstention remains appropriate. Tool attempts fell from five to one, but this single run is not a termination-policy proof.

The after-run reviewer returned true for 385 despite the unanswered output, and found 661's refusal defensible. Those booleans are not used as task-success labels. Source-answer accuracy, published-answer coverage, provenance and output clarity remain separate checks. Row 221's benchmark reference pages 7–8 omit the male rows; manual source checking uses actual physical pages 16–17.

## Follow-up implementation

A separate worktree was used while this batch ran. The follow-up carries valid grounded final-scope objections into one bounded source-repair attempt, preserves the operation and original receipt, and rechecks replacement evidence. It also exposes reviewed arithmetic result-unit and interpretation fields to rendering, and clarifies that source availability means inspectability rather than an already readable answer. Full checks and a fresh frozen run are required before claiming these remaining cases fixed. These follow-up changes are not included in the results above.

## Usage and storage

Main calls: **45**, **388.31 seconds**, **161,885 input tokens**, **26,825 output tokens**, **11 tool attempts**, **2 application retries**. Separate reviews are excluded from main usage. Model prices were not configured, so dollar cost is unavailable rather than zero.

Raw JSON, model captures, typed state, review packets and spans remain local and ignored. Only this English summary is intended for Git. The baseline and every failed attempt remain retained; reruns do not add new distinct questions to the ledger.
