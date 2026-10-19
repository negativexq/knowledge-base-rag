# Extended research tools: fixed MMLongBench mini10

This is a **regression measurement**, not an accuracy-improvement claim. The
extended tools work in offline integration tests, but exposing them and adding
budget reserves did not improve this development-visible sample.

Same ten rows, corrected labels, indexed corpus, model (`gpt-6-luna`), retrieval
settings and configured total budgets as `../agentic-mini10-20261018`. No
re-ingestion, prompt tuning to individual questions, budget increase or question
rerun was performed. The executed implementation is pinned at `a403758` in
`run-settings.json`; subsequent PDF concurrency locking and comparison source-type
metadata fixes were tested offline, not remeasured against this sample.

| Measurement | Previous run | Extended tools |
| --- | ---: | ---: |
| Automatic answerable correct | 5/8 | 3/8 |
| Manually correct **and grounded** answerables | 4/8 | 2/8 |
| Unanswerables receiving no factual answer | 1/2 | 2/2 |
| Of those, model refusals | 1 | 1 |
| Of those, budget errors | 0 | 1 |
| All budget-blocked questions | 2 | 6 |
| Actual model requests | 33 | 35 |
| Input tokens | 335825 | 379472 |
| Output tokens | 2159 | 2284 |
| Summed question latency | 239.9 s | 212.5 s |

The automatic scorer counts the budget-blocked unanswerable as a correct refusal,
so its combined result is 5/10. Manually grounding the released answers reduces
that to 4/10 **if budget withholding is credited**. Requiring an evidence-based
model refusal instead of a runtime failure gives 3/10. These definitions are
reported separately; a budget error is not evidence that the model established
unanswerability. The previous combined grounded/withholding result was 5/10.
This is one run per condition on a small known sample, not a statistical study or
a benchmark-wide comparison. The automatic scorer is lenient numeric/contains
matching, not official benchmark scoring.

## What actually happened

- Rows 381 (seven quizzes) and 472 (16 g coffee) were correct with appropriate
  cited text. Row 1084 correctly abstained.
- Row 507, previously answered correctly as Little Rock, used document discovery
  with zero matches, then hit token preflight before another research turn.
- Row 1016 completed `calculate`, but scope validation returned
  `SCOPE_CHECK_INVALID` twice. Another research turn would consume the reserved
  verification request, so the application withheld the answer. This regressed
  from the previous correct, supported 10314 result; validators were not weakened.
- Row 636's hybrid search **admitted 14 new evidence blocks**, showing that
  pre-retrieval seen-point exclusion can reach new evidence. That did not resolve
  question scope; token preflight blocked recovery.
- Rows 210 and 366 also stopped at token preflight. Row 366 reached a scope
  rejection (`SCOPE_PERIOD_MISMATCH`) before exhausting recovery budget.
- Unanswerable row 660 was withheld after scope rejection and failed recovery;
  this avoided the previous wrong factual answer but ended in a budget error.
- Row 732 again returned the expected number 5 using E1.S117, which describes
  first-24-hour Twitter activity, not the number of Airbus figures. The verifier
  falsely accepted the quantity binding. This answer is **not grounded correct**.

There were 35 actual model requests, including eight cached-receipt-producing
scope checks. Tool observation counters saw 17 execution attempts. Recorded
completed research-tool events were six `find_documents`, two `search`, and one
`calculate`. The six discovery calls all returned zero document anchors.
Attempts that fail before recording a completed tool event are not counted as
successful executions. No completed `inspect_table`, `list_document_elements`,
`inspect_region`, `compare_evidence`, `read_pages`, `resolve_calculation`, section
reading or navigation was recorded. Availability alone did not cause appropriate
use of structural/visual tools.

## Implications

The tools provide the intended capabilities, but this combined change is not
ready to be called a quality improvement. The next evaluation should isolate
routing/tool selection, context/history growth and reserve policy from the
semantic verifier's false acceptances and invalid outputs. Increasing budgets
alone does not repair the Airbus grounding error. A generic document-discovery
route also needs to avoid consuming turns on questions whose target document is
already fixed. Do not add sample-specific aliases, entity rules or answer hints.

The application retains the existing opt-in agentic rollout. No `.env` edit,
production deployment, push or external write occurred.

## Reproduction and scope

```sh
GENERATION_PROVIDER=openai OPENAI_MODEL=gpt-6-luna AGENTIC_RAG_ENABLED=true AGENTIC_SCOPE_VALIDATION_ENABLED=true SUPPORT_IDS_ENABLED=true DERIVED_ANSWERS_ENABLED=true OPERAND_RESOLVER_ENABLED=true VISUAL_ANSWERS_ENABLED=true RERANKER_CANDIDATE_K=40 RERANKER_TOP_N=14 .venv/bin/python scripts/benchmarks/run_mmlongbench_pilot.py --manifest artifacts/mmlongbench-v2/manifest.json --labels data/benchmarks/mmlongbench-doc-v2/samples.json --skip-ingest --rows 507,366,1016,381,472,210,732,636,660,1084 --out artifacts/mmlongbench-v2/FRESH-OUTPUT-DIRECTORY
```

Use the pinned revision and a fresh directory for reproduction. The key comes
from the existing local configuration and is never included in artifacts.
Provider-reported generation token totals are used because the existing forensic
sanitizer redacts token-named fields; redaction is not interpreted as zero usage.
Model prices were not configured, so no dollar-cost estimate is claimed.

The runner shares the production scoped-retrieval wrapper and agent/validators,
but it is a direct production-core harness, not an HTTP chat request. Tenant and
question-document filters were active; cross-tenant probes found zero leaks.
HTTP auth, user/group grant administration and real concurrent production load
were not tested by this live run. Those boundaries have separate offline tests.

`report.json`/`report.md` are unmodified automatic outputs. `manual-review.json`
retains released answers, exact cited text, failures, tool events and the separate
manual verdicts. `selection.json`, `grading-contract.json`, `corpus-inventory.json`
and `run-settings.json` pin the sample, labels, corpus and settings. Raw
`results.jsonl` remains local and git-ignored under the existing repository policy.
