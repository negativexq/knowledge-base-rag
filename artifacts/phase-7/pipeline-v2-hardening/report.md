# Pipeline v2 Citation & Grounded-Abstention Hardening

Identity verified for `63dbd8ed89a35c31f0968bc1ce93770fb8954602`. Historical validator replay reviewed 16 rejected records with zero inference. Evidence IDs use response-local `E1..En` values and server-side provenance.

Focused probe used 9 new qwen3.5:4b calls, zero retrieval calls, and zero reranker/embedding/semantic calls. ACL unsupported answers: 3/3; ACL unauthorized leakage: 0; multi-document raw complete: 1/3; focused decision: **PIPELINE_V2_HARDENING_FAIL_GROUNDING**.

The 36-query hardened smoke was not run because the focused gate did not pass. Development-200, calibration, and frozen test were not run. Runtime default remains `RAG_PIPELINE_V2=false`.
