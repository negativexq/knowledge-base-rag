# Eleven source-negative questions: sequential acceptance check

21 October 2026. Requested rows: **207, 209, 222, 365, 367, 1084,
508, 520, 521, 728, 730**. Original-source findings are recorded in the
[thirteen-question audit](../../adaptive-negative-thirteen-audit-20261020/REPORT.md).
384 (correctable revision premise) and 830 (clarification) are outside this batch.

## Acceptance criterion

The user explicitly accepts a safe “answer not found” outcome for these
source-negative questions. It need not repeat unrelated available values or
generate a strong document-wide absence certificate. A source-grounded mismatch
explanation is also acceptable. An invented value, silent substitution of entity,
period or series, or a technical finalization failure is not accepted.

This criterion evaluates the released response against the prior source audit.
It does not require the runtime to generate a new source-disposition receipt or
claim exhaustive document coverage. Earlier stricter source-disposition diagnostics
remain recorded; they are not the acceptance gate for this requested batch.

## Protocol

- One sequential batch; no parallel question runs.
- Frozen application Python and trace harness hashes, checked before/after each row.
- Existing gpt-6-luna fast-path/evidence-needs profile and unchanged retrieval,
  embedding, parser, model effort and global budgets.
- At most ten main requests, 120,000 tokens and 240 seconds in the application.
  A 360-second subprocess ceiling also includes setup/retrieval/teardown.
- No paid after-run reviewer and no runtime changes while questions run.
- Inspect released answers only after all eleven runs complete.

## Results

**11/11 accepted safe negative outcomes; zero invented answers and zero terminal
technical failures.** Every run publishes “I could not obtain enough evidence to
answer this question.” Security validation accepts each model abstention with no
failure codes or application-forced abstention. No stronger document-wide absence
claim is made.

| Row | Source issue | Released outcome | Run seconds | SDK requests |
| --- | --- | --- | --- | --- |

| 207 | Requested 2022 survey; source is 2018 | Safe answer not found | 67.18 | 9 |
| 209 | Biden request; source concerns Trump | Safe answer not found | 127.88 | 9 |
| 222 | Requested 2022 operand is unavailable | Safe answer not found | 62.38 | 9 |
| 365 | Apple request; source company is GPI | Safe answer not found | 68.79 | 9 |
| 367 | Japan/time-series request; source is India FY2003 | Safe answer not found | 73.96 | 9 |
| 1084 | AMCOR request; source is Best Buy | Safe answer not found | 81.97 | 9 |
| 508 | AR03 mapping not listed | Safe answer not found | 46.17 | 6 |
| 520 | Google audience-data attribution not reported | Safe answer not found | 53.95 | 9 |
| 521 | Amazon audience-age series not reported | Safe answer not found | 71.76 | 9 |
| 728 | Boeing operand unavailable for the difference | Safe answer not found | 99.37 | 9 |
| 730 | Boeing tweet count not reported | Safe answer not found | 65.17 | 9 |

Total main requests: **96**. Total in-run time: **818.58 seconds**;
mean **74.42 seconds**. Ten questions use nine requests and 508 uses six.
The negative-response behavior meets the requested criterion; repeated research
before abstention remains an efficiency concern. No new runtime fixes were made
for this batch. All 164 frozen source files remain unchanged.

## Ledger update

The prior original-PDF audit establishes that these requested answers are not
supported. Combined with these clean live negative outcomes and the user's
explicit acceptance criterion, all eleven move from unresolved to correct refusals.
They are not counted as positive document answers or as new runtime absence
certificates. Historical totals are now **79 supported answers / 2 qualified
calculations / 15 correct refusals / 24 unresolved**, across the same **120 distinct
questions**. No new questions were added. Correct positive controls 380 and 387
are recorded in the [preceding regression batch](../answer-local-validation/REPORT.md).
384 and 830 were not rerun here and remain separately tracked.

Raw JSON, captures, spans, hashes and logs remain local and ignored. Dollar
pricing is not configured, so API dollar cost is unknown.
