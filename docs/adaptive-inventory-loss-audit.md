# Inventory loss audit: 636, 662 and 663

Date: 21 October 2026. Read-only runtime audit on main `43d2f98`.
No runtime edits, model calls, retrieval changes or new benchmark results.

## Finding

The three outcomes are not a single embedding or extraction failure. Row 662 loses the accumulated working inventory between windows, misses two relevant original pages, stops before reviewing its second extraction and lacks a combined count/page-list output operation. Row 663 retains the items it finds but stops without guide-wide coverage and has an unresolved counting-unit definition. Row 636's recorded immediate blocker was a witness-size guard that has since been corrected; its remaining source/object scope has not been remeasured.

## Evidence and method

Inspected saved result, complete model outputs, typed state and spans from:

- `adaptive-remaining-thirty-20261020/row636`
- `adaptive-remaining-thirty-20261020/row663`
- `adaptive-context-coverage-20261020/live-four/row662`

These paths are under `artifacts/mmlongbench-v2/`; raw JSON remains ignored. Current merge and locator functions were replayed locally against saved typed records, without calling a model. Original DSA-278777.pdf was visually surveyed across all 21 physical pages; paper pages 2, 5, 8, 9, 10 and 15 were rendered for scope checks. Intermediate renders and replay state are under `/tmp/inventory-audit` and `/tmp/inventory-state-*.json`, not tracked.

## Row 662: waveform inventory and page list

Question requests both the count of waveform figures and an ascending list of their pages.

| Stage | Observed data | Loss or boundary |
| --- | --- | --- |
| Plan | Correctly retains waveform condition and page-list request | Not a planning loss of the page-list requirement |
| Source catalog | Location candidates include pages 11, 12, 13 and 16; catalog is not a whole-document scan | Relevant pages can be discoverable without being selected |
| First image window | Pages 11, 13, 17 | Page 17 is a schematic; page 12 is not opened |
| First extraction/check | Five diagrams: three on 11, two on 13. Inputs supported, total coverage incomplete | Five items remain in the parent record, but no independently reusable per-window completion receipt exists |
| Repair selection | Pages 14, 16, 18 | Finds new material but still omits 12 and 20 |
| Second extraction | One waveform on 16, one on 18 | The child draft contains only these two items |
| Current merge replay | `scope_research`: old 5 + new 2 produces active draft 2 | Parent is preserved in state, but no combined seven-item inventory is formed |
| Second review | No checker call completes or starts | `TOKEN_RESERVE` is raised before the call; child stays pending |
| Finalization | First proposal says two diagrams and unavailable page numbers; retry safely abstains | Page information exists in typed drafts, but neither record qualifies as a checked complete quantity in model context |

Original-page visual survey confirms additional waveform content on pages **12** (shift-register timing) and **20** (EPROM programming/verification). The distinct waveform-bearing pages are **11, 12, 13, 16, 18, 20** under a visible timing-diagram interpretation. These findings establish missed acquisition, not a runtime-certified answer. Do not simply publish seven or mark the first two windows complete. Signal traces inside a diagram and diagram objects are different counting units.

The recorded token budget is 120,000. Cumulative actual usage after the second collector is **77,214** tokens. First-window collector/checker consume 18,388/19,150 input tokens; second collector consumes 19,629. The guard also reserves estimated next-call input and configured output capacity; therefore a stop before consuming 120,000 actual tokens is expected. The current [call guard](../app/llm/adaptive.py#L931) uses estimated input plus image allowances and output reserves. The trace does not record the rejected checker's exact estimate; do not invent an exact overflow amount. The final two calls bring total usage to 86,809. This is a token-reservation stop, not elapsed-time timeout.

## Row 663: connection graphs

- First window: page 3, two pin diagrams (DIP and PLCC) inside Figure 2. Checker accepts the item readings but cannot certify the guide-wide total.
- Repair window: pages 3–5. Collector returns the same two diagrams plus oscillator connections and external-drive configuration, four items total. Checker again supports inputs but marks coverage incomplete.
- Both records and all four child items survive. Current replay routes this through `entity_inventory` and returns the four-item replacement. There is no demonstrated item loss in this transition because the replacement repeats both originals.
- The narrow collection loop permits one repair by default. It stops after the second incomplete review with `QUANTITY_REVIEW_UNRESOLVED`, seven requests, 87.21 seconds. It does not keep visiting the remaining guide pages.
- Original pages 14, 15, 17 and 18 contain further programming/verification schematics. Whether all are included by “connection graphs,” and whether the two subdiagrams of Figure 2 count separately, needs a consistent source-grounded counting unit. Raising a count to four without that definition and coverage would be unsupported.

## Row 636: prompt examples shown in the main body

- Plan correctly requests shown examples in the main body, not training demonstrations used by a model.
- Selector picks text page 5 through broad support E2.S1, which spans multiple sections/pages. Collector proposes one Figure 1 overview example and explicitly marks coverage incomplete.
- Saved run ends after three requests on `QUANTITY_REFERENCE_TOO_LARGE`, before independent checking. The parent draft remains; no count executes.
- Current [locator resolver](../app/llm/quantities.py#L614) retains full immutable line ranges and makes the optional quote empty if oversized. The saved draft resolves successfully against saved support text in a current-code replay. The obsolete size error must not be listed as an unfixed runtime defect.
- The paper's physical page 2 contains the Figure 1 model overview; page 5 contains the Figure 2 prompt template. References start on page 10, and full prompt listings are in the appendix. The recorded extraction does not establish which shown prompt-example objects are being counted or the main-body boundary. A printed `20` about examples used by a model cannot substitute for an inventory of examples shown.
- No live rerun is made in this audit. Removing the old guard does not prove the question is now solved.

## Current code boundaries

1. [Repair classification and merge](../app/llm/quantity_review.py#L270): count boundary issues route to scope research or entity inventory, where the replacement supersedes the active draft. The list-completion branch has a union path; count windows do not have an equivalent source-bound accumulator.
2. [Typed selection](../app/llm/quantity_state.py#L24): at most three image pages per call. A bounded window is appropriate; the missing capability is continuation and accumulation across windows, not necessarily a larger single call.
3. [Collection loop](../app/llm/quantities.py#L757): one repair by default. Source search cursors can advance candidates, but do not certify an inventory's reviewed coverage or finish all windows.
4. [Context handoff](../app/llm/adaptive.py#L671): complete accepted quantities are exposed; checked partial inputs track numeric operands. Supported count items with incomplete global coverage and pending count drafts lack the corresponding reusable handoff.
5. [Count output](../app/llm/quantities.py#L446): total, distinct or per-group counts execute; the deterministic candidate renders counts. A requested distinct ascending page list is not derived alongside the count. The planner retaining it is insufficient.

## Recommended correction order

1. Preserve independently checked item identities and page-local coverage separately from whole-document completeness. Keep pending observations distinct from accepted ones.
2. Accumulate accepted windows by source/version and source occurrence; preserve old items and provenance. Deduplicate the same occurrence, not equal labels. Do not carry a local `complete` flag into whole-source completeness.
3. Track relevant candidate pages, inspected positive/negative windows, pending windows and an explicit target/counting unit. Continue only through necessary bounded work, using the existing budget. Source acquisition exhaustion is not a semantic absence proof.
4. Reduce repeated payloads: avoid sending irrelevant native glyph/geometry inventories beside the same images on every collection/check pass. Retain full evidence in typed state and supply only the evidence required by that step. Never truncate source quotes to force an answer or drop original-image review.
5. Derive requested count and distinct sorted page list from the same accepted inventory in application code. This needs no additional model calculation or finalizer rewrite.
6. Remeasure 636/662/663 sequentially with short-answer and existing count/list controls. Do not promote a historical result on offline replay alone.

Do not weaken the completeness checker. It correctly prevented partial windows from being presented as guide-wide totals. The defects are the missing completion workflow and prepared-result handoff around that check. The ledger remains **100/120 accepted outcomes, 20 unresolved**.
