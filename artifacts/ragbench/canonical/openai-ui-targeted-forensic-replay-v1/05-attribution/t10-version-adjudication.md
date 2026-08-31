# T10 version disagreement

- User wording requests a version family, but the critical validator receives the model claim, not the original user wording.
- Raw model claim contains `v3` and `v2` values and does not itself contain an explicit family/series/wildcard scope marker.
- Frozen V3 parser classifies the claim specificity as `AMBIGUOUS_SPECIFICITY`; the captured support contains both v3 and v2.
- Baseline: `PASS / NO_CRITICAL_VALUE`.
- V3: `INDETERMINATE / CRITICAL_VALUE_INDETERMINATE`.
- Frozen-contract adjudication: V3 is **contract-correct**. Ambiguous exact-vs-family specificity must remain indeterminate; baseline is overly permissive.
- Disagreement classification: `BASELINE_UNSAFE_PERMISSIVENESS`, not `V3_AVAILABILITY_REGRESSION`.
- Canary significance: this is supportive safety evidence for V3, but shadow disagreement is not semantic ground truth and no canary decision is made here.
