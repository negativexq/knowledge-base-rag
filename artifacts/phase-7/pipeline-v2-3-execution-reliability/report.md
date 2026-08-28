# V2.3 Contract Execution Reliability + Paired Decision

## Execution

The historical V2.3 request contract produced 30 completed rows and 2 pre-header READ_TIMEOUTs. Offline forensic measurements found no size outlier: the timeout request had 14 support units, a 467-byte enum schema, 584 context tokens, and an 8,591-byte request. Server logs show the runner was actively decoding until client cancellation.

## Root cause and fix

A full-enum request with a bounded `num_predict=1024` completed both formerly failing requests. The fix is execution-only and preserves exact application support-ID membership validation. The old 30 rows are historical and are not mixed into the official comparison because request options changed.

## Official paired execution

The new V2.3.2 bounded-output run completed 40/40 holdout and 15/15 ACL calls, with 0 provider failures. The preregistration hash matched. Blind authored-fact review yielded 2 clearly better and 2 clearly worse holdout queries, so the frozen rule returns `V2_3_INCONCLUSIVE_EXPAND_ONCE`. ACL hard safety passed: 0 unauthorized leakage and 0 visibly unsupported answers in the reviewed set. No 36/200 run was started.
