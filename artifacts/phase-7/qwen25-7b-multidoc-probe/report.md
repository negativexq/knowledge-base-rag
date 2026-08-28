# Phase 7.8 qwen3.5:4b vs qwen2.5:7b-instruct

Decision: **QWEN25_7B_NO_MEANINGFUL_GAIN**

Arm A reused the Phase 7.5/7.7 Context Builder v1 result with qwen3.5:4b and
prompt v3. Arm B generated exactly the same three cached contexts with
qwen2.5:7b-instruct and prompt v3. No retrieval, reranking, embedding, or
Phase 6 call was made.

- Fully correct and complete: 4B `0/3`; 7B `0/3`.
- Fact coverage (ordered as multi-00-1, multi-00-3, multi-03-0): 4B `[0.5, 0.5, 0.0]`; 7B `[0.0, 0.5, 0.0]`.
- Obligation-planning failures: 4B `2/3`; 7B `2/3`.
- Evidence-synthesis failures: 4B `1/3`; 7B `1/3`.
- Validator: 4B `2 pass / 1 reject`; 7B `2 pass / 1 reject`.
- Raw B candidates observable: `3/3`.
- Generation latency p50/max: 4B `22332.363/42810.946` ms; 7B `19560.407/25990.566` ms.
- Context IDs/order identical: `True`. Runtime default remains qwen3.5:4b.
