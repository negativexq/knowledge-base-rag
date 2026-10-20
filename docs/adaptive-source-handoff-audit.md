# Source acquisition handoff audit

Date: 20 October 2026. Base: merged PR #117 (`063adcc`).

This is a read-only investigation of rows 517 and 380 from the completed
[nine-row regression](../artifacts/mmlongbench-v2/adaptive-routing-scope-20261020/REPORT.md).
No runtime change, reingestion, embedding change or new paid model run was made.
The purpose is to identify the missing workflow before choosing an implementation.

## Confirmed findings

| Boundary | Row 517: qualitative map comparison | Row 380: financial difference |
| --- | --- | --- |
| Available source | Correct EPS document. Admitted E1.S87 is physical page 10 and names both CA19 and CA23. | Correct financial document. Selector explicitly requests physical pages 18 and 19. |
| What reached reasoning | Parser text identifies the two regions but carries no boundary geometry. | First collector receives E1.S23, only the balance-sheet title, plus E1.S53, a cash-flow excerpt. It does not receive the income table. |
| Actual actions | Three text searches; no inspect, image extraction or visual source selection. | Two text quantity collections, with an intervening document search. No page-19 read or original-image collection. |
| Why the current checks did not repair this | The task is correctly typed as compare, but acquisition modality is not a typed evidence requirement. The reader keeps searching for an explicit textual area comparison. | Page-quality inspection sees readable native text and does not force images. That says nothing about completeness of the selected indexed fragments. |
| Terminal result | NO_RESEARCH_PROGRESS, abstention. | REQUEST_RESERVE, abstention; income remains unread. |

## Row 380: the income is already indexed

A separate, authorized read-only replay used the run's original source ID and immutable
version in the active `kb_bench_mmlongbench_v2` collection, tenant `bench-mmlongbench`.
It used the existing `DocumentReader`, not a new parser or a gold-driven runtime override.
Physical page 19 came from the saved selector output, before this audit.

- Full version-scoped document scan: **37 blocks; scan_limited=false**.
- The existing index contains **109638.91** in an 85-character page-19 block
  (`c3576e1c-43cf-536a-8580-0771d01ad58c`).
- `DocumentReader.read(action="page", page=19, limit=50)` returns **four blocks**,
  `has_more=false`, and includes the income amount.
- The original physical page 19 / printed page 31 visibly shows the profit-and-loss
  statement, the 31.3.2003 column, sales 107734.16, other income 1904.75 and total
  income **109638.91**, in rupees in lacs. Native PDF text contains these values too.

Therefore this case is not evidence of an embedding failure or a parser losing the
income amount. The missing operation is **opening the already selected page through
the existing document reader before treating its selected fragments as complete input**.
The initial retrieval admitted only other portions of page 19; selecting page 19 as
metadata did not load its missing indexed blocks.

The relevant implementation boundaries are:

- `app/llm/quantities.py`: selection records physical pages and checks page quality;
  the text payload is still built from `selected` support units, not a page read.
- `app/evidence/pdf_structure.py:page_quality`: `requires_image` detects essentially
  absent/sparse native text. It explicitly does not guarantee OCR or table accuracy,
  nor completeness of indexed fragments supplied to the collector.
- `app/evidence/documents.py:DocumentReader.read`: the necessary page operation already
  exists and returns the missing indexed amount in this replay.

A separate issue remains after acquiring both operands: the result must convert the
source scale (lacs) to requested rupees. Page acquisition alone does not fix UNITS-001.

## Row 517: a visual relationship is being searched as text

Original `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf`, physical page 10, contains the Los
Angeles market map and the corresponding numbered legend. E1.S87 already binds CA19
to East Los Angeles and CA23 to Covina and West Covina. Manual original-page inspection
shows region 23 drawn much larger than region 19. This supports a qualitative comparison
in the supplied map, not an invented numeric land-area measurement.

The saved planner requests geographic size/extent with `operation="compare"`. The fast
answer correctly says the names/codes do not establish relative size. Then all three
reader decisions request another text search for comparative area/extent. The workflow
never invokes the image extraction path that already exists and worked for row 511.

Thus the first demonstrated gap is **modality selection and dispatch after locating the
source**, not a demonstrated inability to interpret the map. The generator never saw
the map image in this run. A stronger reasoning effort cannot be assumed to repair that.

The relevant boundaries are:

- `EvidenceNeedSpec` describes requested fields, constraints and operation; it does not
  retain a typed requirement for a visual relationship versus text/table observations.
- `ResearchDecision.modality` is available for extraction, but every reader decision
  must choose it again. No application-owned acquisition requirement dispatches the
  prepared visual work.
- Repeated non-progressing searches stop the run. They do not first require trying a
  different, justified representation of the already located source.

## Proposed missing workflow

1. **Locate:** retain authorized source identity, immutable version and candidate pages.
2. **Open:** if indexed fragments do not contain required fields, use the existing
   bounded page reader before another global search. A page number is a locator,
   not evidence that its contents were supplied.
3. **Choose representation:** retain a typed, question-grounded acquisition requirement
   for source text, table observations or a visual relationship. Use original images
   when spatial/color/layout relationships are material; do not require invented
   numeric observations for qualitative comparisons.
4. **Extract:** dispatch the existing narrow extraction tool with the selected need and
   actual source view. Preserve source-page/object bindings and independent checks.
5. **Compute:** execute only after inputs and scale are established. Keep unit conversion
   separate from source acquisition.
6. **Stop or continue:** track missing fields and attempted representations, rather than
   treating a changed search string or newly returned irrelevant chunk as gap closure.

Implementation should reuse the existing page reader and visual extraction capabilities.
It should not force all PDFs through vision, increase global budgets or add document-
specific page/value rules. A native-text character count must not be reinterpreted as
an assertion that a selected fragment includes the required table rows.

## Validation needed before closing an issue

Offline checks should cover heading-only seeds on a correctly selected page, required
rows found by a bounded same-version page read, unreadable/partial tables, missing visual
relationships, non-PDF sources, authorization/version failures, budget exhaustion and
preservation of successful prior facts. Then rerun 517 and 380 plus previously working
text and count controls sequentially. No new live success is claimed by this audit;
ledger counts remain **76 supported / 1 qualified / 4 verified refusals / 39 unresolved**.


## Implementation and measurement follow-up

The [source acquisition report](../artifacts/mmlongbench-v2/adaptive-source-acquisition-20261020/REPORT.md)
records the subsequent implementation and frozen live runs. Bounded page opening
provides both correct operands in 380. Typed visual acquisition and preservation of
long qualitative observations recover 517. The earlier read-only findings above remain
the diagnosis that motivated this work. Arithmetic scale conversion remains a separate
open issue; acquisition success does not certify a final financial result.
