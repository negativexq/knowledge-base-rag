# Original source authority and contextual provenance: final pair

## Findings

Both questions published correct answers under one frozen implementation. Row 729 changed from wrong 71 to correct 41 in 33.03 seconds / six calls, compared with 30.48 seconds / six calls for the wrong baseline. The selector chose text; application inspection found zero native text and raster coverage 1.0, promoted the source to images, and collector/checker read 24,12,5. Application arithmetic and final scope passed. No extra LLM stage or repair loop was inserted.

Row 525 changed from a ten-call / 62.70-second correct fallback to six calls / 40.42 seconds. Numeric source E1.S57 and context sources E1.S66/S67 reached the first final scope together; the original images supplied 16+16=32%. No reader/finalizer/retry loop was needed. Independent PDF reviews supported both answers.

The revision removed irrelevant count fields from arithmetic model projections, separated authorized numeric/context page roles, and added application receipts to reviewer packets. Tests: 2,112 passed, four skipped, five deselected; 66 focused tests, lint, and mypy passed. Published values 41.000 and 32.000 retained unnecessary decimals; content correctness did not imply bare-format exact matching. Historical distinct successes reached ten at this point, not ten rerun successes on this version.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 525 | 32.000 (calculation: 16 + 16 = 32.000) [E3.S1] [E1.S57] [E1.S66] [E1.S67] | 40.42 | 6 | 1 | True |
| 729 | 41.000 (calculation: 24 + 12 + 5 = 41.000) [E3.S1] [E1.S117] | 33.03 | 6 | 1 | True |

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
