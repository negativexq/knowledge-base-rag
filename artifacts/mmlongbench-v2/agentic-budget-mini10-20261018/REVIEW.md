# Initial soft-budget policy audit: fixed mini10

**This run did not demonstrate a quality, cost or latency improvement.** It
measured revision `122c0ca`, the first soft-stop policy, before the dedicated final
candidate repair slot added in `a4eb6df`. Do not present these results as a final
revision benchmark.

The same fixed ten rows, corrected labels, PDFs, indexed corpus, `gpt-6-luna`,
retrieval parameters and hard shared totals were used. No re-ingestion or
question rerun occurred in this directory. Soft policy: three research requests,
four execution attempts, two consecutive no-progress steps, one candidate repair,
20-second tool and 30-second model deadlines. Discovery was hidden for requests
fixed to one source. This is a combined development-policy experiment, not an
ablation isolating individual controls.

| Metric | Extended tools | First soft policy |
| --- | ---: | ---: |
| Automatic answerable correct | 3/8 | 2/8 |
| Manually correct and grounded answerables | 2/8 | 2/8 |
| Correct model refusals on unanswerables | 1/2 | 1/2 |
| Budget-blocked unanswerables | 1/2 | 0/2 |
| Budget-blocked total | 6 | 5 |
| Actual model calls | 35 | 34 |
| Input tokens | 379472 | 387769 |
| Output tokens | 2284 | 2307 |
| Summed question latency | 212.5 s | 305.4 s |

Question latency includes initial retrieval and local work outside the agent's
own deadline; this one-run comparison is not a controlled latency benchmark.
Automatic grading credits a numeric match regardless of grounding and can credit
a runtime withholding as a refusal. Both differences matter: the earlier Airbus
5 was ungrounded, and earlier row 660 was withheld due to a runtime budget error.
The first older agentic mini10 had **4/8 grounded correct**; this run did not
recover that quality. Neither equal grounded accuracy nor one fewer model call
justifies a rollout or efficiency claim.

## Observed control behavior

- Every question stayed within three research requests; maximum admitted tool
  execution attempts per question was two, within the configured cap of four.
- A repeated operation on row 381 was blocked (`REPEATED_TOOL_CALL`). However, its
  first final candidate then failed scope validation and the research request cap
  prevented a correction. Row 636 also reached scope rejection after the last
  research turn. This exposed a phase-allocation bug: the nominal candidate repair
  allowance was not separately available after the research cap.
- `a4eb6df` fixes that by allowing at most one **tools-closed** final candidate
  correction, still inside the unchanged six total model slots and 60,000-token
  quota. It does not permit more searches. This follow-up has deterministic tests
  and a separate targeted three-question smoke, not a full new mini10.
- Rows 472 and 507 answered 16 g and Little Rock with appropriate cited text.
- Row 1084 correctly abstained. Row 660 again released the nearby Port 1/P1.1/T2EX
  fact despite its pinned unanswerable label: semantic scope false acceptance
  remains a separate problem, not something an iteration cap fixes.
- Row 732 abstained, avoiding the earlier wrong Twitter-based figure count but
  still missing an answerable question.
- Rows 210 and 366 had numeric/period/calculation validation failures; row 1016
  returned two `SCOPE_CHECK_INVALID` judgments and exhausted its repair allowance.

There were 14 observed execution attempts but seven recorded completed research
tool events: three searches, two calculations, two section reads. Failed/blocked
attempts and successful completions are distinct. No document discovery completed
under the single-document scope. One search on row 636 added 14 new blocks; one
on row 1084 added five blocks and explicitly excluded nine for evidence budget.
No completed structural/visual tool reading was recorded.

## Scope and limitations

The sample is small, known during development and not a held-out calibration set.
No threshold is established as optimal. Budget control is operationally bounded;
it is not proven to improve answer accuracy or minimize cost. USD prices were not
configured, so actual token usage is reported without a dollar estimate. Existing
forensic token-key redaction is not interpreted as zero usage.

This direct production-core harness applies tenant and question-document scope,
not HTTP auth or user/group grant administration. Cross-tenant probes found zero
leaks; separate offline security tests cover those other boundaries. `.env` was
unchanged, and no push or deployment occurred.

Raw `results.jsonl` is local and ignored by git. Automatic reports remain
unmodified. `manual-review.json` preserves exact released answers/cited text,
control counters, stop/terminal reasons and separate manual verdicts. The pinned
sample, labels, settings and corpus inventory are retained alongside it. The
[implementation audit](../../../docs/agentic-budget-audit.md) links the primary
references and describes the final control contracts. The later
[targeted repair smoke](../agentic-budget-repair3-20261018/REVIEW.md) is deliberately
reported separately.
