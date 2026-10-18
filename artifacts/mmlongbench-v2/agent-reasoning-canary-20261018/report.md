# MMLongBench-Doc pilot

10 questions over 6 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 10 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 0% (0/3) | 0% (0/1) |
| text | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | 0% (0/1) |
| layout | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | 0% (0/1) |
| table | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |
| chart | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: 86% (6/7)
- Answerable questions answered (coverage): 33% (1/3)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: –; in the evidence the model saw: –
- An evidence page among the pages the model was shown: 100% (3/3)
- Wrong answers by the stage that lost the gold answer: unmeasured 3
- Response kinds: answered 2, model_abstained 5, validator_blocked 3
- Ingestion: existing chunks in 0 s; questions: median 21.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
