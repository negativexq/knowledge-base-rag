# Located-source opening and visual acquisition

Date: 20 October 2026. Implements the boundaries identified in the
[source handoff audit](../../../docs/adaptive-source-handoff-audit.md).

## Outcome

The new workflow recovers **517: Covina and West Covina (CA23)** with a qualitative
original-map comparison. Row 380 now supplies both correct financial operands to the
collector, but does not release a result because arithmetic scale conversion remains
unimplemented. Controls 511, 382 and 477 remain source-correct.

The historical ledger becomes **77 supported answers, one qualified calculation,
four verified refusals and 38 unresolved outcomes across 120 unique questions**.
This is a targeted development check; frozen full-set scores are unchanged.

## Application changes

- `EvidenceNeedSpec.acquisition` records text, image or unknown requirements. The
  existing planner proposes this from the question; count/calculation dispatch retains
  its existing path. No dataset-specific query, page or expected value is in runtime.
- For a declared nonnumeric visual need, a narrow locator chooses a presented authorized
  physical page. The existing source matcher then checks the actual page image, followed
  by scoped extraction and independent observation/constraint checks. Successful facts
  reach the existing independent finalizer and scope validator.
- Quantitative text collection opens explicitly selected indexed PDF pages through the
  existing document reader before treating seed fragments as its input. Opened page
  views preserve original source/version and actual overlapping chunk ranges. Page
  numbers alone do not certify that required rows were supplied.
- Application-owned `PageAcquisition` receipts retain source/version, page, admitted view
  IDs and partial-scan flags. Complete visible receipts can be reused; partial scans are
  not completeness or absence certificates. Foreign-version/page results are rejected.
- Page reads count against the same shared tool budget. Nested collection tool attempts
  now contribute to the reported attempt count. No embedding, index, retrieval/reranker,
  time budget, request budget or model reasoning setting changed.
- `research.acquire.visual` and `quantity.source.open` spans expose selected pages,
  admitted evidence and partial-read flags. The locator chooses a location; it neither
  extracts data nor writes an answer.

## First frozen sequential batch

`live-five`: rows **517, 380, 511, 382, 477**, in that order. All application Python
files and the unchanged harness were hashed before/after; the snapshot stayed identical.
Same gpt-6-luna profile: 10 main requests, 120,000 tokens and 240 seconds, with existing
role-specific effort settings. The generator receives no gold answers or reference-page
overrides. Separate reviewers run after generation.

| Row | Released result | Main time | Main requests | Finding |
| --- | --- | --- | --- | --- |
| 517 | Abstention | 71.36 s | 9 | Correct physical page 10 reached image extraction. Correct qualitative relationship was then discarded by the generic observation value's 100-character limit before independent review. |
| 380 | No verified answer | 97.17 s | 9 | Page reads return both correct operands; scale conversion blocks acceptance. |
| 511 | Start new search | 49.97 s | 7 | Visual locator selects physical page 17; extraction and finalization succeed. |
| 382 | 2 quizzes | 57.27 s | 6 | Count control retained. |
| 477 | 7 quality levels | 43.48 s | 5 | Count control retained. |

This batch is preserved as a failed first attempt for 517, not retroactively upgraded.
Its sequential wall time including startup and separate reviews is 476.41 seconds.

## Qualitative value handoff correction

The first 517 extractor output already identifies CA23 as visibly larger than CA19,
with a map/legend witness. Its structured textual relationship exceeds the generic
100-character `ObservedValue.value` capacity, so it never reaches the independent
checker. The application then wastes remaining work trying to reacquire the same map.

Generic observed text values now allow 1,000 characters. Numeric execution still has
its separate 100-character bound and typed numeric source contracts. Values are not
shortened, summarized or rewritten, and no extra repair model request is introduced.
A regression test exercises a complete visual relationship longer than 100 characters
and verifies that the broader text capacity does not relax numeric execution limits.

`qualitative-pair` remeasures **517 then 511**, sequentially, with a new frozen snapshot
and the same model/settings/budgets. The application/harness hashes remain unchanged
throughout this pair.

| Row | Released result | Main time | Main requests | Assessment |
| --- | --- | --- | --- | --- |
| 517 | Covina and West Covina (CA23), larger than CA19 | 50.20 s | 7 | Located page → original-image match → qualitative extraction → independent check → final answer/scope. No numeric area invented. |
| 511 | Start new search | 40.08 s | 7 | Correct visual-text control retained. |

The pair's sequential wall time including startup/reviews is 143.91 seconds. These
observed timings are not a causal latency estimate across repeated samples.

## Source checks and remaining limitation

- Original `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf`, physical page 10, shows the Los Angeles
  map and numbered legend. Region 23 (Covina and West Covina) is visibly larger than
  region 19 (East Los Angeles). The released answer explicitly limits the comparison
  to the supplied map, without asserting a numerical ground-area measurement.
- Physical page 17 of that PDF visibly contains the orange **Start new search** button.
  The separate review packet again contains a different reference image; its caution
  does not overturn the manually checked runtime target page.
- In 380, the opened physical-page-18/19 views expose **25966.14** shareholders' funds
  and **109638.91** income. Both source readings declare scale **100000**. The existing
  arithmetic normalizer leaves the raw values at that scale while labelling them rupees.
  Independent review correctly rejects this. Source acquisition is fixed for this run;
  **UNITS-001 remains open**. The required difference is 8,367,277,000 rupees, but that
  value is not injected into generation or counted as a released answer.
- The initial five-row batch and final two-row pair are separate frozen measurements;
  there is no claim of a final five-row aggregate after the capacity correction.

## Validation and artifacts

- Full suite: **2,268 passed, 4 skipped, 5 deselected** (49.91 seconds).
- Ruff and mypy passed (158 application files); `git diff --check` passed.
- Focused state/acquisition tests: 45 passed.
- Tests cover seed-fragment hydration, original source lineage, cached reads, shared
  budget exhaustion, empty/partial reads, version/page rejection, non-PDF and count-path
  preservation, visual location/matching/checking/finalization, unsuccessful visual
  location and long qualitative observations with unchanged numeric limits.

Raw JSON, captures, spans, logs, screenshots and hash snapshots remain local/ignored;
only this Markdown report is tracked. Pricing for gpt-6-luna is not configured, so API
cost remains unknown rather than zero. Separate reviewer usage is recorded locally.
