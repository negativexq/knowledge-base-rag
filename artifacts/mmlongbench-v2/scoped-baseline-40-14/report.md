# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `none`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 100% (100/100) | 100% (100/100) | 100% (100/100) | 0% (0/100) | – |
| text | 45 | 100% (45/45) | 100% (45/45) | 100% (45/45) | 0% (0/45) | – |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 0% (0/11) | – |
| table | 55 | 100% (55/55) | 100% (55/55) | 100% (55/55) | 0% (0/55) | – |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 0% (0/10) | – |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 0% (0/8) | – |

- Unanswerable correctly refused: 100% (20/20)
- Answerable questions answered (coverage): 0% (0/100)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 71% (35/49)
- An evidence page among the pages the model was shown: 100% (100/100)
- Wrong answers by the stage that lost the gold answer: generation 35, not_in_page_text 14, unmeasured 51
- Response kinds: model_abstained 120
- Ingestion: existing chunks in 0 s; questions: median 9.2 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
