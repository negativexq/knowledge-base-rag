# Validator V5 multi-occurrence polarity DEBUG report

This was a deterministic DEBUG challenger run, not a production change and
not a new TechQA HOLDOUT. The primary scoring unit was the
`CRITICAL_VALUE_OCCURRENCE`; 60 cases contained 134 scored occurrences.

## Candidate and integrity

The frozen V4 helper region remained byte-identical at
`a04edc0bfd6430af89077e1ef9a961fad2edeccb0e14bcd3a106a16a58adebf6`. The V5
source file hash was unchanged before and after execution. V5 remained outside
the production `baseline|v3` selector.

The population and adjudications were frozen before either arm executed. The
population was freshly authored and did not reuse the V4 independent
population. Corrected HOLDOUT was not used; provider calls were all zero.

## V4 reproduction versus V5

| metric | V4 | V5 |
|---|---:|---:|
| real assertions incorrectly skipped | 0 | **1** |
| ambiguous occurrences incorrectly skipped | 0 | 0 |
| rejected premises not skipped | 23 | **1** |
| correct rejected-premise skips | 18 | 40 |
| corrective recovery | 43.90% | 97.56% |
| multi-occurrence role errors | 22 | 1 |
| duplicate-literal global collapse errors | 18 | 0 |
| type-mismatch role errors | 7 | 0 |
| security regressions | 0 | 0 |

The V5 improvement is real on duplicate occurrence separation, including the
C50-like anchor. It is not safe enough for selection because it introduced an
unsafe skip in a frozen regression case.

## Blocking safety finding

`C57.O2` is the second occurrence of `204` in:

> The signed result is -204, not 204.

It is ground-truth `VALIDATE`, because the positive `204` is part of a
sign-sensitive comparison and must remain a validation obligation. V4 kept it
as `VALIDATE`; V5 classified it as `SKIP` due the nearby `not` separator and a
same-value sibling. This is an unsafe assertion skip and a V3/V4 regression.

This is preserved as a V5 failure artifact. V5 is not patched in place; future
polarity work becomes V6.

## C50-like anchor

`C48.O1` (`30`, NUMBER) expected `SKIP`, V4 `VALIDATE`, V5 `SKIP`.

`C48.O2` (`30 days`, DURATION) expected `VALIDATE`, V4 `VALIDATE`, V5
`VALIDATE`.

The result demonstrates that V5 uses exact spans and same-surface sibling
identity rather than a global normalized-value mask. This anchor is regression
evidence only and is not independent proof by itself.

## Gate decision

G1, G3, G4, G5, G6, G7, G8 and G10 pass. G2 and G9 fail because of `C57.O2`;
therefore the all-gates requirement is not met. No selected V5 candidate
freeze preview was created.

## Scope discipline

T4 boolean normalization, T6 unit equivalence, T10 version semantics, V3/V4
artifacts, production defaults, retrieval, BGE, and the consumed HOLDOUT were
unchanged. No production selector entry was added, and no provider or
retrieval calls were made.
