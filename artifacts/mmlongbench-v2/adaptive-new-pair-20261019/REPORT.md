# Two new questions with unchanged code

## Findings

One correct published answer out of two. Row 729 published 71.000 from 24+42+5, but the original physical page 16 shows 24,12,5 and total 41. Both the independent reviewer and a separate visual inspection confirmed the mismatch. Correct document/page retrieval did not prevent a wrong indexed number from propagating through text-only collection, checking, arithmetic, and scope. PyMuPDF get_text returned no embedded text on that page; this run did not identify the exact upstream OCR/parser responsible.

Row 525 correctly identified Twitter and summed 16+16=32%. The typed calculation survived a failed first scope check: numeric evidence lacked the metric-to-platform relationship in its candidate. The first objection also used invalid question-segment references. Finalization later included the relationship evidence, survived one formatting/value retry, and published the correct answer after ten model calls. QUANTITY_REVIEW_UNRESOLVED therefore did not imply that final release was abstaining.

The unstarted easier row 478 was replaced with multi-hop row 525 when the user requested difficult questions. No paid row 478 run occurred. There were no code changes between 729 and 525. The source-authority and context-carrying fixes were subsequent work, not retroactive changes to these results.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 525 | The total is **32%** (16% for White, Non-Hispanic plus 16% for Hispanic among online adult users in 2013). The listed metrics identify Twitter. (calculation: 16 + 16 = 32%) [E2.S1] [E3.S1] [E1.S57] | 62.7 | 10 | 1 | True |
| 729 | 71.000 (calculation: 24 + 42 + 5 = 71.000) [E3.S1] [E1.S117] | 30.48 | 6 | 1 | False |

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
