# Evidence-type repair: first frozen pair

## Findings

One correct published answer out of two. Row 371 selected the correct physical pages 10–11 and extracted 30 company names, but wrote page information in witness prose while leaving typed page fields absent. Group completeness fields also defaulted to false. QUANTITY_ITEM_PAGE_INVALID stopped checking; abstention was not counted as success. Row 396 published [22,21].

The typed entity-inventory repair contract was covered offline but was not exercised as a targeted repair in this pair: row 371 selected the lists directly. The next revision made image page, witness, and explicit completeness fields required. These results are preserved separately from later success.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | I could not obtain enough evidence to answer this question. | 46.99 | 4 | 1 | True |
| 396 | [22, 21] (Strengths, Weaknesses) (count: 22 listed items) (count: 21 listed items) [E3.S1] [E1.S58] [E1.S59] [E1.S60] | 52.95 | 6 | 1 | True |

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
