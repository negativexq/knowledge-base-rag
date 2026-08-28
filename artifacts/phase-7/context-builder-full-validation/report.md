# Phase 7.5 Context Builder Full Validation

Status: **CONTEXT_BUILDER_GAIN_MODEST_MORE_WORK_NEEDED**

The exact 36-query retrieval cache was reused. Arm A was historical and made
zero generation calls; Arm B used qwen3.5:4b, prompt v3, think=false and
Context Builder v1. Retrieval, reranking, embedding and Phase 6 evaluators
were not invoked.

- Gold-present answerable: `22`; A full: `10/22`; B full: `13/22`
- Multi-document full: A `0/3`; B `0/3`
- Validator rejects: A `7`; B `8`
- Evidence lost: `False`; membership expanded: `False`
- Context token p50/p95: A `528/621`, B `521/611`
- Generation p95: A `49987.912` ms; B `40207.7` ms

The evidence set remained fixed. B improved the measured content class on the
full smoke, but the complete multi-document slice remains unresolved and
citation support still requires manual review. Context Builder v1 is not
promoted by this experiment.
