# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 100% (100/100) | 100% (100/100) | 100% (100/100) | 47% (47/100) | 86% (54/63) |
| text | 45 | 100% (45/45) | 100% (45/45) | 100% (45/45) | 53% (24/45) | 97% (31/32) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 36% (4/11) | 60% (3/5) |
| table | 55 | 100% (55/55) | 100% (55/55) | 100% (55/55) | 44% (24/55) | 82% (27/33) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 10% (1/10) | 100% (5/5) |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 12% (1/8) | 50% (1/2) |

- Unanswerable correctly refused: 85% (17/20)
- Answerable questions answered (coverage): 63% (63/100)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 71% (35/49)
- An evidence page among the pages the model was shown: 100% (100/100)
- Wrong answers by the stage that lost the gold answer: generation 10, not_in_page_text 11, unmeasured 32
- Response kinds: answered 66, model_abstained 46, validator_blocked 8
- Ingestion: existing chunks in 0 s; questions: median 9.1 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
