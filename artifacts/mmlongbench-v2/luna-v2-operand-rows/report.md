# MMLongBench-Doc pilot

2 questions over 1 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | 100% (1/1) |
| text | 0 | – | – | – | – | – |
| layout | 0 | – | – | – | – | – |
| table | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | 100% (1/1) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 50% (1/2)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 0% (0/1); in the evidence the model saw: 0% (0/1)
- An evidence page among the pages the model was shown: 100% (2/2)
- Wrong answers by the stage that lost the gold answer: not_in_page_text 1, unmeasured 1
- Response kinds: answered 1, model_abstained 1
- Ingestion: existing chunks in 0 s; questions: median 32.0 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
