# Wrong chart or experiment setting: unresolved diagnostic

## Findings

No verified answer was released. The correct document was available, but the model selected a chart/experiment setting that did not establish the requested ProgramFC gold-evidence F1 comparison. Later stages could not recover a source-supported final answer within the run.

An independent PDF review located the relevant source values after the main run. That review cannot retroactively make the main response correct. This separated semantic source/experiment selection from the earlier literal quotation/schema problem; simplifying a schema did not by itself fix choosing the wrong evidence.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 642 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 77.44 | 7 | 3 | True |

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
