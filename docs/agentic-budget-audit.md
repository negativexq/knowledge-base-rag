# Agent research budget audit

The issue was not missing global limits. Before this change, the agent already
had six shared model-response slots, eight successful SDK tool calls, 60,000
reported tokens, a 120-second run timeout and token/request reserves for final
scope verification. Those limits terminate a run but do not reliably stop
unproductive research early enough to finalize an answer.

## Evidence and findings

The extended-tools mini10 recorded 35 real model requests, 379,472 input tokens,
17 observed tool attempts, nine completed-tool records and six budget-blocked
questions. Six document-discovery completions all found zero anchors even though
the benchmark had already fixed the target document. Grounded answerable accuracy
fell from 4/8 to 2/8. See the
[unaltered run and manual audit](../artifacts/mmlongbench-v2/agentic-tools-mini10-20261018/REVIEW.md).

1. **High: no progress-based stop.** Empty searches, unchanged evidence and
   repeated actions could continue until a hard limit prevented final generation.
2. **High: successful-call counts are not execution-attempt counts.** The SDK's
   `RunUsage.tool_calls` counts successful tool calls, so application control must
   also account for failures and retries. Observed attempts and completed events
   must not be reported as interchangeable metrics.
3. **High: tools were exposed when irrelevant to request scope.** Document
   discovery cannot broaden a request fixed to one already known source; exposing
   it added selection/schema overhead and opportunities for unproductive calls.
4. **High: missing per-operation deadlines.** A total run timeout does not prevent
   a single tool or model request from occupying the remaining time.
5. **Medium: research and verification retries compete for the same budget.**
   Keeping scope verification mandatory is correct; endlessly repairing an
   invalid/rejected candidate is not. A repair allowance must be explicit.
6. **Medium: history/context growth.** Initial evidence, tool outputs and schemas
   contribute repeatedly to input cost. Request counts alone do not measure that
   cost. Arbitrary truncation/LLM summaries can lose qualifiers and provenance;
   this change does not introduce either.
7. **Existing protection confirmed:** native SDK and OpenAI tool clients have
   transport retries disabled (`max_retries=0`), and OpenAI research/tool calls use
   reasoning effort `none`. The observed problem was repeated orchestration,
   not evidence of an unbounded hidden-reasoning setting.

## Practice and primary references

The general pattern is bounded execution, explicit stop conditions, useful tools,
minimal relevant context and evaluation of both success and cost. Anthropic
recommends explicit iteration stopping conditions and progress grounded in tool
results in [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents).
Its [tool design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents)
explains how redundant/overlapping tools distract agents, and recommends measuring
runtime, tool calls, token use and errors alongside task success.

PydanticAI provides shared [UsageLimits](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/)
and [operation/run timeouts](https://pydantic.dev/docs/ai/core-concepts/timeouts/).
The SDK counts successful tool calls and checks provider-reported token usage
after responses. Exact request token counting may add provider overhead; our local
preflight remains an estimate. PydanticAI also supports
[history processors](https://pydantic.dev/docs/ai/capabilities/process-history/),
but that capability alone does not make evidence truncation safe.

None of these sources prescribe **3 turns / 4 attempts / 2 empty steps**. Those
are configurable starting thresholds for this application, not universal best
practice. A small known benchmark cannot establish optimal thresholds.

## Implemented policy

`ResearchPolicy` is server-owned, validated and configurable with the JSON setting
`AGENTIC_RESEARCH_POLICY`. Clients and document text cannot override it. The
existing hard total SDK limits remain in place.

| Control | Default | Behavior |
| --- | ---: | --- |
| Research model responses | 3 | Includes the final research response; scope and nested model calls still share the hard total of six. |
| Tool execution attempts | 4 | Includes failed execution attempts; checked inside each tool batch, not just before exposing tools. |
| Consecutive no-progress steps | 2 | Close tools and ask for final output from existing evidence. |
| Repeated identical action at unchanged evidence revision | 1 | Block the repeated execution and close research. |
| Candidate repair allowance | 1 | A second recorded deterministic/scope rejection stops the run; no unvalidated draft is released. |
| Tool deadline | 20 s | Close research on timeout; allow a final response if the outer budget permits. |
| Model request deadline | 30 s | Stop and withhold on timeout, including verifier calls. |
| Finalization time reserve | 30 s | Stop starting tools near the run deadline; reserve is clamped to at most one third of a custom run timeout. |

No-progress is a deterministic signal, not another LLM judge. A new ledger block,
successful verified visual reading/resolution, arithmetic result or useful
inspection counts as progress. Empty/no-new-evidence search/navigation and failed
operations do not. A changed ledger revision permits the same search query again,
because seen-point exclusion can now produce new evidence. Equivalent paraphrased
queries are not claimed to be detected; total attempts and no-progress caps bound
them instead.

Once research closes, future tool definitions are hidden and a generic server
instruction directs a final structured answer, clarification or abstention from
current evidence. Calls already emitted in a batch are checked again before
execution. No new planning model or summarization call is added. An empty result,
timeout or budget signal never establishes a factual absence.

Soft closure does not bypass deterministic validation, scope receipts or the final
release gate. One research turn is explicitly kept for finalization; one shared
request slot and the existing token reserve remain for scope validation. If those
resources are insufficient, the system still fails closed. The final answer and
verifier are not guaranteed to fit merely because research closed early.

## Observability and remaining limits

Forensic budget metadata records policy, research requests, admitted tool attempts,
blocked calls, consecutive no-progress steps and validation rejections. Content-free
trace attributes show `research.stop_reason` and `research.terminal_reason`
separately: a soft research stop can precede a valid answer; a terminal reason
explains withholding. Counters are safe-allowlisted. Tool argument signatures are
hashed in request-local memory only; raw arguments are not added to traces.

The 120-second deadline applies to the **agent run**, not the entire HTTP request:
initial retrieval, embedding and query rewriting happen before it. Their own
existing deadlines/accounting remain separate. Local token preflight and
provider-reported usage do not constitute a guaranteed dollar spending ceiling.
No USD cap is claimed without configured prices and reliable usage data.
Cancellation stops awaiting synchronous worker work but cannot forcibly terminate
a running Python thread/native PDF operation; the existing bounded PDF scans and
shared process lock remain necessary. No automatic raw-evidence compaction or
unverified cached-answer fallback was introduced.

## Validation

Offline agent-loop tests cover repeated unsuccessful search, two distinct empty
results, progress resetting the counter, an oversized tool batch, recoverable tool
timeout, terminal model timeout, validated server configuration, mandatory scope
verification after soft closure and the one-repair rejection bound. Existing
security/receipt/release tests must continue passing. A live fixed-sample follow-up
is recorded separately; no quality or cost improvement is asserted from passing
unit tests alone.
