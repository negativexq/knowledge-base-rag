# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 99% (98/99) | 98% (97/99) | 99% (98/99) | 54% (53/99) | 78% (49/63) |
| text | 45 | 100% (45/45) | 96% (43/45) | 98% (44/45) | 56% (25/45) | 83% (24/29) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 45% (5/11) | 50% (3/6) |
| table | 54 | 98% (53/54) | 100% (54/54) | 100% (54/54) | 57% (31/54) | 81% (29/36) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 20% (2/10) | 50% (1/2) |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 25% (2/8) | 50% (1/2) |

- Unanswerable correctly refused: 86% (18/21)
- Answerable questions answered (coverage): 64% (63/99)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 69% (34/49)
- An evidence page among the pages the model was shown: 98% (97/99)
- Wrong answers by the stage that lost the gold answer: generation 10, not_in_page_text 9, retrieval 2, unmeasured 25
- Response kinds: answered 66, model_abstained 40, validator_blocked 14
- Ingestion: existing chunks in 0 s; questions: median 9.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
