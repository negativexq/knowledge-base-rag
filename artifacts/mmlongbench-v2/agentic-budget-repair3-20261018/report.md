# MMLongBench-Doc pilot

3 questions over 3 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 33% (1/3) | 100% (1/1) |
| text | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |
| layout | 0 | – | – | – | – | – |
| table | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 100% (1/1) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 33% (1/3)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 50% (1/2); in the evidence the model saw: 50% (1/2)
- An evidence page among the pages the model was shown: 100% (3/3)
- Wrong answers by the stage that lost the gold answer: generation 1, unmeasured 1
- Response kinds: answered 1, validator_blocked 2
- Ingestion: existing chunks in 0 s; questions: median 37.0 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
