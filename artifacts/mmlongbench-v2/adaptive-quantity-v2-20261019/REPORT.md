# Quantitative evidence and proof formatting: repeated checks

## Findings

Rows 371 and 396 published correct answers; row 740 retained correct dates. Row 371 returned 30 through the ordinary reader path after the new collection tool failed its text-plus-pages argument contract. Therefore its answer was correct but this run did not prove the new collection path worked end to end. Row 396 did complete the new visual inventory path and application counting for [22,21].

Row 740 still answered the two dates as sentences rather than the requested list. Source correctness and strict output-format compliance were reported separately. Mode-specific total/distinct handling and readable proof segmentation addressed earlier failures; a successful fallback was not mislabeled as successful tool execution.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | Collectively, the three directors hold Board directorships at 30 companies (R.A. Shah: 14; S.V. Shanbhag: 5; C.M. Maniar: 11). This follows the report’s count of memberships of other companies, which excludes private-company and alternate directorships. (calculation: 14 + 5 + 11 = 30) [E1.S24] [E1.S25] | 33.66 | 4 | 1 | True |
| 396 | [22, 21] (Strengths, Weaknesses) (count: 22 listed items) (count: 21 listed items) [E3.S1] [E1.S59] [E1.S60] | 49.06 | 5 | 1 | True |
| 740 | Incident date: 2015-03-24 Report date: 2015-03-25 [E1.S10] [E1.S2] | 25.8 | 6 | 1 | True |

## Scope and records

These are selected development diagnostics scoped to the source document, not
an open-corpus retrieval score or a complete benchmark. A reviewer support flag
alone is not a success: an abstaining response is not counted as a published
answer. See the findings for source correctness, formatting differences, and
any limitations of the review packet. Main generation did not receive gold
answers; separate diagnostic review occurred afterward.

Reported main-run latency excludes dependency loading and separate PDF review.
Model usage is recorded in local result files; reviewer usage is separate.
A null cost field means prices were not configured, not that calls were free.
Historical price estimates, where stated, are not current pricing or billing.

The underlying measurements, source snapshots, full typed state, model outputs,
spans, profiles, and independent reviews remain unchanged in local run folders.
Raw JSON/JSONL, images, captures, source capsules, and original-language report
backups are ignored by Git. This English summary retains the outcome and main
failure mechanisms; later successful runs do not overwrite earlier failures.
