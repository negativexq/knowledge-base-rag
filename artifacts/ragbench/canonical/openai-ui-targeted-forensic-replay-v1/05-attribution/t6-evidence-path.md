# T6 evidence path

- Corpus/source: supported by `nimbus_api_reference.md#Authentication`.
- RRF Top20: PRESENT (API Authentication chunk is rank 1).
- BGE Top5: PRESENT (same chunk is rank 1).
- Final evidence: PRESENT; it contains `60 minutes`.
- EvidenceBuildResult: 2 blocks, no truncation, no budget exhaustion, no dropped expansion.
- Raw model: `60 minutes—that is, 1 hour`, substantively correct.
- Baseline and V3: `INDETERMINATE / CRITICAL_VALUE_INDETERMINATE`; the 60-minute token has direct support, while the generated `1 hour` representation has no matching hour-form support and no unit conversion in the frozen contract.
- Forced abstain: caused by critical-validator indeterminate result; support ID `E1.S1` was rejected downstream.

First failure stage: **validator unit-equivalence/representation comparison**, not retrieval, reranking, or evidence build. Primary attribution: `UNIT_EQUIVALENCE_GAP`; secondary: `CRITICAL_VALUE_NORMALIZATION_GAP`.
