# MMLongBench-Doc pilot

39 questions over 12 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 39 | 100% (38/38) | 100% (38/38) | 100% (38/38) | 47% (18/38) | 87% (26/30) |
| text | 17 | 100% (17/17) | 100% (17/17) | 100% (17/17) | 47% (8/17) | 100% (12/12) |
| layout | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 100% (2/2) | 100% (2/2) |
| table | 28 | 100% (28/28) | 100% (28/28) | 100% (28/28) | 46% (13/28) | 83% (19/23) |
| chart | 7 | 100% (7/7) | 100% (7/7) | 100% (7/7) | 14% (1/7) | 100% (4/4) |
| figure | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) |

- Unanswerable correctly refused: 100% (1/1)
- Answerable questions answered (coverage): 79% (30/38)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 47% (9/19); in the evidence the model saw: 47% (9/19)
- An evidence page among the pages the model was shown: 100% (38/38)
- Wrong answers by the stage that lost the gold answer: generation 2, not_in_page_text 7, unmeasured 11
- Response kinds: answered 30, model_abstained 5, validator_blocked 4
- Ingestion: existing chunks in 0 s; questions: median 8.4 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
