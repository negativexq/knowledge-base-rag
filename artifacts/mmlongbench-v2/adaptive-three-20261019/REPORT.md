# Three new questions: source binding and continuation checks

## Findings

Rows 371 and 396 failed to publish verified answers; row 740 published source-correct dates [2015-03-24,2015-03-25]. Row 371's correct first total 30 was not preserved through scope/control flow. Row 396 lost the category continuation relationship needed for [22,21].

The full raw parser view narrowed the reviewer's explanation: relevant content existed in the admitted evidence, so the failure cannot be described as retrieval never finding it. Source grouping and category boundaries were mishandled downstream. Row 740 found a missing date and retained the correct event/report association. These outcomes motivated quantitative inventories, proof shaping, and preservation of successful work, not a blanket increase in model effort.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 41.47 | 10 | 0 | True |
| 396 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 94.94 | 10 | 1 | True |
| 740 | ["2015-03-24", "2015-03-25"] [E2.S1] [E1.S2] | 24.9 | 5 | 1 | True |

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
