# Agentic MMLongBench mini-10 — 2026-10-18

Ran the current PydanticAI agent with GPT-6 Luna, claim-scope verification,
calculation/operand tools and visual reading enabled. Used the existing isolated
MMLongBench collection, question-document retrieval scope, corrected V2 labels,
Qwen3 embeddings and BGE reranking at 40 candidates / top 14. No corpus re-ingest,
prompt change, budget tuning or question rerun was performed for this measurement.

The ten-question selection was committed before model generation (`0728c98`),
using seed 20261018 and metadata-only strata: two text, two table, one layout,
one chart, one figure, one mixed-evidence answerable question and two unanswerable
questions. It spans ten PDFs. Categories overlap. These are development-visible
benchmark questions, not a fresh blind holdout.

## Results

- Existing automatic scorer: **5/8 answerable correct (62.5%)**, **1/2 unanswerable
  correctly refused**; combined label-based task successes **6/10**.
- Manual cited-evidence review: **4/8 correct and grounded answers** plus **1/2
  correct refusals**; combined **5/10** under the correct-and-evidenced objective.
- The extra automatic success is row 732: output `5` matches gold but comes from
  a Twitter-activity table rather than a count of Airbus figures. The scope guard
  accepted this wrong quantity binding. Its citation is page 16, outside gold
  pages 7/11/14. The automatic score is preserved, not silently replaced.
- Retrieval hit at least one evidence page for **8/8** answerable questions;
  all their labeled pages had indexed text. This does not mean every required
  fact, layout relationship or visual element was model-visible or understood.
- Two answerable questions ended in `AGENT_BUDGET_EXCEEDED`; one answerable
  question was voluntarily refused. One labeled-unanswerable question was answered.
- Cross-tenant retrieval probe: **0 leaks**. The direct benchmark harness does
  not exercise HTTP authentication or application user/group-grant management.
- **33 actual model calls**, including scope checks and nested tools; **335825
  input / 2159 output tokens**, about **240 seconds** summed question latency;
  median **24.1 seconds**. This is not a measured invoice or startup-inclusive
  wall time. The forensic trace's token-named keys are redacted; these usage
  totals come from the saved, numeric generation metadata.

| Row | Type | Gold | Observed outcome | Manual finding |
| --- | --- | --- | --- | --- |
| 210 | Chart/text | 21% | Abstained | Retrieved relevant page; duplicate-only search, no further useful tool use. |
| 366 | Text/calculation | 2.4% | Token budget exceeded | Existing numeric validator repeatedly rejected; scope checker was never reached. |
| 381 | Table/count | 7 | 7 | Quiz #1–#7 supported by cited evidence. |
| 472 | Layout | 16 | 16 | Cited text explicitly gives max. 16 g. |
| 507 | Text/table lookup | Little Rock | Little Rock | Cited table binds AR01 to Little Rock. |
| 636 | Layout/text count | 2 | Request budget exceeded | Scope rejected twice; research did not resolve the main-body condition before the six-request cap. |
| 660 | Unanswerable | Not answerable | Port 1 / P1.1 T2EX | Incorrect against fixed V2 label; nearby fact passed scope verification after one rejection. |
| 732 | Figure/text count | 5 | 5 | Numeric match with wrong support: Twitter-activity table, not figure counting. |
| 1016 | Table/calculation | 10314 | 10314 | Verified 6692 + 2642 + 980, with the correct FY2021 lease/debt rows. |
| 1084 | Unanswerable | Not answerable | Abstained | Correctly withheld an AMCOR answer scoped to a BESTBUY document. |

## What this shows

The current retrieval found relevant pages in this small set. Losses include
unproductive follow-up research, numeric-validator retries, shared budgets and
semantic acceptance of the wrong question/quantity. It would be premature to
claim the scope guard solved semantic grounding: row 732 is a direct counterexample,
and row 660 remains an answerability failure under the pinned labels.

Although visual reading and operand resolution were enabled, neither `read_pages`
nor `resolve_calculation` was selected in this run. Tool availability alone did
not produce adequate research behavior on the visual/ambiguous questions.

Increasing budgets alone would not fix those false acceptances. The next work
should separately measure numeric rejection causes, recovery/tool use and
claim/question quantity binding without adding fixture-specific prompt rules.
This run did not change the implementation in response to the measured failures.

There is no paired old/new run here and no claim of improvement over historical
120-question reports. The automatic scorer is lenient contains-match/numeric
matching within 1%, not official benchmark scoring. Manual grading is review of
the released answer and its cited text, not a separate model judge.

## Reproduction and artifacts

```sh
GENERATION_PROVIDER=openai OPENAI_MODEL=gpt-6-luna AGENTIC_RAG_ENABLED=true AGENTIC_SCOPE_VALIDATION_ENABLED=true SUPPORT_IDS_ENABLED=true DERIVED_ANSWERS_ENABLED=true OPERAND_RESOLVER_ENABLED=true VISUAL_ANSWERS_ENABLED=true RERANKER_CANDIDATE_K=40 RERANKER_TOP_N=14 .venv/bin/python scripts/benchmarks/run_mmlongbench_pilot.py --manifest artifacts/mmlongbench-v2/manifest.json --labels data/benchmarks/mmlongbench-doc-v2/samples.json --skip-ingest --rows 507,366,1016,381,472,210,732,636,660,1084 --out artifacts/mmlongbench-v2/NEW-OUTPUT-DIRECTORY
```

Use a fresh output directory. The historical command above contains no credential;
the existing local environment supplies the API key. The real `.env` was unchanged.

- `selection.json`: pinned rows, metadata and selection rule.
- `grading-contract.json`: corrected gold labels, locked for scoring.
- `run-settings.json`: flags/budgets, code revision and manifest/label hashes.
- `corpus-inventory.json`: indexed document versions/page coverage and PDF hashes.
- `report.json` / `report.md`: unmodified automatic benchmark reports.
- `manual-review.json`: released answers, cited passages, observed tool/failure
  events and separate manual verdicts; retained for audit.
- `results.jsonl`: local raw checkpoints/results, excluded from git by repository
  policy. No previous results were resumed or overwritten.
