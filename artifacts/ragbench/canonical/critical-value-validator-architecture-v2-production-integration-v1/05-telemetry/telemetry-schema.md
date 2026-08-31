# Telemetry schema and privacy

The request span may carry only bounded metadata:

- architecture identifier or `none`;
- validator outcome, reason class, duration, and forced-abstain boolean;
- occurrence and role counts;
- shadow enabled/error booleans, outcome, disagreement, and bounded error class.

No raw query, answer, claim, evidence, support text, prompt, critical
literal, normalized literal, occurrence span text, or occurrence ID is sent
to OTel. Per-request occurrence details remain local forensic data only.

Architecture V2 forensic details are nested in the existing opt-in local
capture path. With raw capture disabled, raw claim/literal fields are omitted;
with raw capture enabled, existing local forensic policy applies. Both
forensic switches remain disabled by default.
