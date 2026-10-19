# Intermediate select/list repair measurement

## Outcome

Twitter answered correctly; diagram abstained after reading the correct Functions-column labels but treating repeated source occurrences as invalid inputs.

These runs are preserved rather than replaced by subsequent results. Main generation used `gpt-6-luna`, the existing index, source-document scope, fast path and evidence needs enabled, and the unchanged 10-request/120,000-token/240-second diagnostic budget. Gold answers and reference pages were available only to separate after-run reviews.

| Row | Published response | Seconds | Model calls | Tool attempts | Retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 524 | 2013 rural users [E3.S1] [E1.S57] [E1.S69] [E1.S70] | 42.57 | 6 | 1 | 0 |
| 634 | I could not obtain enough evidence to answer this question. | 47.64 | 6 | 2 | 0 |

## Findings

Row 524 selected both heading and tool-list context IDs and passed the first scope check in six main model calls. The application now also retains bounded same-page/chunk context when a selector picks only a detached paragraph; that expansion is verified offline, not causally isolated by this run. Row 634 correctly transcribed the two blue Functions-column boxes as Fact Checker. The checker rejected the repeated name as a bad input rather than separating output uniqueness from source transcription. It requested an entity inventory; the repair dispatcher tried to reuse an allegedly insufficient source and rejected the retry. The later revision separates reviewed list presentation from source accuracy and keeps categorical list repair out of arithmetic/count inventory conversion.

Raw JSON/JSONL, profiles, captures, spans and review packets remain local and ignored. Pricing was not configured; null API cost is not zero. Timings exclude loading and separate reviews. This is a targeted source-scoped diagnostic, not a full benchmark.
