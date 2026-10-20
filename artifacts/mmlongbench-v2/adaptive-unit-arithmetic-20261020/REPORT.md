# Source-scale arithmetic and bounded numeric functions

Date: 20 October 2026. Branch: `fix/arithmetic-unit-scale-conversion`, based on
main `f98df09`. This measures calculation boundaries without changing embeddings,
retrieval, reranking, source data, model settings or research budgets.

## Implementation

- Preserve source displays and canonical Decimal values separately from source-to-base
  factors and output conversion. A typed `QuantityArithmeticConversion` records units,
  factors, the named-input formula and application-expanded expression in ResearchState,
  normalization spans, checker input and proof evidence.
- Apply lakh/lac, crore, thousand, million and billion factors in application code.
  Same-currency factors cancel in ratios; requested output scale applies once.
  Mismatched unit identities and unsupported compound dimensions fail before execution.
  No currency exchange is inferred. Explicit source scales remain independently reviewed.
- Support `abs`, `min`, `max`, `mean` in quantity execution and source-literal verification;
  add `abs` to the existing fact calculator. Function names are operators rather than
  missing operands. Attributes, imports, keyword/starred arguments and other functions
  cannot execute. Every argument requires source support, including unselected extrema.
- Preserve literal Decimal precision, bound expression complexity and numeric magnitude,
  and round only the final result. Zero division and invalid arity fail locally.
- Final semantic projection reexecutes the operation and compares its conversion receipt;
  an absent or tampered receipt cannot gain arithmetic-only validation authority.
  Source bindings, period, scale, formula interpretation and scope remain independently checked.
- No new calculation model call is introduced. The model selects an interpretation and
  transcribes source inputs; application code executes the prepared operation.

## Frozen sequential measurement

`live-five`: **380, 366, 1021, 741, 1086**, in that order. All application Python files
and the unchanged trace harness were hashed before/after; the snapshot stayed identical.
Same gpt-6-luna profile, ten main requests, 120,000 tokens and 240 seconds. No gold values
or reference-page overrides enter generation. Separate reviewers run after generation.

| Row | Released result | Main time | Main requests | Interpretation |
| --- | --- | --- | --- | --- |
| 380 | **8,367,277,000 rupees** | 50.29 s | 6 | Recovered. Both source values and their lakh-to-rupee factors are used. |
| 366 | **35.821%** relative shortfall | 58.34 s | 6 | `abs` executes correctly; qualified metric interpretation, not an unconditional gold match. |
| 1021 | **0.715** | 63.78 s | 9 | Correct ratio retained via sourced text calculation after collector failure. |
| 741 | **41.667%** | 41.80 s | 6 | Correct percentage retained, including its mathematical factor of 100. |
| 1086 | No verified answer | 69.22 s | 9 | Correct 13,929 million computed/checked, but proof admission and finalization fail. |

Sequential wall time including startup and separate reviews: **448.83 seconds**.
Four answers were released; three are unqualified source-supported answers and one
has an explicit defensible metric convention. This is a targeted diagnostic cohort,
not a new 120-question benchmark score or a causal timing estimate.

## Source and trace audit

- **380:** original financial statements, physical pages 18–19, show 25,966.14
  shareholders’ funds and 109,638.91 income, in lacs. The expanded operation is
  `(109638.91 * 100000) - (25966.14 * 100000)`, yielding 8,367,277,000 rupees.
  Separate review supports both transcriptions, period and conversion. Previously the
  arithmetic kept the raw lakh numbers while labelling the output rupees.
- **366:** the original first page states India forecast growth of 6.7% and achieved
  growth of 4.3%. The published interpretation is relative shortfall:
  `abs((6.7 - 4.3) / 6.7) * 100 = 35.821%`. The absolute gap is 2.4 **percentage points**.
  Function support fixes execution, not the ambiguous metric definition. This moves
  the row to qualified interpretation, alongside 1072, rather than certifying the gold label.
- **1021:** the balance sheet shows 29,441 current liabilities and 41,190 total
  liabilities. Their quotient rounds to 0.715. A checker proposes canonical notation
  for valid comma-grouped displays; replaying the captured draft/check raises
  `NUMERIC_NOTATION_ALREADY_VALID`. The collector remains pending. The sourced text
  calculator recovers the final answer; this is not a clean collector regression pass.
- **741:** the original page links ten English tweets and 24 total tweets in the same
  scope. `10 / 24 * 100` remains 41.667%, with no added unit-scale multiplier.
- **1086:** repaired original-image inputs are independently accepted; the application
  computes `(15803*1000000 - 1874*1000000)/1000000 = 13929.000` million. Its checked
  proof block is excluded by the evidence budget, then finalization fails at
  `REQUEST_RESERVE` / `ADAPTIVE_FINALIZATION_FAILED`. ResearchState retains the completed
  record; the final answer does not publish it. The separate reviewer lacks the actual
  target balance-sheet/cash-table images, a previously known review-coverage limitation.
  Prior manual source review and the historical successful ledger entry remain recorded.

## Proof serialization follow-up

The initial failed 1086 attempt is preserved. Checked-proof JSON now omits formatting
whitespace while retaining every field, witness, input and conversion receipt. No quote
is shortened, no additional model call is added and the evidence budget is unchanged.
A separate frozen `compact-proof` run measures only 1086 after this serialization change.
The follow-up also abstains: **71.00 seconds, nine main requests**. The application
again independently accepts and computes **13,929 million**, but its proof is excluded
by the evidence budget and finalization fails at `REQUEST_RESERVE`. Compact serialization
alone does **not** fix this boundary. Both source snapshots remain unchanged within
their respective runs; the first five-row outcome is not rewritten. No further paid
rerun is made. A future correction must preserve independently checked result evidence
through budget-aware admission/finalization, without increasing limits or dropping quotes.

## Validation and accounting

- Final full suite: **2,310 passed, 4 skipped, 5 deselected** (52.60 seconds).
- Ruff and mypy pass, covering 159 application files.
- Tests cover signed accounting inputs, mixed magnitude ratios, percentage factors,
  output scales, precision/rounding, zero division, disallowed calls, mismatched units,
  immutable source displays, independent source-scale rejection, exact state roundtrip,
  and stale/tampered conversion receipts in semantic projection.
- Historical coverage is **120 distinct questions: 78 source-supported answers,
  2 qualified calculations, 4 verified refusals and 36 unresolved outcomes**.
  Reruns do not increase distinct-question coverage. Existing successful control rows
  remain historical successes; this report explicitly preserves new failed attempts.
- Pricing for gpt-6-luna is not configured: API cost is **unknown**, not zero.
  Raw results, token usage, separate reviewer usage, source snapshots, spans, captures
  and logs remain local/ignored; only this Markdown report is tracked.
