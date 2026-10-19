# Required visual fields and entity inventories: frozen pair

## Findings

Both questions published source-correct answers. Row 371 extracted 14, 5, and 11 company names from physical pages 10–11. Input and coverage checks passed; the operation review raised total-versus-distinct ambiguity. Application code computed both as 30, resolving the material ambiguity without another model call. The original ambiguous assessment remained in history; final scope passed.

The independent reviewer supported the individual counts but incorrectly stated that no union comparison had occurred. Its packet omitted the application ambiguity receipts. The full typed state and application-count-audit.json recorded total=30 and exact-normalized distinct=30. The two original pages were separately rendered and visually inspected; names and boundaries matched and no repeated company name appeared across the lists. External alias resolution was not performed. The original review was retained unchanged.

Row 396 collected 22 Strengths and 21 Weaknesses from physical pages 13–14; checking, application counting, and final scope passed. The entity-inventory repair branch itself was not needed in these live runs. Output included explanations/citations rather than bare JSON. Tests at this revision: 2,104 passed, four skipped, five deselected; lint/mypy clean.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 371 | 30 (calculation: 14 + 5 + 11 = 30) (count: 14 listed items) (count: 5 listed items) (count: 11 listed items) [E3.S1] [E1.S33] [E1.S34] | 61.63 | 7 | 1 | True |
| 396 | [22, 21] (Strengths, Weaknesses) (count: 22 listed items) (count: 21 listed items) [E3.S1] [E1.S59] [E1.S60] | 45.03 | 5 | 1 | True |

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
