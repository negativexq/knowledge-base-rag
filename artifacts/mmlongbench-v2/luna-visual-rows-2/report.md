# MMLongBench-Doc pilot

5 questions over 5 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 5 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 50% (2/4) | 0% (0/3) |
| text | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 67% (2/3) | 0% (0/2) |
| layout | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | 0% (0/1) |
| table | 0 | – | – | – | – | – |
| chart | 0 | – | – | – | – | – |
| figure | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 0% (0/1) |

- Unanswerable correctly refused: 100% (1/1)
- Answerable questions answered (coverage): 75% (3/4)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 100% (2/2); in the evidence the model saw: 100% (2/2)
- An evidence page among the pages the model was shown: 100% (4/4)
- Wrong answers by the stage that lost the gold answer: generation 1, unmeasured 1
- Response kinds: answered 3, model_abstained 2
- Ingestion: existing chunks in 0 s; questions: median 16.1 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
