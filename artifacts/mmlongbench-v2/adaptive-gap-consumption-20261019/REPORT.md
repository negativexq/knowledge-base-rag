# Source-gap consumption and population binding: successful recheck

Row **212** published **92%** in **123.41 seconds**, with **9 model requests,
3 tool attempts and no diagnostic retries**. Independent after-run original-PDF
review confirmed the answer. Source hashes were frozen before the single request;
generation could not see gold answers or reference pages. No question-specific
values, party names, document rules or page numbers were added to runtime code.

## Observed execution

1. Initial lookup collection read physical page 14 and correctly transcribed
   Democratic candidate support as 92% and Republican support as 90%. It marked
   the four prerequisite comparison values as missing, preserving the distinction
   between public assessments and registered partisan voters.
2. Independent review rejected incomplete coverage without discarding those
   observations. The application searched the same authorized immutable document,
   using the original question alongside the missing-field descriptions.
3. Search admitted complete source chunks. The typed gap receipt retained the
   parent, required evidence, candidate IDs and subsequent inspected sources.
   Repair selected `E5.S1` and `E3.S1` and proposed pages 4 and 14. Application
   binding retained the complete bounded candidate range, producing pages 4, 5
   and 14 within the unchanged three-page inspection ceiling.
4. The new extraction bound public assessments to **50%, 42%, 50%, 41%**, and
   candidate support to the separate registered-voter populations. Input,
   coverage and operation review passed against the original page images.
5. Application arithmetic compared Democratic **50+42=92** with Republican
   **50+41=91**, selected the Democratic identity and returned its linked
   congressional-support value, **92%**. Final scope and separate source review
   both passed. The incomplete parent receipt remains in state.

`quantity.gap.bind` records actual source/page handoff; `quantity.gap.review`
records a resolved gap; `quantity.lookup` records comparison scores, selected
identity and linked output operand. Two lookup spans reflect provisional and
final application computation, not additional model calls. No finalizer model
rewrote the checked answer.

## General changes and limits

`ResearchState.quantity_gap_searches` is typed application state, not an LLM
summary. Search results remain candidates until independently checked extraction
establishes the missing inputs. New candidates are explicitly carried into bounded
inspection. Source freshness compares content and inspected pages across both
input and context roles; changing an existing source's role or ID is not progress.
Lookup operands retain population, series and period for role-specific review.

The live selector already chose the newly located sources. This success therefore
does not isolate the effect of overriding an unchanged selector: the deliberately
repeated-old-source case is verified by an offline end-to-end test. Likewise,
semantic population judgments remain model-based; structured fields and review do
not guarantee that every future population distinction will be understood correctly.

This is one successful diagnostic recheck, not a stability estimate or full-set
regression score. The [preceding failed three-row run](../adaptive-evidence-completion-20261019/REPORT.md)
is retained. Row 635's blue/grey visual-condition error remains unresolved; it was
not rerun or counted as a success here. Previously successful rows were not paid-rerun
on this final revision.

## Validation and measurement

Before this request: **2,154 backend tests passed**, four optional skips and five
deselections. The updated offline adaptive target passes **224 tests**, including
13 completion/lookup/absence tests. Ruff and mypy are clean. Tests cover ignored new
evidence, input/context role changes, same-page aliases, source-window ceilings,
checkpoint retention and distinct comparison/output populations.

The same `gpt-6-luna` effort profile and ten-request/120,000-token/240-second
diagnostic ceilings were retained. Main usage was **46,737 input tokens and 8,379
output tokens**, including 1,251 cached input tokens. Main elapsed time includes
retrieval/reranking and generation; the separate diagnostic reviewer is excluded.
Pricing is unset, so dollar cost is unavailable. Embedding, ingestion, initial
retrieval/reranking settings and production budgets were unchanged.

Raw profiles, runtime hashes, JSON, source states, captures and spans remain local
and ignored. The [aggregate ledger](../../../docs/adaptive-solved-questions.md)
counts this as a historical source-supported answer, not an additional distinct
question: **35 tried, 32 published source-supported answers, one correct refusal,
two unresolved** across development revisions.
