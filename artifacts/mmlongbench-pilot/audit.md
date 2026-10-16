# MMLongBench-Doc pilot — audit

The first pilot report (PR #21) misread several failures. This audit went
through each question by hand: the model's raw output, the evidence pages,
and which chunks were retrieved. `report.md` is now re-scored from the saved
`results.jsonl` with the fixed harness (`--from-results`).

## Harness fixes

- Inline support markers (`[E1.S2]`) were matched as numbers. They are now
  stripped before answer matching.
- A malformed model output (`*_INVALID` validator codes) counted as a correct
  refusal. Each result now has a response kind: `answered`,
  `model_abstained`, `validator_blocked`, `output_invalid` or `no_verdict`.
  Only the first two refusal kinds count as correct refusals.
- The report is rebuilt from the saved results with the same scoring code,
  so a re-score never asks the model again.

## Corrections to the PR #21 note

| Claim | What the audit found |
| --- | --- |
| The validator rejected 4 correct answers | 3 of the 4 blocks were wrong answers: 219 computed 73%, 221 said "5.0", 639 answered with hop counts. Only 383 is a false reject: support units are split by line, so "Produced by:" and its value end up in separate units. |
| The reranker dropped evidence 4 times | 1–2 real drops (636). 218 is an off-by-one label (41% is on page 6). The data for 221 is in the page 16–17 tables, and those were retrieved. 364's candidate page holds only the header. |
| Ingestion is slow because of OCR | The slowness is embedding throughput: qwen3-embedding:4b at about 3.1 s per chunk. |
| Ingestion is 100% | A page counts as ingested if it has at least one chunk. The evidence for 364 (a bankers list drawn as vector graphics) and for 377 (the garbled MSTT31c20b font) is not in any chunk. |

## Per-question verdicts

- **Strictly correct:** only 218. The lenient contains-match also credits 370 and 634.
- **Unanswerable questions:** only 365 is a clean refusal. 220 was invalid output. 384 and 660 (false premises) and 635 (a visual attribute) were answered.
- **Ingestion gaps:** 364 (text drawn as vectors), 377 (font without a Unicode mapping) and 658 (table structure lost).
- **Validator false reject:** 383.
- **Out of reach for text-only RAG:** 385, 389, 661 and 662 (layout, cover image, waveform, whole-document aggregation).
- **ACL:** no leaks.
