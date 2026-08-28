# Phase 7.4 Context Builder v1 Probe

Decision: **CONTEXT_BUILDER_GAIN_MODEST**

This is a controlled 12-query probe. Arm A reused the historical qwen3.5:4b
outputs and Arm B ran the same model, prompt `v3`, think=false, and
strict validation after deterministic Context Builder v1 presentation. The
authorized Top-5 set was reused unchanged; no retrieval or semantic gate ran.

- A full correct/complete: `3/12`
- B full correct/complete: `7/12`
- Multi-document full: A `0/3`, B `0/3`
- Validator failures: A `3`, B `1`
- Citation-alignment proxy failures: A `9`, B `0`
- Context tokens p50: A `527`, B `521`
- Generation p95: A `56579.07` ms, B `38091.582` ms
- Evidence lost: `False`; Top-5 expanded: `False`

The probe does not promote B to the runtime default and does not claim a
production-quality result from twelve records.
