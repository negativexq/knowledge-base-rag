# MMLongBench-Doc pilot

10 questions over 10 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 10 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 25% (2/8) | 100% (2/2) |
| text | 5 | 100% (5/5) | 100% (5/5) | 100% (5/5) | 20% (1/5) | 100% (1/1) |
| layout | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 50% (1/2) | 100% (1/1) |
| table | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | – |
| chart | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |
| figure | 1 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | – |

- Unanswerable correctly refused: 50% (1/2)
- Answerable questions answered (coverage): 25% (2/8)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 50% (1/2); in the evidence the model saw: 50% (1/2)
- An evidence page among the pages the model was shown: 100% (8/8)
- Wrong answers by the stage that lost the gold answer: not_in_page_text 1, unmeasured 5
- Response kinds: answered 3, model_abstained 2, validator_blocked 5
- Ingestion: existing chunks in 0 s; questions: median 28.5 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
