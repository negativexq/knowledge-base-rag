# MMLongBench-Doc pilot

27 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 27 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 70% (7/10) | 86% (6/7) |
| text | 7 | 100% (7/7) | 100% (7/7) | 100% (7/7) | 71% (5/7) | 80% (4/5) |
| layout | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 100% (1/1) |
| table | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 67% (2/3) | 100% (2/2) |
| chart | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 100% (1/1) |
| figure | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) |

- Unanswerable correctly refused: 76% (13/17)
- Answerable questions answered (coverage): 70% (7/10)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 50% (2/4); in the evidence the model saw: 50% (2/4)
- An evidence page among the pages the model was shown: 100% (10/10)
- Wrong answers by the stage that lost the gold answer: unmeasured 3
- Response kinds: answered 11, model_abstained 12, validator_blocked 4
- Ingestion: existing chunks in 0 s; questions: median 15.9 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
