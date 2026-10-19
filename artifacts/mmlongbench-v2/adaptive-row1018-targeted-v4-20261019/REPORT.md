# Costco FY2021 debt / EBITDA: source-supported answer

## Findings

The published result was 1.344 = (799+6692+3916)/(6708+1781). Debt included the current portion of long-term debt and lease liabilities; EBITDA used the source-backed earnings/depreciation inputs. The original-PDF reviewer supported the result. Three incorrect intermediate computation drafts were rejected; earlier unsuccessful runs remain separate records.

The run stopped research at TOKEN_RESERVE but finalized a supported answer from saved work. It used nine model calls, two logical searches, and 68.02 seconds. Native authorized document search and source hand-off improvements reduced lost/missing inputs without collection-specific answer rules. Input/output/cached input usage was 97,137/2,330/4,640 tokens. A single development success did not establish repeated-run stability.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 1018 | Costco’s FY2021 total debt-to-EBITDA ratio was **1.344×**. Total debt is calculated as current and noncurrent long-term debt plus all lease liabilities; EBITDA is operating income plus depreciation and amortization. Amounts are in millions. (calculation: (799+6692+3916)/(6708+1781) = 1.344) [E1.S20] [E9.S1] [E6.S1] [E2.S1] | 68.02 | 9 | 2 | True |

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
