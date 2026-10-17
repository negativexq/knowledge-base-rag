# Loss audit — luna full run, 40/14, derived answers

Run: `luna-full-derived` (scoped retrieval, candidate_k 40, top_n 14, derived answers
on, PRs #46–#53). 47/100 answerable correct, 17/20 unanswerable refused. The 56 rows
that lost are below, read from each row's raw model output, failure codes and cited
unit texts.

| Loss | Rows |
| --- | ---: |
| Answerable, answered wrong | 16 |
| Unanswerable, answered | 3 |
| Answerable, validator blocked | 6 |
| Answerable, model abstained | 31 |
| Total | 56 |

The two other blocked rows (220, 384) are unanswerable and correctly refused.

## 1. Answered wrong (16)

The validator passed every one: each number is in a cited unit. The errors are which
number, which passage, or a question that needs data the answer did not combine.

- **Survey counts that need share × sample (4):** 206 (gold 541, answered 36%), 219
  (4087), 225 (1251; the model said the report gives only percentages), 227 (gold
  (87−31)% × 537 ≈ 301). The answer restates the share; the question asks for people.
  The sample size is in the units (`n=537`), so a calculation would verify.
- **Wrong quantity or hop (3):** 212 (gold 92% = 50 + 42, answered 48%, another
  row), 1070 (gold 0.10 percentage points, answered a 1.08% relative change), 229
  (gold 73.0 against a gap of 12; the gold looks like a different reading of the
  question).
- **Other definition (2):** 1016 (gold 10,314) and 1017 (gold 11,407): long-term debt
  and total debt read without the lease lines the gold includes.
- **Misread or incomplete (3):** 371 (Maniar counted 4 times, the table has 11), 396
  (21/14 against 23/21; a verified count checks that each item is in the support,
  not that the list is complete), 729 (24 + 42 + 5 = 71 against 41; the OCR'd table
  runs "first 24 hours" into the numbers).
- **Wrong passage or format (3):** 386 (another objective's row of the cited table;
  the gold is Objective B), 831 (another section's content), 368 (addresses less
  specific than the gold's).
- **Visual (1):** 634 (a color the text layer does not carry).

## 2. Unanswerable, answered (3)

- 471: the answer rejects the question's premise in words, yet states values, so it
  scores as answered.
- 635: a color asked about; the answer picked one from text that names no color.
- 660: a numeric premise ("port 10–13") the document does not have; the answer
  matched nearby port numbers.

A premise check on colors would refuse 471 and 635 (and turn 634 into an abstention);
660 needs the question's own numbers checked against the support.

## 3. Validator blocked, answerable (6)

| Row | Block | Cause |
| --- | --- | --- |
| 221 | INDETERMINATE | "(float format: 12.0)": `12.0` is typed VERSION, the support has `12` |
| 399 | count not verified | counted operands, `counts` null |
| 509 | calculation missing | a range count given without a calculation |
| 639 | value not in support | an invented "totaling 9%" |
| 741 | CALCULATION_RESULT_NOT_IN_ANSWER | "about 42%" against the result 41.67 |
| 1014 | value not in support | a derived sum with no calculation |

639 and 1014 are correct blocks. 221 and 741 are format: a trailing `.0` and a
rounded result. 399 and 509 follow the derived-answer rules only in part.

## 4. Model abstained, answerable (31)

- **Visual or layout (10):** 385, 393, 511, 636, 637, 661, 662, 663, 732, 829 —
  colors, boxes, figures, waveforms, counting across a page. The model sees only the
  text layer; no page image reaches it.
- **Financial ratios and multi-step derivations (11):** 380, 1018, 1020, 1023, 1072,
  1073, 1074, 1075, 1079, 1084, 1086. The operands span statements (income statement
  and balance sheet, two years); the model abstains rather than combine them.
- **Multi-hop survey or chart (5):** 210, 216, 524, 641, 642.
- **Counting or difference (3):** 381, 476, 727.
- **Gold in evidence, abstained (2):** 517, 1013 (385, 393, 511 and 524 above also have
  the gold in the evidence).

## What would move the score

| Fix | Rows | Kind |
| --- | --- | --- |
| Page images for visual questions | 10 abstained, 634, 635 | input |
| Share × sample as a calculation | 206, 219, 225, 227 | generation |
| Multi-statement financial derivations | 11 abstained, 1014, 1016, 1017 | generation |
| Premise check on colors | 471, 635 (634 abstains) | validator |
| `12.0` as a number; rounded result stated with "about" | 221, 741 | validator |
| List completeness for counts | 396, 371 | generation |
| Gold or OCR quirks | 229, 729 | none |

The validator now loses 2 answerable rows (221, 741); everything else is generation,
visual input, or the question. Visual input and multi-step financial derivation are
the two largest blocks (21 abstentions together).
