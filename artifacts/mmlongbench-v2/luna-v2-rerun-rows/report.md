# MMLongBench-Doc pilot

23 questions over 9 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 23 | 100% (22/22) | 100% (22/22) | 100% (22/22) | 36% (8/22) | 90% (9/10) |
| text | 6 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 50% (3/6) | 100% (4/4) |
| layout | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | – |
| table | 15 | 100% (15/15) | 100% (15/15) | 100% (15/15) | 40% (6/15) | 86% (6/7) |
| chart | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | – |
| figure | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 100% (1/1) |

- Unanswerable correctly refused: 100% (1/1)
- Answerable questions answered (coverage): 45% (10/22)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 50% (6/12); in the evidence the model saw: 50% (6/12)
- An evidence page among the pages the model was shown: 100% (22/22)
- Wrong answers by the stage that lost the gold answer: generation 4, not_in_page_text 2, unmeasured 8
- Response kinds: answered 10, model_abstained 11, validator_blocked 2
- Ingestion: existing chunks in 0 s; questions: median 12.0 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
