# Phase 7.10 — Structure-aware chunking and fact evidence

The previous source-level proxy overstated evidence availability. Both `multi-00-1` and `multi-00-3` had the required Standard source in Top-5, but only its Case record chunk; the root chunk containing `14 calendar days` was absent.

Fact passage recall is 100.0% at candidate Top-20 and 71.4% at Top-5. All required facts are present for 3/3 queries at Top-20 and 1/3 at Top-5.

The offline representation winner is `SECTION_AWARE_MERGED`. It recovers compact same-source sections without generated text and with lower cost than full-parent expansion. This is diagnostic, not promoted.

Primary attribution is reranker/Top-5 selection: the supporting Standard root chunk is in candidate Top-20 but omitted from final Top-5. The literal authored span is fully contained in a current chunk, so this is not a span-splitting failure.

Generation probe: RUN.
