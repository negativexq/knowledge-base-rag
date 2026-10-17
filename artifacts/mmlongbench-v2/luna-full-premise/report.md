# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 100% (100/100) | 100% (100/100) | 100% (100/100) | 44% (44/100) | 81% (48/59) |
| text | 45 | 100% (45/45) | 100% (45/45) | 100% (45/45) | 53% (24/45) | 94% (30/32) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 36% (4/11) | 60% (3/5) |
| table | 55 | 100% (55/55) | 100% (55/55) | 100% (55/55) | 38% (21/55) | 70% (21/30) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 20% (2/10) | 83% (5/6) |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 12% (1/8) | 100% (1/1) |

- Unanswerable correctly refused: 80% (16/20)
- Answerable questions answered (coverage): 59% (59/100)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 71% (35/49)
- An evidence page among the pages the model was shown: 100% (100/100)
- Wrong answers by the stage that lost the gold answer: generation 11, not_in_page_text 11, unmeasured 34
- Response kinds: answered 63, model_abstained 50, validator_blocked 7
- Ingestion: existing chunks in 0 s; questions: median 8.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
