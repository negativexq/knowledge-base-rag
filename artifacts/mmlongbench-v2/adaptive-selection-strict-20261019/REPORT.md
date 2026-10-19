# Source-input operation repair: final strict-output pair

## Outcome

**2/2 formerly unanswered questions now have correct, source-supported published answers.** Both completed within the unchanged diagnostic budgets, with six main model calls, one collection attempt, no retries, and one passing final scope check each. The finalizer model was not called. This is a targeted development recheck, not a full benchmark or stability guarantee.

| Row | Question | Source answer | Published response | Seconds | Main calls / tools / retries |
| --- | --- | --- | --- | ---: | --- |
| 524 | Which year has the lower rural-user percentage for the platform identified by the named tools? | 2013: 11%, versus 17% in 2014 | Rural users, 2013 [E3.S1] [E1.S57] [E1.S69] [E1.S70] | 40.07 | 6 / 1 / 0 |
| 634 | Which execution-function names have blue backgrounds in Figure 1, alphabetically? | ["Fact Checker"] | ["Fact Checker"] [E3.S1] [E1.S36] | 37.72 | 6 / 1 / 0 |

## Implementation and evidence

- **Typed selection:** source-printed decimal measurements, identity labels and units are collected separately. `select_mode=minimum` or `maximum` executes in application code and preserves tied labels. Arithmetic remains restricted to numeric arithmetic; no arbitrary comparison expression or code execution was enabled. Mixed units are rejected until a valid conversion is supplied elsewhere.
- **Categorical listing:** list extraction uses flat items and source-object/column provenance rather than count groups. Application code applies ordering and the independently reviewed uniqueness policy. Source transcription and output presentation are judged separately; correct repeated source occurrences are not invalid inputs merely because a name-set result is unique.
- **Context retention:** authorized same-page/chunk sibling paragraphs can remain with a selected context seed, bounded to six IDs and a 6,000-character expansion allowance. Identity checks include source, version, tenant and parent block. A dedicated span records selected seeds and retained IDs. Both final Twitter seeds already included the heading and list, so this run does not isolate the causal effect of automatic expansion; offline tests exercise a detached-list-only selection.
- **Native strict output:** OpenAI PydanticAI stages now request `ToolOutput(..., strict=True)`, enforcing required fields and forbidding extra fields at generation time. Local Pydantic coherence checks, zero SDK retries, and request/time/token budgets remain. No mandatory completeness field is silently defaulted to true and no paid schema-repair loop was introduced. Other providers retain their existing compatibility path.
- **Independent finalization:** checked inputs, assessments, application results and execution diagnostics remain typed state. Successful selection/list results can be finalized without another answer-writing model call. Execution failures retain inputs and a failed execution receipt rather than losing the extraction.

### Row 524

The original slide 15 Rural row shows 11 in 2013 and 17 in 2014. Slide 19 identifies the measurement tools as Twitter tools. The image collector returned both measurements; application minimum selection returned the 2013 label. Heading/list context E1.S69/E1.S70 reached the first final scope check alongside E1.S57 and checked-image proof E3.S1. Six model calls ran: need planner, answerer, selector, collector, checker and scope validator. The released short answer was “Rural users, 2013”; there was no later paraphrase call.

### Row 634

The original paper Figure 1 (physical page 2) contains two different blue-box regions. The Reasoning Program column contains Verify instructions, while the Functions column contains Fact Checker execution handlers. The explanatory text identifies execution sub-task handlers through the Functions column. The final collector explicitly recorded source_object="Functions column", and the independent input and final scope checks supported Fact Checker. A separate original-page review agreed. This conclusion uses source role/relationships rather than an exact gold-label match.

The final strict run stored one item for the shared Fact Checker name, with unique-name presentation. It answers the requested name set but does not prove an exhaustive inventory of both box occurrences. The preceding revision and offline tests retain duplicate source items while rendering a unique list; occurrence counting still requires the count inventory contract. This distinction remains visible rather than treating a unique-name answer as a figure-count result.

## Previous attempts remain separate

| Version | Twitter | Diagram | Main calls | Main seconds |
| --- | --- | --- | ---: | ---: |
| [adaptive-selection-fix-20261019](../adaptive-selection-fix-20261019/REPORT.md) | Correct; scope recovered through finalizer | Different diagram region; not counted as source-verified | 15 | 121.42 |
| [adaptive-selection-fix-v2-20261019](../adaptive-selection-fix-v2-20261019/REPORT.md) | Correct | Abstained after repeated-name/input-policy confusion | 12 | 90.21 |
| [adaptive-selection-fix-v3-20261019](../adaptive-selection-fix-v3-20261019/REPORT.md) | Failed: mandatory completeness omitted | Correct Functions-column name set | 16 | 98.24 |
| Final strict output | Correct | Correct | 12 | 77.79 |

The original [mixed-five report](../adaptive-mixed-five-20261019/REPORT.md) retains both initial abstentions. An intermediate reviewer accepted the wrong/different diagram region and called the gold label wrong; that conclusion is explicitly not counted as a source-verified success. Reviewer booleans alone are not the task-completion metric. No failed run was overwritten.

## Validation and accounting

- Backend: **2,125 passed**, four skipped, five deselected; Ruff and mypy passed.
- Offline adaptive checks: **195 passed**, including exact-decimal ties, mixed-unit rejection, illegal-expression rejection, list ordering, occurrence preservation, both reviewed uniqueness directions, context authorization/version/page/size boundaries, typed-state round trips, independent finalization, and strict output configuration.
- Embedding, index, retrieval/reranking settings, reasoning efforts and default flags were unchanged. Source IDs are scoped to the question document; main generation receives no benchmark answer or reference-page list. Reader/final reasoning remains medium where configured.
- Every final main model span recorded `research.output_strict=true`. Neither final run had a model-output-invalid failure or a finalizer call.

Final pair: 77.79 main seconds; 12 model calls; 25,203 input tokens; 4,916 output tokens; 2 tool attempts; 0 retries. Times exclude dependency/model loading and separate review.

All four repair-version pairs: 387.66 main seconds; 55 model calls; 140,292 input tokens; 23,369 output tokens; 12 tool attempts; 1 retries. Times exclude dependency/model loading and separate review.

The eight separate review calls used 79,590 input tokens and 11,263 output tokens. Dollar cost is unavailable because model prices were not configured; null is not free. These review calls are outside main-answer usage.

The historical ledger now contains **20 distinct questions with a source-supported answer out of 20 tried**. Only these two were rerun on the final strict-output implementation; the other 18 successes are historical and require a fresh regression run before making a current 20/20 claim.

Profiles pin the working-tree source hashes because these measurements precede a commit. Raw results, full typed state, captures, spans, reviews and images remain local and ignored. Only compact Markdown summaries are intended for Git.
