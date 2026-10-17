# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 91% (91/100) | 89% (89/100) | 90% (90/100) | 45% (45/100) | 78% (47/60) |
| text | 45 | 91% (41/45) | 87% (39/45) | 89% (40/45) | 47% (21/45) | 81% (21/26) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 45% (5/11) | 50% (3/6) |
| table | 55 | 89% (49/55) | 89% (49/55) | 89% (49/55) | 45% (25/55) | 83% (29/35) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 20% (2/10) | 50% (1/2) |
| figure | 8 | 75% (6/8) | 75% (6/8) | 75% (6/8) | 12% (1/8) | 0% (0/1) |

- Unanswerable correctly refused: 85% (17/20)
- Answerable questions answered (coverage): 60% (60/100)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 65% (32/49); in the evidence the model saw: 63% (31/49)
- An evidence page among the pages the model was shown: 89% (89/100)
- Wrong answers by the stage that lost the gold answer: generation 9, not_in_page_text 19, retrieval 2, unmeasured 25
- Response kinds: answered 63, model_abstained 44, validator_blocked 13
- Ingestion: existing chunks in 0 s; questions: median 9.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
