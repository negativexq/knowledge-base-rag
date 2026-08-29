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

## Current engineering position

Retrieval is strong, ACL and provenance boundaries are deterministic, and
SectionAware budget pressure is graceful. The planned citation contract is
`text + support_ids[]`: the model selects IDs from the current visible
evidence, and the application resolves canonical citation text. A valid ID
proves provenance and authorization, not semantic entailment. The support-ID
contract is not yet broadly validated on Basic-50.
