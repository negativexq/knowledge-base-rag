# Initial quantitative input workflow

## Findings

Rows 371 and 396 did not release an answer. Correct item inventories and provisional values survived in state, but per-group versus aggregate operation handling and an oversized single-line JSON witness blocked final scope. Row 396 had source-correct [22,21] data; that is not a published-answer success.

Row 740 preserved the correct two dates but returned sentences rather than the requested list. Subsequent revisions separated per_group/total/distinct operations and split proof text into bounded source segments. These are extraction/control-flow failures, not evidence of an embedding failure.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 89.74 | 10 | 1 | True |
| 396 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 68.6 | 10 | 1 | True |
| 740 | Incident date: 2015-03-24. [E1.S10]  Report date: 2015-03-25. [E1.S2] | 21.34 | 5 | 1 | True |

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
