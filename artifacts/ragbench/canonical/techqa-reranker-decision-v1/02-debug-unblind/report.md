# TECHQA RERANKER DECISION — DEBUG UNBLIND

This is a Codex blind-review unblind, not independent human adjudication. The scorecard was frozen and hashed before the secret arm map was read. No semantic labels were changed.

## Semantic result

| | ON | OFF |
|---|---:|---:|
| Correct | 16 | 22 |
| Partial | 6 | 12 |
| Incorrect | 8 | 4 |
| Unavailable | 20 | 12 |

Strict: ON 16/50; OFF 22/50.  
Lenient: ON 22/50; OFF 34/50.

Pair preference: ON_BETTER=4, OFF_BETTER=16, TIE=28, BOTH_BAD=2. Net OFF preference=12.

## Frozen evidence and security

Evidence remains an independent operational axis: ON ANY=36/38, OFF ANY=37/38; ON ALL=29/38, OFF ALL=32/38; pre-existing prediction/recovery match=5/5. Frozen deterministic security accepted violations are all zero.

## Gate

- G1_security: PASS
- G2_off_incorrect_le_on: PASS
- G3_off_correct_plus_partial_ge_on: PASS
- G4_off_better_ge_on_better: PASS
- G5_off_evidence_all_gt_on: PASS
- G6_no_new_catastrophic_failure: PASS

DEBUG_GATE: PASS

Status: **RERANKER_OFF_READY_FOR_HOLDOUT**

HOLDOUT: not inspected, not run, and not touched. No forensic follow-up was run. Production config was not changed.
