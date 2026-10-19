# Two sequential questions with a frozen implementation

## Findings

Both published answers were source-correct under the same code/settings. Row 210 used sufficient text and returned 21% without extraction. Row 642 recovered from an incorrect first draft by reading visual evidence and returned gold-evidence F1 values 64.4, 62.5, 62.2 for HOVER 2-hop, 4-hop, 3-hop.

The stored label [64.3,62.4,62.2] differs from standard one-decimal rounding of source values 64.35 and 62.46. This report records source correctness, not exact label matching. The output also used explanatory lines rather than the requested bare list.

The historical price-based estimate was USD 0.0015185 main + 0.0014293 review for row210, and 0.0061681 main + 0.0022958 review for row642: 0.0114117 total. These are recorded estimates, not current pricing or billing evidence. Both questions had been reused during development; this was not held-out evaluation.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 210 | 21%. The Democratic Party had the higher combined figures for good policy ideas and high ethical standards (50% + 42%, versus 50% + 41% for the GOP); 21% of Democrats and Democratic leaners said they followed congressional-election news very closely. [E2.S1] [E2.S1] | 28.25 | 3 | 0 | True |
| 642 | ProgramFC F1 scores with gold evidence for Flan-T5-small, descending: HOVER (2-hop): 64.4; HOVER (4-hop): 62.5; HOVER (3-hop): 62.2. [E3.S1] [E4.S1] [E5.S1] [E6.S1] | 66.11 | 8 | 1 | True |

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
