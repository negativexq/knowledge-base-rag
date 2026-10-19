# Intermediate repair: presentation separated, strict output still missing

## Outcome

**One source-verified answer and one failure.** The diagram used the Functions column and returned `["Fact Checker"]`; Twitter failed after valid image values were returned without the mandatory completeness field. The pair was not replaced or silently rerun in the same directory.

| Row | Published response | Seconds | Calls | Tools | Retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 524 | I could not produce a verified answer from the documents. Please try rephrasing the question. | 54.34 | 10 | 4 | 1 |
| 634 | ["Fact Checker"] [E3.S1] [E1.S36] | 43.90 | 6 | 1 | 0 |

## Findings

For 634 the collector returned both source occurrences of Fact Checker under source_object=Functions, while the independent assessment selected unique-name presentation. Application code retained both transcribed items and rendered one name; the first final scope check passed. For 524, the collector correctly returned measurements 11 and 17 with year bindings but omitted `complete`. Pydantic rejected the incomplete envelope; the fallback source selector also produced invalid output, and research exhausted its request allowance. Neither omission was fixed by inventing a completeness default or another paid schema-repair call. Inspection of the installed SDK showed optional defaults made implicit tool strictness insufficient. The subsequent revision explicitly requests native strict output for OpenAI stages, while retaining local Pydantic validation, zero SDK retries, and existing budgets.

All source-scoped runs used gpt-6-luna with unchanged retrieval, embedding, reasoning settings and diagnostic budgets. Main generation never received gold answers/reference pages; separate reviews happened after release. Raw profiles, state, captures and spans remain local and ignored; this report retains the failure. API pricing was not configured. Timings exclude loading and review.
