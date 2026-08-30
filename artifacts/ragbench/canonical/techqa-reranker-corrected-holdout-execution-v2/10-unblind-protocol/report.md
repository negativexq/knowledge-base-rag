# TECHQA reranker unblind decision protocol v1

This append-only protocol freezes interpretation rules for the already
completed corrected HOLDOUT blind review. It does not contain the arm map,
does not unblind any query, and does not calculate ON/OFF semantic totals.

## Frozen identities

- Amendment V2 SHA256: `22da15d58b5e29bacd3a5593f0d40a14c9c81e84b54f69179341cbdf865326a4`
- Frozen Codex scorecard SHA256: `7ebbc884f659f5f0625d76ed6b3ca81aef4d5dfb8ab2a3b4f0ba296dedc2f6c4`

The frozen scorecard remains immutable. Candidate A/B are treated as
per-query randomized mixtures; the supplied 16/16 blind unavailable and
14/18 operational abstention counts reconcile to 32, but do not identify
either arm.

## Primary rule

The authoritative Amendment V2 G1–G7 gate is copied without modification:

1. OFF deterministic security regressions = 0.
2. OFF Incorrect <= ON Incorrect.
3. OFF Correct + Partial >= ON Correct + Partial.
4. OFF_BETTER >= ON_BETTER.
5. Evidence non-inferiority: `ALL_OFF >= ALL_ON` and
   `mean_recall_OFF >= mean_recall_ON - 1 percentage point`.
6. No catastrophic OFF-specific query-class regression.
7. Meaningful measured reranker latency removal.

Semantic non-regression is PASS only when G2, G3, and G4 all pass. This is
separate from the secondary effect-size label.

## Secondary interpretation

`NET_OFF = OFF_BETTER - ON_BETTER`.

- `NET_OFF >= +8`: `CLEAR_OFF_WIN`
- `-7 <= NET_OFF <= +7`: `NO_LARGE_DIRECTIONAL_EFFECT`
- `NET_OFF <= -8`: `CLEAR_OFF_REGRESSION`

This is not a formal equivalence test and must not be reported as
`STATISTICALLY_EQUIVALENT` or `PROVEN_EQUIVALENT`.

## Sensitivity

The primary denominator remains all 50 rows. A secondary 45-row sensitivity
may exclude exactly Q252, Q157, Q300, Q308, and Q283 without rescoring them.
It cannot override the primary gate.

## Required next unblind sequence

Only after this protocol and the frozen scorecard hashes are verified may the
corrected arm map be opened in a separate task. That task must map every
query, evaluate G1–G7, calculate the secondary effect label and sensitivity,
and publish one of the three allowed final architecture verdicts. Frozen
semantic labels must not be altered.

No HOLDOUT rerun, provider call, semantic judge, production change, commit,
or push is authorized by this protocol task.
