# Population, denominator and question-interpretation source audit

22 October 2026. Read-only application audit after PR #125 (`a6eb343`). Existing questions, captured source readings and original PDFs were inspected locally. No application changes, new generation/judge calls or benchmark reruns. Source findings are not runtime recoveries; historical coverage remains 101/120 with 19 unresolved workflows.

## Finding

The four population cases are not interchangeable. Three permit explicit, assumption-bound approximate sample equivalents; one combines different populations and cannot support the reference count. The question/formula group contains a confirmed prior audit error, two counting/wording ambiguities and a declared-formula choice. Raising effort or enforcing gold integers does not settle these distinctions.

## Population and denominator cases

| Row | Actual request | Source and calculation | Appropriate response boundary |
| --- | --- | --- | --- |
| 206 | Number of surveyed adults rating the administration's ethical standards poor | `05-03-18-political-release.pdf`, physical p. 8: poor 36%; pp. 16-17: n=1,503, weighted results and unweighted sample sizes. 1503 × .36 = 541.08. | About 541 when explicitly applying the reported percentage to the sample size. This does not recover an exact observed respondent count from weighted, rounded percentages. |
| 219 | People who do not go online or use SNS in the older-adults survey | `PIP_Seniors-and-Tech-Use_040314.pdf`, physical p. 6: mutually exclusive chart groups offline 41%, online/no SNS 32%, SNS 27%; age 65+ n=1,526. P. 24 calls sample sizes unweighted and results weighted. 1526 × (.41 + .27) = 1037.68. | About 1,038 if the request means the chart's offline and SNS-user groups among seniors. Do not infer that SNS users use the internet exclusively for SNS, or silently apply the result to all adults. |
| 225 | Number of people age 65+ online daily/almost daily or 3-5 times weekly | Same PDF physical p. 4: among older internet users, 71% daily and 11% 3-5 weekly, total 82%. P. 16: 59% of all 65+ use internet/email, n=1,526. P. 24: weighting/unweighted sample caveat. 1526 × .59 × (.71 + .11) = 738.2788. | About 738 under the chained reported-percentage estimate. Multiplying 82% directly by all 1,526 seniors uses the wrong denominator. Preserve conditional bases, then qualify the estimate. |
| 216 | Number of Democrats saying neither party has high ethical standards | Political PDF physical p. 12: Democrat 18%, independent Democratic leaner 33%. Physical p. 17 provides only combined Dem/Lean Dem n=710, not a Democrats-only base. 710 × .18 = 127.8 reproduces the label but mixes populations. | State that 18% of Democrats gave this response; the Democrats-only sample size is not supplied in this table, so their count cannot be established from these inputs. Do not publish 128 as a source-supported estimate merely because the multiplication works. |

Rounded weighted percentages multiplied by unweighted sample sizes are approximate sample equivalents under a simplifying assumption, not reconstructed raw counts. Labeling the output "approximately" is necessary but does not repair a mismatched base. The minimum requirements are a common source population/period, explicit conditional-base relationships, disjointness for summed groups, and a declared estimate status. No statistical machinery or per-question exception is needed to express those distinctions.

## Question, counting-unit and formula cases

### 214: corrected source finding; the reference 7.0 is compatible with the chart

The question asks for the gap between the youngest and oldest age groups that **strongly disapprove**. The political PDF physical p. 10 (printed p. 8) is a segmented chart. The legend distinguishes total disapproval (bold numbers outside the bar) from strong disapproval (numbers in the dark segment):

| Age group | Total disapprove | Strongly disapprove |
| --- | ---: | ---: |
| 18-29 | 65 | 46 |
| 65+ | 49 | 39 |

The requested gap is **46 − 39 = 7 percentage points**. The later captured 65 − 49 = 16 result uses the wrong category, despite its accepted input review. The earlier report called 7.0 disputed; this source audit corrects that finding. A figure being original-image-backed and independently checked did not guarantee that the right legend category had been selected.

The question additionally describes the president as having started the job in 2018. This premise is not established by the supplied chart and is separate from the survey's 2018 date. A useful conditional answer can identify that qualification and give the chart-based 7-point gap without asserting the premise. Do not force a generic refusal merely because an incidental clause is wrong when the intended chart can be established; do not silently rewrite a genuinely ambiguous entity either.

The workflow remains unresolved until a current live run reads the correct category and releases an appropriately qualified answer. No ledger promotion follows from this inspection.

### 658: two N entries are not necessarily two part identifiers

`DSA-278777.pdf`, physical p. 3, PACKAGES table: Prefix N appears twice. Merged part/package rows and the footnote link the N/PLCC group with 8052AH, 8032AH and 8752BH, and a second group with 8751BH. Counting explicit N entries gives two; interpreting the question as the distinct part identifiers associated with N can give four. The source supports explaining that distinction, rather than replacing a part count with a prefix-cell count to match the reference. The merged-cell relationship and requested counting unit must be explicit in any released answer. No unqualified four-part or two-part workflow success is newly certified.

### 732: figure can mean an illustration or a numerical figure

`germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf`, physical p. 16, includes one Airbus graph panel and a Company/Tweets table showing Airbus = 5. The question is "How many figures are related to Airbus?" A chart-panel count is not the same task as reading the Tweet count. A bounded response can distinguish "5 Tweets in the table; one Airbus graph on this page," or ask which quantity is intended. A page-local panel observation does not certify a whole-document illustration count. Do not silently choose the benchmark's interpretation.

### 1075: formula and debt scope must be declared

`BESTBUY_2023_10K.pdf`, physical p. 39, January 28, 2023 balance sheet: noncurrent long-term debt 1,160, current portion of long-term debt 16, equity 2,795 (USD millions). Under debt / (debt + equity), excluding the current portion yields 1160 / (1160 + 2795) × 100 = 29.3%; including it yields 1176 / (1176 + 2795) × 100 = 29.6%.

The label is consistent with including the current portion. Neither arithmetic alone nor this balance-sheet page establishes that an unstated metric definition is the uniquely intended one. The question supplies no formula. A response can say "Using long-term debt including its current portion divided by debt plus equity, 29.6%." The assumption should be part of the output and source bindings, not a per-row rule selected to recover the label. Whether a source-defined metric elsewhere constrains this choice is not newly established by this page check.

## Two related premise/clarification cases

Existing original-source audit already separates these from ordinary calculation:

- **384:** the available revision is May 2016, not the requested May 2018. The producer can be supplied under an explicit correction; do not assert a nonexistent revision. See [the original source audit](../adaptive-negative-thirteen-audit-20261020/REPORT.md).
- **830:** "When will the market open?" does not specify market/session/date. The course material's closing-time instruction does not establish opening time. The latest saved execution emits clarification, and export handling was subsequently fixed offline; this is not a new current-run certification. Ask for the missing market/time scope rather than import external hours.

## Implementation direction and next verification

Keep the workflow small: retain each percentage with its population, denominator and source scope; compose only validated relationships; execute the expression in the application; preserve whether the answer is a reported fact, approximate derivation or declared interpretation. Unknown compatible inputs warrant acquisition; established incompatible populations warrant a source-limitation answer. Missing formula/counting-unit choices warrant a transparent assumption or clarification, not endless retrieval or target-label tuning.

First test 206/219/225 as qualified estimates with 216 as an incompatible-population control and an ordinary exact-count control. Separately test 214's legend-category binding and explicit premise correction. Then assess the declared interpretation cases 1075/658/732 without scoring every difference from the gold string as a runtime defect. This audit changes no prompt, tool, budget, embedding, retrieval, runtime acceptance or benchmark score.

Pages were rendered and visually inspected using the existing local PyMuPDF installation because Poppler was unavailable. Original PDFs remain unchanged; intermediate PNGs are local under `/tmp/composition-audit-pages`. All calculations above were independently evaluated with Python Decimal.
