# V4 contract validation failure analysis

## Blocking gate

G9 MULTI_OCCURRENCE_SAFETY: FAIL.

C50 contains two textual `30` occurrences with different adjudicated roles. The first is the rejected question premise and should be `SKIP_REJECTED_PREMISE`; the second is a substantive negative assertion and should remain `VALIDATE`. The frozen occurrence comparison recorded `VALIDATE` for both occurrences under V4.

The direct implementation evidence is that the first occurrence is tokenized as `NUMBER` while the second is tokenized as `DURATION` because it appears in `30-day`. V4 pairing requires a same-kind/same-unit companion, so the first occurrence was not deterministically paired and was not skipped.

This is not an unsafe assertion skip and does not indicate a V4 mutation. It is a failure to satisfy the required occurrence-role distinction. The population and source remain frozen; no relabeling or patch was made after execution. Future work is V5.
