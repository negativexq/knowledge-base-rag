# Five direct-lookup controls

## Findings

All five answers were published and supported by separate original-PDF reviews. Four questions used only need_planner, answerer, and scope_validator: three model calls and no tools. Row 368 needed an additional document search after the initial context mentioned Guntur without establishing both plant locations. Its six-call path found Andheri (Mumbai) and Guldhar (Ghaziabad), retaining the subsidiary ownership qualification.

The other answers were Rick Scott (387), 16 grams as integer 16 (472), Little Rock for AR01 (507), and 1,874 million USD (1076). The financial reading selected the January 28, 2023 cash-and-cash-equivalents cell rather than the 2022 value or restricted-cash-inclusive total. Total main-run time was 107.29 seconds and total model requests 18, excluding separate reviews and dependency loading. The code/settings matched the preceding two calculation checks: 7/7 selected checks on that version, 15 historical distinct successes, eight not rerun on that version.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 1076 | Best Buy reported cash and cash equivalents of $1,874 million as of January 28, 2023. [E2.S1] | 20.21 | 3 | 0 | True |
| 368 | The two plant locations are Andheri (Mumbai) and Guldhar (Ghaziabad). The source specifies that the Guldhar plant is owned by the company’s wholly owned subsidiary, International Tobacco Company Limited. [E3.S1] | 33.76 | 6 | 2 | True |
| 387 | The governor is Rick Scott. [E2.S1] | 23.09 | 3 | 0 | True |
| 472 | 16 [E2.S1] | 16.33 | 3 | 0 | True |
| 507 | The geographic market name for EPS Code AR01 is Little Rock. [E2.S1] | 13.9 | 3 | 0 | True |

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
