# MMLongBench-Doc pilot

17 questions over 4 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 17 | 100% (16/16) | 100% (16/16) | 100% (16/16) | 25% (4/16) | 100% (4/4) |
| text | 0 | – | – | – | – | – |
| layout | 0 | – | – | – | – | – |
| table | 16 | 100% (16/16) | 100% (16/16) | 100% (16/16) | 25% (4/16) | 100% (4/4) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: 100% (1/1)
- Answerable questions answered (coverage): 25% (4/16)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 25% (1/4); in the evidence the model saw: 25% (1/4)
- An evidence page among the pages the model was shown: 100% (16/16)
- Wrong answers by the stage that lost the gold answer: generation 1, not_in_page_text 2, unmeasured 9
- Response kinds: answered 4, model_abstained 13
- Ingestion: existing chunks in 0 s; questions: median 13.8 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
