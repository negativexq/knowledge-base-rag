# Rollback plan

Trigger rollback on any hard safety trigger, attributable runtime exception
increase, or an unexplained shadow/canary disagreement pattern. Soft triggers
pause expansion and require review.

Action: set the server-side validator selector back to `baseline` and restart
or redeploy only if the chosen configuration mechanism requires it. Verify
the active configuration fingerprint, baseline validator outcome counters,
and absence of V3 traffic before resuming normal service.

The rollback requires no reindex, data migration, model reload, data rewrite,
retrieval change, or artifact regeneration. Exact recovery time is deployment
dependent and is not specified here.
