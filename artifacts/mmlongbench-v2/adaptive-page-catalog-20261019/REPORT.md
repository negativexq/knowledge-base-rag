# Native page catalog and grounded missing-coverage routing

## Outcome

**1/2 questions answered:** the three visual headings are correctly published; the company-wide director list remains unanswered in this frozen pair. The subsequent single-question recheck is recorded [separately](../adaptive-inventory-window-20261019/REPORT.md).

| Row | Published response | Seconds | Main model calls | Tools |
| --- | --- | ---: | ---: | ---: |
| 372 | I could not obtain enough evidence to answer this question. | 50.76 | 6 | 2 |
| 385 | ["STRATEGIC PRIORITY AREAS", "STRATEGIES", "OBJECTIVES"] [E4.S1] [E3.S1] [E1.S21] [E1.S22] [E1.S24] | 63.06 | 10 | 2 |

## What worked

The application constructs a typed native-page catalog from immutable original PDFs, within page ranges already admitted to the request. The existing selector receives exact native header/footer lines, physical pages, document versions and live support IDs. Printed labels remain location clues; they do not replace physical-page identity or certify an answer. At most 36 pages across three snapshots are inspected per attempt. No extra model call is needed for the catalog, and no embedding, ingestion, index or initial retrieval/reranker setting changes.

Coverage=unknown with a grounded boundary/missing-inventory objection now requests missing coverage, just as coverage=incomplete does. Unknown by itself is insufficient. Repair candidate ranking uses the concrete evidence gap inside authorized units, rather than preserving the same initial anchors. New source choices are checked against presented IDs before retained parent evidence is added. Operation-specific reviewer issues now distinguish non-null bounded item/group/operand indexes from null operation indexes.

**385 — correct original-image answer:** The selector located physical page 5, whose printed label is 2. Collection and input review correctly identified STRATEGIC PRIORITY AREAS, STRATEGIES, OBJECTIVES, left to right. The first final-scope review still lacked an explicit binding between physical page 5 and the question's printed page 2. Its grounded objection triggered the new bounded scope-to-source handoff. A second original-image collection made that page relationship explicit; review and final scope passed. The selector proposed read during repair, but the application preserved the original list operation. Two source receipts remain in state. All ten model calls fit the original request ceiling; no answer-writing finalizer call was added.

**372 — correct page discovered, application window guard blocked progress:** Native catalog hints exposed physical page 9 inside an admitted 8–16 page range. After rejecting the Audit Committee subset's complete-company coverage, the repair selector requested original pages 8, 9 and 10. The application prepended the previous page 11, producing four pages and rejecting `REPAIR_SOURCE_WINDOW_TOO_LARGE`. No second extraction ran. The next fix retains the original receipt in state while allowing a separately checked full-inventory replacement inside the existing three-page window. The window ceiling is not increased.

## Latency of the successful visual question

Total main request: **63.06 seconds**, including retrieval and reranking, excluding model/dependency startup and after-run diagnostic review.

| Work | Seconds |
| --- | ---: |
| Need planning + initial answer attempt | 9.60 |
| Source selection, two calls | 12.75 |
| Input extraction, two calls | 8.89 |
| Input/coverage/operation checks, two calls | 7.45 |
| Final scope checks, two calls | 9.87 |
| Reranking | 11.63 |
| Query embedding | 0.48 |
| Other application work | about 2.39 |

Model calls total **48.57 seconds**, about **77%** of elapsed time. The local page catalog took **0.34 seconds** over two inspections; application computation took milliseconds. Parent/wrapper spans overlap these stages and must not be summed again. Reranking and repeated semantic calls dominate; this is one local diagnostic, not a production latency distribution. Keeping the checked printed/physical-page relationship in the first proof may avoid the extra four-call scope repair in future optimization; that optimization is not claimed here.

## Controls and usage

Each row ran once, sequentially, with frozen source hashes, gpt-6-luna and unchanged role effort. Hard ceilings remained ten requests, 120,000 tokens, 240 seconds and six tool attempts. Original-page access remained version-bound and source-scoped. Main runs saw neither gold answers nor benchmark reference pages. The full backend suite passed **2,140 tests**, with four optional skips and five deselections; **210 adaptive tests** passed; Ruff and mypy were clean.

Main usage: **16 calls**, **113.82 seconds**, **58,338 input tokens**, **6,263 output tokens**, **4 tool attempts**, **0 application retries**. Separate reviews are excluded. Prices are unset, so dollar cost is unavailable.

Raw results, catalogs, typed state, captures and spans remain local and ignored. Only this English Markdown summary is intended for Git. Historical distinct-question coverage stays 30 tried, 27 published source-correct answers, one correct refusal and two never-successfully-answered rows at this revision. Earlier failed and timed-out attempts remain preserved.
