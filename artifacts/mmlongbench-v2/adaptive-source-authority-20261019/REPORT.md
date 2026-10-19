# Original-page authority and context: intermediate pair

## Findings

Neither question released a correct answer: 0/2. In row 729, native_text_chars=0 and full-page raster coverage triggered image reading. Both extractions correctly obtained 24,12,5 and preserved provisional 41. However, an irrelevant arithmetic count_mode=per_group compatibility default was interpreted by the checker as a vector request. Recollection did not fix that semantic contract leak.

In row 525, the selector found numeric source E1.S57 and relationship sources E1.S65/S66/S67. It returned pages [15,18], but validation checked the list only against the numeric source and rejected an authorized context page before collection. Later attempts from an overly broad OCR view hit the bounded-page guard and request reserve.

The next revision projected mode-specific fields and partitioned numeric/context page roles. These intermediate abstentions are preserved and are not counted as successes or latency improvements. The revision had passed 2,110 offline tests before these live checks exposed the missing integration cases.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 525 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 35.38 | 9 | 3 | True |
| 729 | I could not obtain enough evidence to answer this question. | 50.68 | 8 | 2 | True |

## Scope and records

These are selected development diagnostics scoped to the source document, not
an open-corpus retrieval score or a complete benchmark. A reviewer support flag
alone is not a success: an abstaining response is not counted as a published
answer. See the findings for source correctness, formatting differences, and
any limitations of the review packet. Main generation did not receive gold
answers; separate diagnostic review occurred afterward.

Reported main-run latency excludes dependency loading and separate PDF review.
Model usage is recorded in local result files; reviewer usage is separate.
A null cost field means prices were not configured, not that calls were free.
Historical price estimates, where stated, are not current pricing or billing.

The underlying measurements, source snapshots, full typed state, model outputs,
spans, profiles, and independent reviews remain unchanged in local run folders.
Raw JSON/JSONL, images, captures, source capsules, and original-language report
backups are ignored by Git. This English summary retains the outcome and main
failure mechanisms; later successful runs do not overwrite earlier failures.
