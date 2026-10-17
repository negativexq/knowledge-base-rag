# Loss audit — luna, MMLongBench-Doc-V2 labels, OCR index

Run: `luna-full-v2` = `luna-full-v9` (97 rows) with 23 rows re-asked after the
OCR re-index and under V2's rewritten questions (`luna-v2-rerun-rows`), all scored
with V2 labels (`--labels`). Resolver and visual answers on.

| | Questions | Correct | Refused | Wrong |
| --- | ---: | ---: | ---: | ---: |
| Answerable | 99 | 53 | 36 | 10 |
| Unanswerable | 21 | 18 (refused) | – | 3 (answered) |

Against `luna-full-v9` (V1 labels, pages lost without OCR: 45/100): V2 labels
turn 229 and 1084 right; OCR restores 364, 519, 524, 525, 727, 729, 732, 740, 741
to the index (some answered right, 519, 524, 727, 729, 732 still refused).

## Wrong (13)

- Unanswerable, answered (3): 388 (a name from the wrong passage), 475 (the
  visual path read a red "Eco-mode" label as a red bar and the check confirmed
  it), 660 (port numbers the document does not have).
- Answerable (10): 227, 371, 382, 515 (counts or share × sample read wrong),
  368 (less specific addresses), 1023, 1070, 1075 (wrong definition or kind of
  change), 1025 (answers "1,358 (000's)"; the contains-match misses 1,358,000),
  1027 (a paraphrase the contains-match misses).

## Refused (36)

- Visual (11): 385, 393, 511, 634, 636, 637, 661, 662, 732 and the two charts
  642, 641. The visual path ran on most and its check refused or read nothing.
- Computed from several figures (14): 206, 216, 219, 225 (share × sample; the
  type check refuses the restated share), 210, 212, 366, 380, 399, 727, 729,
  1072, 1073, 1079. The resolver ran: operands missing from the evidence, a
  program it does not accept (`abs`), or no calculation planned.
- 10-K definitions now spelled out by V2 (3): 1017, 1018, 1020. The resolver
  planned them but bound only some operands (`OPERAND_LABEL_NOT_IN_UNIT`).
- Gold in evidence, refused or blocked (8): 381, 396, 476, 517, 519, 524, 639,
  831.
