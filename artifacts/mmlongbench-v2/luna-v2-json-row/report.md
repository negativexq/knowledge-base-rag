# MMLongBench-Doc pilot

1 questions over 1 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) |
| text | 0 | – | – | – | – | – |
| layout | 0 | – | – | – | – | – |
| table | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) | 100% (1/1) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 100% (1/1)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: –; in the evidence the model saw: –
- An evidence page among the pages the model was shown: 100% (1/1)
- Wrong answers by the stage that lost the gold answer: none
- Response kinds: answered 1
- Ingestion: existing chunks in 0 s; questions: median 33.5 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
