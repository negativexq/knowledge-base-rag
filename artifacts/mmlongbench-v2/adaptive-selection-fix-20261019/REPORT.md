# Intermediate select/list repair measurement

## Outcome

Twitter answered correctly; diagram output is not counted as a source-verified success because it selected a different diagram region.

These runs are preserved rather than replaced by subsequent results. Main generation used `gpt-6-luna`, the existing index, source-document scope, fast path and evidence needs enabled, and the unchanged 10-request/120,000-token/240-second diagnostic budget. Gold answers and reference pages were available only to separate after-run reviews.

| Row | Published response | Seconds | Model calls | Tool attempts | Retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 524 | 2013 had the lower percentage of rural Twitter users: 11%, compared with 17% in 2014. The platform is identified by the listed Twitter measurement tools. [E3.S1] [E2.S1] [E1.S57] [E1.S70] | 79.90 | 9 | 1 | 0 |
| 634 | ["Verify", "Verify"] [E3.S1] [E1.S36] | 41.52 | 6 | 1 | 0 |

## Findings

Row 524 used typed minimum selection and retained its checked result even though the first scope check lacked the heading connecting the tool list to Twitter. Independent finalization recovered by citing the broader source text; nine main model calls were used. Row 634 produced `["Verify", "Verify"]`, reading the blue Reasoning Program boxes instead of resolving the requested execution-function role using the Functions column and explanatory text. Its reviewer accepted the response and declared the gold label wrong. That reviewer conclusion is not adopted: the same page has two blue-box regions, and the paper explicitly explains the execution handlers through the Functions column. This run exposed source-object ambiguity and the danger of treating a support boolean as task success.

Raw JSON/JSONL, profiles, captures, spans and review packets remain local and ignored. Pricing was not configured; null API cost is not zero. Timings exclude loading and separate reviews. This is a targeted source-scoped diagnostic, not a full benchmark.
