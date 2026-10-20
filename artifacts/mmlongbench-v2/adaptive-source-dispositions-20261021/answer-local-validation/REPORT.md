# Answer-local validation without another model loop

21 October 2026. Current follow-up to the [lifecycle audit](../AUDIT.md) and the
[unsuccessful terminal-finalizer measurement](../terminal-finalization/REPORT.md).

## Scope

The goal is to withhold invented or wrongly bound values while preserving supported
answers. Questions with missing source information must not be answered with a
nearby value from another entity, period, category or unit. An incomplete search
does not prove that the whole document lacks an answer.

The unsuccessful finalizer source-proposal extension has been removed. An
abstaining reader no longer triggers another finalizer call. No additional judge,
terminal assessor, research loop or benchmark-specific rule has been introduced.
Typed terminal receipts remain application-owned observability data and do not
cause model calls.

## Focused correction

Previously, `AdaptiveSession.verify` rejected any answer citing only sources of an
unresolved quantity record, before independently checking a newly supplied
calculation. In the preceding 380 run, this blocked the correct canonical formula
even though it could have undergone the normal validation path.

A proposed calculation can now proceed past that coarse veto **only when
independent semantic scope validation is enabled**. It still must pass:

1. Source authorization and visibility.
2. Existing bounded original-page quality checks and image requirements.
3. Application checks of cited operands and deterministic arithmetic.
4. Existing independent semantic validation of the question and source binding.
5. The existing final-release checks.

This does not approve the failed extraction, promote its draft operands, authorize
an unexplained numeric guess, or disable period/entity/unit checks. The prior
record remains unchanged. There is no extra model request beyond the normal scope
check that a supported answer already requires.

Clarification export remains fixed: the trace harness records explicit terminal
kind and clarification separately from streamed answer tokens. The captured 830
clarification passes the export helper offline without another paid call.

## Verification

**2,381 tests passed**, four skipped and five deselected. Ruff passes; mypy passes
163 application files. New regressions show that the same failed collection:

- Allows a correctly sourced and computed new formula through one normal scope check.
- Does not allow a wrong result or an unsourced operand.
- Does not allow a formula bound to the wrong question entities.
- Does not cause reader abstention to open another finalizer/reviewer loop.

Existing naked-guess rejection, source scope, premise, quantity and clarification
tests remain included. A broader semantic bypass for negative prose was not
retained: existing positive-answer validation remains authoritative.

## Live measurement

Frozen sequential rows: **380, 387, 508**. The arithmetic control, easy prose
control and missing-field case use the same gpt-6-luna profile, fast path, evidence
needs and global budgets. All application Python plus the harness are hashed
before and after each run. All three subprocesses completed with unchanged hashes
for all 164 frozen files.

| Row | Released result | Run seconds | SDK requests | Assessment |
| --- | --- | --- | --- | --- |
| 380 | **8,367,277,000 rupees** | 51.86 | 6 | Correct arithmetic control retained. This run succeeds through checked collection/application proof; it does not establish live causality through the changed failed-collection branch. |
| 387 | **Rick Scott** | 29.31 | 3 | Correct easy prose answer retained; no extra terminal assessment loop. |
| 508 | Insufficient evidence | 51.10 | 7 | No geographic market or nearby code is invented. The released response remains generic; no independently verified source-disposition receipt is produced. |

These are three reruns of existing questions. Totals remain **120 distinct
questions: 79 supported, two qualified, four verified refusals, 35 unresolved**.
508's safe generic response is not promoted to a verified closed-object refusal.
The controls show retained correctness in these runs, not a guarantee for the
entire question set or recovery of all source-negative cases.

## Remaining work

This correction does not close the source-disposition lifecycle gap. Existing
period/requirement checks can still reject a useful negative explanation submitted
as an ordinary positive answer. Strong source findings need their existing
independent grounding; incomplete research must remain insufficiency. The latest
1017 missing-input acquisition and whole-document closure also remain open.

Raw JSON, captures, spans and source hashes remain local and ignored. Dollar
pricing is not configured, so API dollar cost is unknown.
