# RAG research history

This log keeps the conclusions of the Phase 7–12 and RAGBench work without
keeping every exploratory checkpoint in the product repository.

| Work | Result | Decision |
| --- | --- | --- |
| Phase 7 | `pipeline_v2_2_evidence_backed` selected; local Qwen remains the historical baseline. | Preserve retrieval, ACL, reranking, and deterministic validation. |
| Phase 8 | Luna was materially stronger than local Qwen, but literal generated quotes were brittle. | Keep Luna as the planned generator; do not treat old quote text as canonical provenance. |
| Phase 9 | Global semantic verification improved safety but reduced quality (`95/150` to `75/150`) and introduced false abstentions. Ambiguity controls did not generalize. | Do not use a global post-generation semantic gate or ambiguity preflight. |
| Phase 10 | RAGBench evidence was strong at Top20; losses were concentrated in Top5/assembly and generation. | Keep retrieval unchanged and preserve retrieval-stage observability. |
| Phase 11 | Evidence planning selected facts but recovered only `4/21`. | Do not add a planner→synthesis runtime stage. |
| Phase 12 | Luna `none → medium` recovered `0/16`. | Do not add reasoning routing based on this experiment. |
| RAGBench Basic-50 | Graceful SectionAware budget changed assembly failures `31 → 0`, grounded visible answers `9 → 40`, and abstentions `41 → 10`. | Keep anchor-preserving graceful budget behavior. |
| Quote audit | Conservative quote normalization recovered `0/4`. | Retire literal generated quotes as the primary contract. |
| Sentence-ID feasibility/challenger | Exact request-scoped IDs were feasible `4/4`; challenger produced valid IDs `4/4` and semantic recovery `3/4`. | Keep support IDs as a small-scale validated direction; broader confirmation remains pending. |
| Completeness diagnostic | Minimal completeness instruction recovered `1/4`. | Do not add it globally. |
| Canonical Basic-50 confirmation | Frozen retrieval stayed strong (`100%` Hybrid Top20 mean relevant recall; `96.24%` BGE Top5; `89.72%` SectionAware), but the support-ID path yielded `24` correct, `7` partial, `2` incorrect, `15` validator-induced no-valid outputs, and `2` parse failures. | Do not promote support IDs globally or move to TechQA until output/validation robustness is fixed. |
| Claim-local validator integration | Frozen replay recovered `6/6` confirmed critical-value false positives, kept `0/4` indeterminate cases auto-passed, and changed visibility `33 → 38` with no visible or support-ID security regressions. | Adopt claim-local critical-value consistency in the canonical validator; semantic status for the five newly visible outputs remains pending judge-only review. |
| Newly visible semantic judging | Five exact post-fix outputs were judged without new Luna calls: `1` correct, `4` partial, `0` incorrect. Final frozen post-fix record is `25` correct, `11` partial, `2` incorrect, and `12` unavailable. | Claim-local validation recovered semantically useful availability; retain the support-ID direction and carry the remaining broader-contract risk into the next benchmark. |
| TechQA Phase -1 / Phase 0 | The original TechQA sample is now `DEBUG50`; a disjoint identity-only `HOLDOUT50` was frozen with seed `4242` before further fixes. Artifact-only analysis found native strict JSON Schema already enabled, `11/11` structured failures as `abstain=true` plus non-empty parts, `17` critical-value-affected rows, and `10` BGE-all to SectionAware-not-all rows. | Keep the holdout untouched; treat the primary structured-output issue as answer/abstain state-machine encoding debt and investigate SectionAware anchor feasibility separately. |
| TechQA output-state schema challenger | A provider-compatible nested strict-schema union removed all `11/11` application state conflicts (`7` answer states, `4` abstentions), but only `1/6` newly visible answers was semantically useful; five encoded a not-found response as an answer with structurally valid yet unhelpful citations. | Do not adopt the schema-only fix. Redesign the answerability state contract before evidence experiments or holdout use. |
| TechQA answerability/relevance V4 | A native strict discriminated `ANSWER`/`ABSTAIN` contract plus a preregistered `0.60` exact content-token support gate produced `11/11` valid states, `10` self-abstentions, and `1` visible answer. The gate suppressed one unsupported part without a blocklist; the sole visible answer was judged incorrect. | Keep the security/provenance behavior, but do not promote this combined challenger. The model still needs an answerability contract that distinguishes supported negative answers from unsupported search-failure text; holdout remains untouched. |

## Current engineering position

Retrieval is strong, ACL and provenance boundaries are deterministic, and
SectionAware budget pressure is graceful. The planned citation contract is
`text + support_ids[]`: the model selects IDs from the current visible
evidence, and the application resolves canonical citation text. A valid ID
proves provenance and authorization, not semantic entailment. The support-ID
contract is not yet broadly validated on Basic-50: the full canonical
confirmation did not meet the stability gate despite strong retrieval and
zero accepted unauthorized/hidden/cross-request IDs. The subsequent claim-local
critical-value replay plus targeted judging of five newly visible outputs found
all five semantically useful (one correct, four partial) with no safety
regression. This targeted result is not a regenerated full benchmark, and the
remaining parser/support-selection debt should be addressed before claiming
production-wide semantic guarantees.

| TechQA Basic-50 cross-dataset confirmation | The unchanged canonical run completed `50/50` Luna calls, but TechQA retrieval/evidence dropped to Hybrid Top20 `96.71%`, BGE Top5 `88.28%`, and SectionAware `77.98%` mean relevant-sentence recall. Only `24/50` answers were visible and `14/50` passed all support-ID/claim-local validation; semantic output was `13` correct, `9` partial, and `2` incorrect. | Do not call the architecture cross-dataset stable yet; target TechQA evidence assembly and structured-output availability before expanding benchmark coverage. |
