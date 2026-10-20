# Quantity repair and evidence handoff

## Changes

- Source-correction extraction exposes only input fields. The application owns the
  operation, expression, interpretation, rounding, lookup choices and scalar-output
  conventions. Operand names are fixed; untargeted observations remain unchanged.
  Operation objections retain their separate repair path.
- Mixed text/image repair validates each observation against its own authorized
  locator. Independent checking receives the retained literal text. Old image
  handles are rebound by source, version and physical page, never ordinal alone.
- Explicitly requested visual context pages reach extraction and checking alongside
  input pages, within the existing three-page limit and source/version permissions.
  Input/context roles remain separate; receipt and span metadata record the handoff.

No embedding, retrieval, reranker, model-effort or budget changes were made.
No additional model stage was introduced.

## Offline validation

The full test suite passed: **2,201 passed, 4 optional skipped, 5 deselected**.
Ruff and mypy passed. Fourteen new regression tests cover native patch schemas,
mixed provenance, requested context-page delivery, cross-page lookup relationships,
image-handle rebinding, and rejection of foreign, hidden or unauthorized evidence.

Saved-failure replay results (no model calls):

| Row | Replay result | Remaining boundary |
| --- | --- | --- |
| 1016 | Operation preserved; locators valid; existing values calculate 10314. | Live extraction and independent review must still pass. |
| 1072 | Retained text locators remain valid during image repair. | Full source-scale and operation assessment still required. |
| 641 | Both requested pages 7/8 retained under their authorized supports. | Live selection, reading and comparison still required. |
| 366 | Merge and locator checks pass. | Separate unsupported named-function failure remains. |
| 1070 | Merge and locator checks pass. | Incomplete issuer/evidence semantics remain. |

These replays do not establish new published answers or change benchmark scores.

## Sequential live regression

Requested rows: **1016, 1072, 641, 1021, 1086**, in that order. The last two are
previously successful controls. All use the existing trace harness with gpt-6-luna,
fast path, evidence needs and independent after-run review. Each run retains the
10-request, 120,000-token and 240-second answer budget. Reviewer usage is separate.
Runtime file hashes are frozen for the whole sequential batch.

Completed: all five main runs and independent reviews saved successfully. **One
answer published, four abstentions.** No main run hit the 240-second timeout.
Raw results, captures, spans and selection hashes remain local and ignored under
`live-five/`. Source hashes were checked before every row; runtime stayed fixed.

| Row | Published outcome | Main seconds / requests | Trace finding |
| --- | --- | --- | --- |
| 1016 | Abstention | 66.64 / 8 | Native source-only image repair and retained text locators pass. Correct source display `6,692` is marked with incompatible number notation and rejected with `NUMERIC_NOTATION_INVALID`; no final calculation. |
| 1072 | Abstention | 70.65 / 9 | Mixed text/image repair passes and inputs are accepted. Application calculates 26.304% under the stated operating-income / ending-capital formula. Final scope review requires support for the ROCE definition; the question does not specify the convention. |
| 641 | Abstention | 95.17 / 7 | Both initial pages 7/8 reach collection; repair also receives requested pages 6/7/8. Checker requests a FEVEROUS-S / FEVEROUS identity link. Repair emits a numeric value with ambiguous status, which fails the NumericReading invariant. |
| 1021 | Abstention; prior successful control regressed | 70.76 / 10 | Both deterministic calculations produce the correct 0.715. Scope validator twice claims the quotient must round to 0.716 and blocks release. This is a false arithmetic objection, not missing source evidence. |
| 1086 | 13,929 million USD | 52.57 / 9 | Native source-only image repair passes, checked inputs calculate 15803−1874 and final scope review accepts. |

Main answer time totals **355.79 seconds**, with **43 model requests**,
194,654 input tokens and 24,621 output tokens. Independent after-run reviews use
five additional requests and are excluded from those totals. Pricing is not
configured for this model: receipts report incomplete cost and no reliable USD
amount. A process exit of zero means artifacts were saved, not that the answer
was correct.

## Adjudication and remaining issues

- **REPAIR-001 / REPAIR-002:** live source-only patch schemas and mixed provenance
  succeed in 1016, 1072 and 1086; the old operation-text/page-locator exceptions do
  not recur. Other blockers mean this is not three new end-to-end successes.
- **PAGE-001:** requested visual pages now arrive together. In this run the initial
  selector assigns the graph to the input role, so this live path does not alone
  prove the old context-role transition; the dedicated regression test covers it.
- **1016:** notation metadata and display are inconsistent. Preserve literal text
  and explicit interpretation; do not guess locale or remove numeric validation.
- **1072:** source inputs, deterministic arithmetic and metric-definition support
  are separate. A formula-policy decision is still needed; this run does not prove
  source absence or establish a unique ROCE convention. Percent 26.304% and ratio
  0.263042… are equivalent before their respective rounding.
- **641:** offline validation of the saved native collector output reproduces the
  exact failure at operand 7: `Only a readable numeric input carries a source value`.
  It supplies `value="56.82"` with `value_status="ambiguous"`. The ambiguity concerns
  entity binding while the cell itself is readable; these concerns need distinct
  contracts. An identity join must still be source-supported. The after-run
  review cannot establish it from only the supplied reference images.
- **1021:** independent Decimal calculation gives
  `29441 / 41190 = 0.7147608642874484098082058752`, rounded to **0.715**. Both the live
  scope validator and after-run reviewer assert the wrong arithmetic. Their raw
  diagnoses are preserved but overridden here. The earlier successful control
  remains historical evidence; this latest run is a false refusal. Deterministic
  calculation receipts need an authority boundary against unverified LLM arithmetic
  objections; actual wrong inputs, formulas and scope must remain contestable.
- **1086:** after-run review lacks the actually used balance-sheet pages (it only
  receives the label's reference page 40), so its negative review is not a source
  contradiction. Original balance-sheet verification in the prior fifteen-row
  report already confirms the unchanged assets/cash values and 13,929 result.

All 120 unique manifest questions remain attempted; these are five remeasurements,
not new questions. Historical 120-row/55-row audit scores are frozen and have not
been recomputed with this development batch. No further code fixes or paid reruns
were made after inspecting these results.
