# MMLongBench-Doc pilot

11 questions over 4 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 0% (0/11) | 100% (2/2) |
| text | 0 | – | – | – | – | – |
| layout | 0 | – | – | – | – | – |
| table | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 0% (0/11) | 100% (2/2) |
| chart | 0 | – | – | – | – | – |
| figure | 0 | – | – | – | – | – |

- Unanswerable correctly refused: –
- Answerable questions answered (coverage): 18% (2/11)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Gold answer in the evidence pages' text: 0% (0/2); in the evidence the model saw: 0% (0/2)
- An evidence page among the pages the model was shown: 100% (11/11)
- Wrong answers by the stage that lost the gold answer: not_in_page_text 2, unmeasured 9
- Response kinds: answered 2, model_abstained 9
- Ingestion: existing chunks in 0 s; questions: median 22.2 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
