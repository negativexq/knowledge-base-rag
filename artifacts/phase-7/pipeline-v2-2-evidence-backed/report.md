# Pipeline v2.2 Evidence-Backed Claims & Deterministic Abstention

Identity verified for `63dbd8ed89a35c31f0968bc1ce93770fb8954602`. Historical replay was offline and found 36 records without quote fields.

The focused gate used 9 new qwen3.5:4b calls, zero retrieval calls, and zero reranker/embedding/semantic calls. ACL unsupported visible answers: 0/3; unauthorized leakage: 0; multi-document raw full: 1/3. Decision: **PIPELINE_V2_2_GATE_FAIL_MIXED**.

The 36-query smoke and development-200 were not run because the focused gate did not pass. Runtime default remains `RAG_PIPELINE_V2=false`.
