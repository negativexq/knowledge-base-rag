# Evaluation Corpus v2 manual sample review

This is a static, stratified review of 36 records (four from each category)
after corpus generation. The review is intentionally text-only; no model,
retriever, reranker, judge, or generation call was used.

Reviewed categories:

- `acl_negative`: `acl-00-0`, `acl-00-1`, `acl-00-2`, `acl-00-3`
- `ambiguous`: `ambiguous-00-0`, `ambiguous-00-1`, `ambiguous-00-2`, `ambiguous-01-0`
- `cross_lingual`: `cross-00-0`, `cross-00-1`, `cross-01-0`, `cross-01-1`
- `hard_answerable`: `hard-activation-evidence`, `hard-allowlist-api`, `hard-annual-cancel`, `hard-api-private`
- `injection_bearing`: `injection-00-0`, `injection-00-1`, `injection-00-2`, `injection-00-3`
- `multi_document`: `multi-00-0`, `multi-00-1`, `multi-00-2`, `multi-00-3`
- `standard_answerable`: `native-00-0`, `native-00-1`, `native-00-2`, `native-00-3`
- `unanswerable`: `negative-00-0`, `negative-00-1`, `negative-00-2`, `negative-00-3`
- `version_conflict`: `version-00-0`, `version-00-1`, `version-00-2`, `version-00-3`

## Review findings

- Answerable records point to a source that contains the stated business
  fact; multi-document records require both listed source identities.
- Standard, premium, marketplace, digital activation, regional, and
  enterprise terms are intentionally close but remain resolvable by plan,
  channel, tenant, region, or contract authority.
- Cross-language samples use Turkish queries against English evidence and
  preserve the explicit `tr->en`/`en->tr` metadata.
- Unanswerable samples have no expected evidence and retain nearby documents
  as distractors. ACL samples point only to tenant-b facts while the caller is
  tenant-a.
- Version samples distinguish the effective delivery date from the newer
  document and retain the superseding source as a distractor.
- Injection samples contain real refund evidence alongside controlled
  adversarial text; the expected answer follows business evidence and not the
  document instruction.
- The sampled wording includes direct, operator, customer-scenario,
  comparison, temporal, and policy-review forms. The generated set is still a
  synthetic fixture and semantic paraphrase leakage should be checked again
  during the next benchmark review.

No sampled record was removed or relabeled during this review. The validator
remains the authority for IDs, paths, tenant boundaries, split values,
answerability/evidence consistency, and fingerprints.
