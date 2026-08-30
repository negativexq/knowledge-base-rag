# TECHQA reranker final unblind and verdict

## Integrity

Amendment V2, the frozen scorecard, and the unblind protocol matched their required raw-byte hashes before arm-map access. The corrected arm map matched `72d3ad76356678c5d4d2e96d7e6c98a168cc86dc2c8a54bac02968fd71d213f1`, contained 50 unique query IDs, and assigned opposite arms per query. Frozen semantic labels were not changed.

## Semantic results

| | ON | OFF |
|---|---:|---:|
| Correct | 15 | 12 |
| Partial | 20 | 19 |
| Incorrect | 1 | 1 |
| Unavailable | 14 | 18 |
| Strict | 15/50 (30.0%) | 12/50 (24.0%) |
| Lenient | 35/50 (70.0%) | 31/50 (62.0%) |

OFF minus ON: Correct -3, Correct+Partial -4, Incorrect 0, Unavailable +4.

Pairwise: ON_BETTER 13, OFF_BETTER 12, TIE 25, BOTH_BAD 0; NET_OFF = -1.

Secondary effect: `NO_LARGE_DIRECTIONAL_EFFECT`.

## Frozen deterministic inputs

Shared RRF Top20: 40/41 ANY, 38/41 ALL, 95.905% recall. ON SectionAware: 33/41 ANY, 30/41 ALL, 77.875%. OFF SectionAware: 37/41 ANY, 33/41 ALL, 85.867%. Evidence G5 PASS. Security regressions are zero for both arms. Measured BGE latency is 98.70s p50, 251.40s p95, 293.58s max; G7 PASS.

Semantic unavailable reconciles exactly with operational abstention: ON 14 and OFF 18.

## Gates and verdict

G1 PASS; G2 PASS; G3 FAIL; G4 FAIL; G5 PASS; G6 PASS; G7 PASS. Semantic non-regression FAIL because G3 and G4 fail. Final architecture verdict: `BGE_REMOVAL_NOT_SUPPORTED`.

The exact 45-row secondary sensitivity excludes Q252, Q157, Q300, Q308, and Q283. It yields ON C/P/I/U = 14/16/1/14, OFF C/P/I/U = 12/14/1/18; ON_BETTER 10, OFF_BETTER 11, TIE 24, BOTH_BAD 0, NET_OFF_45 1. Direction sign changes, so robustness is LOW; sensitivity cannot override the primary 50-row verdict.

No semantic rescore, retrieval, model call, forensic, tuning, or production change was performed.

