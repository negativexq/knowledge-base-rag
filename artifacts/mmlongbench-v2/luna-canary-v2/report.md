# MMLongBench-Doc pilot

21 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 21 | 100% (5/5) | 100% (5/5) | 100% (5/5) | 100% (5/5) | 100% (5/5) |
| text | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 100% (4/4) | 100% (4/4) |
| layout | 0 | – | – | – | – | – |
| table | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 100% (2/2) | 100% (2/2) |
| chart | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: 69% (11/16)
- Answerable questions answered (coverage): 100% (5/5)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 50% (2/4); in the evidence the model saw: 50% (2/4)
- An evidence page among the pages the model was shown: 100% (5/5)
- Wrong answers by the stage that lost the gold answer: none
- Response kinds: answered 10, model_abstained 8, validator_blocked 3
- Ingestion: existing chunks in 0 s; questions: median 10.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
