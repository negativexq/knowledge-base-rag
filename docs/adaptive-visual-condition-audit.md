# Visual condition handoff audit

21 October 2026. Read-only runtime audit at main commit `18e8bd1`.
No model calls, benchmark reruns, runtime edits or score changes were made during
this initial audit. The subsequent [implementation and measurements](../artifacts/mmlongbench-v2/adaptive-visual-conditions-20261021/REPORT.md)
record the actual correction, failed intermediate outcome and successful controls.

## Findings

The restrictions were present in all three recorded need-planner outputs. The
failure was not initial question understanding: extraction and acceptance failed
to enforce the requested relationship. Historical outputs must be distinguished
from the protections now present in code.

| Row | Recorded failure | Current boundary |
| --- | --- | --- |
| 635 | Planner retained “with grey background”. Image collector described Fact Checker as “pale gray-blue”; checker approved it. Final scope cited generated transcription and caption, without separately reviewing the color relationship. | Original-page reuse in scope selects exact completed arithmetic/count candidates, excluding lists. Requirement validation can accept a condition using only generated proof text. This is the first implementation target. |
| 638 | Planner retained “figure at the bottom of page 6985”. Both collection attempts counted the complete example in Figure 2 at the top. The checker repaired count mode but approved object identity; scope accepted the generated inventory. | Count scope now receives the reviewed original pages and explicit requirement bindings. Native location diagnostics also exist, but require a resolvable object anchor and compare peer captions. Missing anchors skip that check. The earlier inventory follow-up already withheld this wrong-object answer; that historical incorrect release is not a claim that current code still publishes it. A fresh targeted measurement is needed to assess the current outcome. |
| 660 | Planner retained “from port 10-13”. Answerer returned Port 1 / P1.1. Scope and after-run review verified its Capture/Reload Trigger function while overlooking the requested range. | Current `range_conflicts` rejects this exact historical answer offline. The historical scope response also lacks the now-required requirement bindings. Keep this as a regression/control; do not implement a second range rule. |

The retained original renders were inspected directly: row 635's Fact Checker
boxes are pale blue; on printed page 6985 the complete program example is in the
upper Figure 2, with a different Figure 3 below. A correctly read label/count does
not establish that the question-selected object was used. This audit does not
invent an alternative count or infer whole-document absence.

## Code boundaries

- [Scope projection](../app/llm/quantity_scope.py):
  `semantic_scope_projection` selects arithmetic/count modes only. The resulting
  IDs are the only records passed to `checked_scope_images` in
  [answer validation](../app/llm/adaptive.py). An image-backed list therefore does
  not get this original-page handoff, even if its items were independently checked.
- [Requirement validation](../app/llm/scope_requirements.py): checks complete
  binding indexes, verdicts and valid source locators. Generated witness text is
  excluded from the additional entity/population name check, but condition bindings
  have no equivalent independent-source requirement. A supported condition with
  a valid generated-proof locator can pass. This is an evidence-origin gap, not
  permission to determine color from text heuristics.
- [Inventory diagnostics](../app/llm/inventory_evidence.py): location checks need
  a native object anchor and caption peers. They are useful contradiction hints,
  not a universal certificate of object identity or absolute page position.

## Offline checks

- Replayed the exact 660 question and published answer through `range_conflicts`:
  **conflict detected**.
- Parsed all three historical scope responses against current
  `RequiredScopeJudgment`: **all rejected for missing requirement bindings**.
  This checks schema coverage, not future model judgment quality.
- Synthetic condition replay with a generated-only witness: **accepted** by
  `validate_requirements`; confirms the current evidence-origin gap.
- Completed-list projection replay: **no record selected** for scope page reuse.
- Existing inventory/scope and checked-image suites: **30 passed**.

## Recommended minimal correction

1. Reuse version-bound original pages for exact independently checked list
   candidates in the existing scope call. Keep the actual list and requested
   conditions visible; list semantics must not inherit arithmetic authority.
2. Bind visual condition approval to the original object/page evidence, rather
   than treating generated transcription as independent support. Preserve the
   distinction between readable labels, object identity and condition satisfaction.
   Textual conditions supported directly by source text must remain valid.
3. Reuse the existing repair/research path on mismatch or unknown identity. Missing
   evidence should not become an automatic negative answer. Add no judge loop,
   color vocabulary, row IDs, fixed coordinates or document-specific rules.
4. Measure 635, 638 and 660 sequentially, with positive visual-list, spatial-count
   and in-range controls. Report incorrect-release prevention separately from
   successful answers and safe insufficiency.

Recorded inputs are under the evidence-completion row635, remaining-thirty row638
and unseen-fifteen row660 artifact folders. Raw captures and renders stay ignored;
this report contains no raw capture dump.
