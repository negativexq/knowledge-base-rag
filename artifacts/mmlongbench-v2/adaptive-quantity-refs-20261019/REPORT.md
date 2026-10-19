# Exact source references: first pair

## Findings

Row 371 published 30.000 after replacing model-copied text quotations with source ranges resolved by application code. Three operands were bound to the relevant table segment, and normal source/scope checks passed.

Row 396 failed before tool execution because the optional need plan corrected the question typo metioned to mentioned and therefore failed literal question binding. The planning hint had become an unnecessary gate. The later optional-plan fallback addressed that class of failure; this pair remained 1/2.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | 30.000 (calculation: 14 + 5 + 11 = 30.000) [E3.S1] [E1.S24] | 40.26 | 5 | 1 | True |
| 396 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 46.44 | 9 | 0 | True |

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
