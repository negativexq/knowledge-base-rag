# MMLongBench-Doc pilot

20 questions over 5 PDFs (dataset revision `2ff6aa92`), production path, tenant `bench-mmlongbench`, model `qwen3.5:4b`. Rates are over answerable questions; a question with several evidence types counts in each.

| Slice | Questions | Ingestion | Hit@5 | Hit@15 | Answer | Citation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 20 | 100% (15/15) | 53% (8/15) | 80% (12/15) | 20% (3/15) | 22% (2/9) |
| text | 8 | 100% (8/8) | 62% (5/8) | 100% (8/8) | 12% (1/8) | 25% (1/4) |
| layout | 3 | 100% (3/3) | 33% (1/3) | 67% (2/3) | 0% (0/3) | 0% (0/2) |
| table | 5 | 100% (5/5) | 80% (4/5) | 100% (5/5) | 20% (1/5) | 67% (2/3) |
| chart | 3 | 100% (3/3) | 33% (1/3) | 67% (2/3) | 0% (0/3) | 0% (0/1) |
| figure | 4 | 100% (4/4) | 75% (3/4) | 100% (4/4) | 25% (1/4) | 0% (0/3) |

- Unanswerable correctly refused: 40% (2/5)
- Answerable questions answered (coverage): 60% (9/15)
- ACL leaks (same questions as `tenant-a`): 0
- Ingestion: 144 chunks in 583.4 s; questions: median 37.8 s each.

Answer accuracy is a lenient, deterministic contains-match (numbers within 1%), not the benchmark's official LLM-extracted score.
