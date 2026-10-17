# MMLongBench-Doc pilot

120 questions over 13 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `gpt-6-luna`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@14 | Hit@40 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 120 | 100% (99/99) | 99% (98/99) | 100% (99/99) | 61% (60/99) | 79% (55/70) |
| text | 45 | 100% (45/45) | 98% (44/45) | 100% (45/45) | 64% (29/45) | 79% (26/33) |
| layout | 11 | 100% (11/11) | 100% (11/11) | 100% (11/11) | 27% (3/11) | 40% (2/5) |
| table | 54 | 100% (54/54) | 100% (54/54) | 100% (54/54) | 63% (34/54) | 84% (32/38) |
| chart | 10 | 100% (10/10) | 100% (10/10) | 100% (10/10) | 30% (3/10) | 75% (3/4) |
| figure | 8 | 100% (8/8) | 100% (8/8) | 100% (8/8) | 50% (4/8) | 25% (1/4) |

- Unanswerable correctly refused: 90% (19/21)
- Answerable questions answered (coverage): 71% (70/99)
- ACL leaks (same questions as `tenant-a`): 0
- Evidence given to the model: retrieved
- Retrieval scope: question_document
- Labels: data/benchmarks/mmlongbench-doc-v2/samples.json
- Gold answer in the evidence pages' text: 71% (35/49); in the evidence the model saw: 69% (34/49)
- An evidence page among the pages the model was shown: 99% (98/99)
- Wrong answers by the stage that lost the gold answer: generation 10, not_in_page_text 7, unmeasured 22
- Response kinds: answered 72, model_abstained 41, validator_blocked 7
- Ingestion: existing chunks in 0 s; questions: median 11.1 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score. Gold visibility uses the same match, so an answer that has to be computed counts as not in the text.
