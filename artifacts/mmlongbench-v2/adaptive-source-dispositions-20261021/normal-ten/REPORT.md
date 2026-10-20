# Ten answerable regression controls

21 October 2026. Sequential rows: **507, 519, 383, 1076, 832, 223,
727, 634, 1079, 1024**. These are ten previously source-verified answerable
questions from the [existing ledger](../../../../docs/adaptive-solved-questions.md),
covering five direct text/table lookups, three table/visual tasks and two ratios.
The selection spans nine documents and excludes the immediately preceding 380/387
positive controls.

## Protocol

One question at a time, with no parallel runs or runtime edits. Application Python
and the trace harness are frozen before measurement and checked before/after each
row. The existing gpt-6-luna fast-path/evidence-needs profile, retrieval, embedding,
parsers, model effort and hard limits are unchanged: ten main requests, 120,000
tokens and 240 seconds per question. A separate 360-second process ceiling covers
setup, retrieval and teardown too. No paid after-run reviewer is enabled.

Released answers will be compared with the earlier original-source findings after
all ten questions complete. A generic refusal is a failure for an answerable
question; a passing security check alone does not establish factual correctness.
Expected answers and benchmark labels are never added to runtime prompts.

## Results

**9/10 correct answers, one answerable question withheld, zero incorrect published
answers and zero technical terminal failures.** A safe refusal counts as a failure
in this answerable cohort. All ten subprocesses exited zero; all 164 frozen source
files remained unchanged. Published answers were compared with the earlier
source-verified ledger findings, not merely the security validator boolean.

| Row | Expected source-supported result | Released result | Run seconds | SDK requests |
| --- | --- | --- | --- | --- |

| 507 | Little Rock | Little Rock | 21.23 | 3 |
| 519 | eMarketer (Facebook audience) | eMarketer (Facebook audience) | 23.82 | 3 |
| 383 | Florida Department of Health | Florida Department of Health | 28.08 | 3 |
| 1076 | USD 1,874 million | USD 1,874 million | 25.55 | 3 |
| 832 | Unit 1: Understanding Economic Systems and Business; Unit 2: Making Ethical Decisions and Managing a Socially Responsible Business | Unit 1: Understanding Economic Systems and Business; Unit 2: Making Ethical Decisions and Managing a Socially Responsible Business | 21.93 | 3 |
| 223 | 90%, 42%, 39% | 90%, 42%, 39% | 69.15 | 8 |
| 727 | 12 Tweets = 24 - 12 | **Insufficient evidence — failed answerable control** | 104.61 | 10 |
| 634 | Fact Checker | Fact Checker | 84.02 | 9 |
| 1079 | 0.627 = 9912 / 15803 | 0.627 = 9912 / 15803 | 94.47 | 10 |
| 1024 | 0.304 = 8958 / 29441 | 0.304 = 8958 / 29441 | 41.16 | 7 |

Five direct lookups pass **5/5**, the table/visual group passes **2/3**, and the two
financial ratios pass **2/2**. Total main requests: **59**; summed in-run time:
**514.02 seconds**, mean **51.40 seconds**. The easy lookups each use
three requests. The difficult visual/math controls still consume nine or ten.

## 727: verified image input is overruled by parser text

Question: “How many more Tweets are attributed to Germanwings than Lufthansa?”
The original page 16 table reports Germanwings **24** and Lufthansa **12**, so the
supported result is **12 Tweets**. The indexed parser instead has Lufthansa **42**.
The original-page finding is also recorded in the
[prior source audit](../../adaptive-negative-thirteen-audit-20261020/REPORT.md).

The captured sequence is:

1. The fast answer reads the parser's 42 and proposes `24 - 42 = -18`; it is withheld.
2. Image collection opens page 16 and extracts **24 and 12**. Independent image
   review accepts both inputs, their coverage, identity and operation.
3. Application arithmetic computes **24 - 12 = 12** and retains its proof.
4. The semantic scope validator sees the conflicting indexed text and rejects the
   checked Lufthansa 12 because the parser shows 42.
5. Repair collects the image again, adding page 19; it again extracts **24 and 12**,
   and independent input review again accepts them.
6. The second semantic scope check again uses parser 42 to reject the result.
   All ten main requests are consumed; finalization safely abstains.

This is a source-authority conflict during scope validation. It is not missing
operands, a wrong arithmetic result, or a genuinely unanswerable question. The
checked values and computed 12 remain in typed state. The next correction should
preserve the authority of version-bound, independently checked visual inputs while
still checking entity, series, period and unit relationships. No runtime correction
or extra paid review was made during this measurement.

## Accounting and limits

These are ten reruns; no distinct question or historical success is added. Historical
ledger totals remain 79 supported answers / 2 qualified calculations / 15 correct
refusals / 24 unresolved. **727 is a current regression among the historical
successes**, recorded separately; those historical totals are not a claim that all
79 currently pass. The current positive cohort score is **9/10**, alongside
[11/11 accepted source-negative outcomes](../negative-eleven/REPORT.md).

Raw JSON, captures, spans, hashes and logs remain local and ignored. Dollar pricing
is not configured, so API dollar cost is unknown.
