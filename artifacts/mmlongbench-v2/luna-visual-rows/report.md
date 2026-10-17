# MMLongBench-Doc pilot

17 questions over 8 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 17 | 93% (13/14) | 93% (13/14) | 93% (13/14) | 7% (1/14) | 50% (2/4) |
| text | 6 | 83% (5/6) | 83% (5/6) | 83% (5/6) | 17% (1/6) | 0% (0/1) |
| layout | 5 | 100% (5/5) | 100% (5/5) | 100% (5/5) | 0% (0/5) | 0% (0/1) |
| table | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 0% (0/4) | 100% (2/2) |
| chart | 0 | – | – | – | – | – |
| figure | 7 | 86% (6/7) | 86% (6/7) | 86% (6/7) | 0% (0/7) | 0% (0/1) |

- Unanswerable correctly refused: 100% (3/3)
- Answerable questions answered (coverage): 29% (4/14)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 100% (4/4); in the evidence the model saw: 100% (4/4)
- An evidence page among the pages the model was shown: 93% (13/14)
- Wrong answers by the stage that lost the gold answer: generation 4, not_in_page_text 1, unmeasured 8
- Response kinds: answered 4, model_abstained 10, validator_blocked 3
- Ingestion: existing chunks in 0 s; questions: median 13.9 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
