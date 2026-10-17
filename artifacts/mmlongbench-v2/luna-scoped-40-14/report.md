# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 100% (100/100) | 100% (100/100) | 100% (100/100) | 23% (23/100) | 82% (28/34) |
| text | 45 | 100% (45/45) | 100% (45/45) | 100% (45/45) | 33% (15/45) | 95% (21/22) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 18% (2/11) | 50% (2/4) |
| table | 55 | 100% (55/55) | 100% (55/55) | 100% (55/55) | 13% (7/55) | 70% (7/10) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 0% (0/10) | 100% (1/1) |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 0% (0/8) | 0% (0/1) |

- Unanswerable correctly refused: 80% (16/20)
- Answerable questions answered (coverage): 34% (34/100)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 71% (35/49)
- An evidence page among the pages the model was shown: 100% (100/100)
- Wrong answers by the stage that lost the gold answer: generation 19, not_in_page_text 14, unmeasured 44
- Response kinds: answered 38, model_abstained 43, validator_blocked 39
- Ingestion: existing chunks in 0 s; questions: median 9.9 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
