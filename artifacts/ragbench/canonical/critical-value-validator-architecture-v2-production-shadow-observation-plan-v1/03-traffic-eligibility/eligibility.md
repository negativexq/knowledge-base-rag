# Traffic eligibility contract

The future activation task must record, using bounded counters only:

- total requests;
- eligible validator requests;
- ineligible requests by bounded exclusion reason;
- Architecture V2 shadow executions; and
- environment failures that prevented execution.

An explicitly classified environment failure is not a semantic Architecture V2
failure, but a missed eligible execution still lowers coverage and must be
explained. Health probes never enter the coverage denominator.
