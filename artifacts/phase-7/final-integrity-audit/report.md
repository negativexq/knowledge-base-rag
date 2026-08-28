# Final Integrity Audit + Architecture Closure

Historical integrity: PASS.  Preregistration, V2.2 baseline, initial V2.3 result, and all 15 frozen evidence snapshots matched their recorded hashes.

Execution symmetry failed retrospectively because V2.2 did not record `num_predict`, while V2.3 was bounded at 1024. The permitted corrected rerun therefore executed both arms on the same frozen snapshots with `num_predict=1024`: V2.2 40/40 and V2.3 40/40, provider failures 0.

Corrected paired result: 0 clearly better, 3 clearly worse, 5 equivalent/unstable. Clearly worse: multi-01-2, multi-01-3, multi-01-0. Clearly better: none.

ACL lineage matched the final challenger configuration; the frozen ACL result was reused: unauthorized leakage 0, visible unsupported 0, hard gate PASS.

The one-time +8 extension was not run because only one eligible unseen development multi-document query remained after the initial holdout and debug set. No calibration or frozen-test query was used.

## Decision

`V2_3_REJECT`; keep `pipeline_v2_2_evidence_backed`. The corrected run met the preregistered clear-regression condition (clearly worse >= 3/8). No Smoke36 or Development200 run was authorized for rejected V2.3. No V2.4 or additional architecture experiment was opened.

Manual scoring disclosure: corrected-rerun scoring was blinded to pipeline/variant identity, but the grader had prior exposure to initial outcomes, so contamination cannot be fully excluded.
