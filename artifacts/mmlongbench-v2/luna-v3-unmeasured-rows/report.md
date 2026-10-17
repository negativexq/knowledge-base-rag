# MMLongBench-Doc pilot

4 questions over 3 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 4 | 100% (4/4) | 100% (4/4) | 100% (4/4) | 0% (0/4) | 100% (1/1) |
| text | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | 100% (1/1) |
| layout | 0 | – | – | – | – | – |
| table | 3 | 100% (3/3) | 100% (3/3) | 100% (3/3) | 0% (0/3) | – |
| chart | 2 | 100% (2/2) | 100% (2/2) | 100% (2/2) | 0% (0/2) | 100% (1/1) |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 25% (1/4)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 0% (0/3); in the evidence the model saw: 0% (0/3)
- An evidence page among the pages the model was shown: 100% (4/4)
- Wrong answers by the stage that lost the gold answer: not_in_page_text 3, unmeasured 1
- Response kinds: answered 1, model_abstained 1, validator_blocked 2
- Ingestion: existing chunks in 0 s; questions: median 18.7 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
