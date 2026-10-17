# MMLongBench-Doc pilot

8 questions over 2 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 50% (4/8) | 100% (4/4) |
| text | 0 | – | – | – | – | – |
| layout | 0 | – | – | – | – | – |
| table | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 50% (4/8) | 100% (4/4) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 50% (4/8)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 0% (0/2); in the evidence the model saw: 0% (0/2)
- An evidence page among the pages the model was shown: 100% (8/8)
- Wrong answers by the stage that lost the gold answer: unmeasured 4
- Response kinds: answered 4, model_abstained 4
- Ingestion: existing chunks in 0 s; questions: median 18.5 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
