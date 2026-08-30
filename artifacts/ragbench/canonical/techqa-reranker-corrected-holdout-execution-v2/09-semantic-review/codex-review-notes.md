# Codex blind semantic review

reviewer_type: CODEX_BLIND
review_mode: BLINDED_SEMANTIC_REVIEW
population: corrected HOLDOUT50 blind pack, 50 queries

The review used only the corrected blind `manual-review.md`, frozen
`review-rubric.md`, and the original blank `blind-scorecard.csv`. Candidate
A and Candidate B were scored independently against the supplied reference
answer before assigning pair preference. No arm identity was consulted or
inferred.

## LOW_CONFIDENCE_QUERY_IDS

- Q252 — both candidates contain relevant stale-connection remedies, but the
  reference's specific Validate on Reserve and Oracle setting are absent.
- Q157 — the reference is procedural while both visible answers are mainly
  troubleshooting/reference guidance.
- Q300 — both visible answers omit the direct answer while their supporting
  material addresses related DB2 storage behavior.
- Q308 — the distinction between a complete resource-search answer and a
  useful but generic support-portal answer is borderline.
- Q283 — both candidates provide licensing guidance, but the reference asks
  specifically for vendor contact routes.

## CONSISTENCY_PASS_CHANGES

NONE. The second blinded pass checked the CORRECT/PARTIAL boundary for
multi-part answers, numeric/version mismatches, abstention handling, and
pair preference ordering. No score was changed to balance Candidate A/B
counts.

## SUPPRESSION_DIAGNOSTIC

These are arm-neutral review notes only and are not semantic classes or
arm-level results. Visible abstentions were kept as UNAVAILABLE even when a
raw answer shown in the blind pack appeared useful.

- SUPPRESSION_JUSTIFIED: NONE assigned globally; no automatic determination.
- SUPPRESSION_OVERBLOCK: not used as a primary label; potentially relevant
  rows are noted locally in the scorecard where useful.
- SUPPRESSION_INDETERMINATE: rows with visible abstention and no usable
  visible answer remain UNAVAILABLE.

## BLINDING AND SCOPE

The corrected arm map was not read. ON/OFF identities remain unknown. No
new retrieval, embedding, reranking, generation, provider, judge, or
HOLDOUT experiment execution was performed in this review task. The only
HOLDOUT material read was the explicitly authorized persisted blind review
pack. The original blank scorecard was preserved.
