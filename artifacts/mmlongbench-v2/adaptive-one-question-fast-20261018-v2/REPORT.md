# Prepared evidence and application-resolved quotations

## Findings

The source-supported 21% answer passed numeric/support checks and semantic scope. Application-resolved quotation boundaries avoided asking a model to reproduce exact source prose.

Recorded comparison: successful v5 used seven calls, 45,017 input / 3,187 output tokens, 60.55 seconds; the first failed short-path attempt used six calls, 23,589 / 1,821 tokens, 42.74 seconds; this revision used two calls, 5,157 / 720 tokens, 26.17 seconds. This is a paired development diagnostic rather than a general latency guarantee.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 210 | 21%. The Democratic Party has the higher combined figure (50% saying it has good policy ideas and 42% saying it has high ethical standards, versus 50% and 41% for the GOP). Among Democrats and Democratic leaners, 21% said they followed congressional-election news in their state or district very closely. [E2.S1] | 26.17 | 2 | 0 | True |

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
