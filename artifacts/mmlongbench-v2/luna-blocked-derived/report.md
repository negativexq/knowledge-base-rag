# MMLongBench-Doc pilot

39 questions over 12 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 39 | 100% (38/38) | 100% (38/38) | 100% (38/38) | 34% (13/38) | 79% (15/19) |
| text | 17 | 100% (17/17) | 100% (17/17) | 100% (17/17) | 29% (5/17) | 89% (8/9) |
| layout | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | – |
| table | 28 | 100% (28/28) | 100% (28/28) | 100% (28/28) | 36% (10/28) | 71% (10/14) |
| chart | 7 | 100% (7/7) | 100% (7/7) | 100% (7/7) | 29% (2/7) | 80% (4/5) |
| figure | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |

- Unanswerable correctly refused: 100% (1/1)
- Answerable questions answered (coverage): 50% (19/38)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 47% (9/19); in the evidence the model saw: 47% (9/19)
- An evidence page among the pages the model was shown: 100% (38/38)
- Wrong answers by the stage that lost the gold answer: generation 3, not_in_page_text 8, unmeasured 14
- Response kinds: answered 19, model_abstained 7, validator_blocked 13
- Ingestion: existing chunks in 0 s; questions: median 8.2 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
