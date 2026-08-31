# C50-like regression anchor

The fresh anchor is C48; it is not reused as the V4 independent population case.
V5 uses exact occurrence spans and same-surface sibling discovery across the answer.

- C48.O1: raw='30', type=NUMBER, span=0:2, expected=SKIP, V4=VALIDATE, V5=SKIP
- C48.O2: raw='30 days', type=DURATION, span=52:59, expected=VALIDATE, V4=VALIDATE, V5=VALIDATE
