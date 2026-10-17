# MMLongBench-Doc pilot

7 questions over 4 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 7 | 100% (7/7) | 100% (7/7) | 100% (7/7) | 14% (1/7) | 0% (0/2) |
| text | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 33% (1/3) | 0% (0/2) |
| layout | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 0% (0/4) | 0% (0/1) |
| table | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |
| chart | 0 | – | – | – | – | – |
| figure | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 25% (1/4) | 0% (0/1) |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 29% (2/7)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 100% (2/2); in the evidence the model saw: 100% (2/2)
- An evidence page among the pages the model was shown: 100% (7/7)
- Wrong answers by the stage that lost the gold answer: generation 2, unmeasured 4
- Response kinds: answered 2, model_abstained 5
- Ingestion: existing chunks in 0 s; questions: median 15.3 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
