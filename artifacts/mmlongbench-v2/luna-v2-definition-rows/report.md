# MMLongBench-Doc pilot

4 questions over 2 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 50% (2/4) | 100% (3/3) |
| text | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) |
| layout | 0 | – | – | – | – | – |
| table | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 33% (1/3) | 100% (2/2) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 75% (3/4)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: –; in the evidence the model saw: –
- An evidence page among the pages the model was shown: 100% (4/4)
- Wrong answers by the stage that lost the gold answer: unmeasured 2
- Response kinds: answered 3, model_abstained 1
- Ingestion: existing chunks in 0 s; questions: median 14.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
