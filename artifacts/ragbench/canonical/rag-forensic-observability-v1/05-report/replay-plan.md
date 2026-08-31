# Targeted forensic replay plan

This plan is prepared only; no adversarial replay is performed in this task.

Targets: T3, T4, T5, T6, T10.

1. Use the frozen questions and the same local corpus/provider configuration
   where available.
2. Enable `RAG_FORENSIC_CAPTURE_ENABLED=true` and, only for controlled local
   fixtures, `RAG_FORENSIC_CAPTURE_RAW_TEXT=true`.
3. Preserve `CRITICAL_VALIDATOR_VERSION=baseline` and
   `CRITICAL_VALIDATOR_V3_SHADOW_ENABLED=true`; V3 remains diagnostic only.
4. Capture one record per request before reviewing results.
5. Do not add, remove, or edit cases after observing output. Do not tune any
   layer between replays.
6. Review retrieval Top20, BGE Top5, EvidenceBuildResult, raw structured model
   result, support-ID decisions, validator occurrences, citation resolution,
   and visible response in that order.

Raw records must remain local, task-owned, and synthetic/safe where possible.
They must not be exported to OTel or committed if local policy forbids raw
evidence artifacts.
