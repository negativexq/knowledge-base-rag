# Agentic RAG security review

Scope: the opt-in PydanticAI request path, server-owned retrieval/document scope,
evidence ledger, calculation and visual tools, final release validation,
cancellation, trace export and authenticated trace inspection. This is a local
code review with deterministic regression tests; it is not an external
penetration test, dependency vulnerability scan or live-model injection eval.
No live model API calls were made for this review.

## Findings and implemented fixes

| Boundary | Finding | Change and regression coverage |
| --- | --- | --- |
| Evidence admission | The ledger relied on upstream authorization flags. A malformed or incorrectly scoped retrieval result could be admitted. | The production ledger also checks the server-owned tenant and selected source IDs. Missing/wrong tenants, out-of-scope sources, unauthorized/hidden blocks are excluded. Tests inject incorrect upstream payloads. |
| Local visual source | A filename-derived PDF lookup alone did not prove that rendered bytes were the authorized indexed source/version. Replacement between lookup and rendering was possible. | The tool is available only in the configured filesystem tenant. An admitted filesystem support ID and version are required. SHA-256 must match the indexed version. The renderer pins the verified bytes for reading and confirmation; changed versions fail closed. Tests replace the file after binding and reject another source. File snapshot reads are capped at 64 MiB and individual rasters at 12 million pixels. |
| Trace access | Possession of a trace identifier was insufficient as an access boundary. Detailed tool/usage data makes cross-user access more sensitive. | List/detail endpoints require authentication and ownership; regular users see their own chats, OPERATOR+ their tenant. Legacy chat tags or tenant-owned sync history can establish scope. Cross-user/cross-tenant tests verify no spans are returned. Direct Jaeger links require an explicit flag plus ADMIN. |
| Trace identity | An inherited trace identity can originate from client-controlled HTTP propagation. Reusing it as an ownership index key could merge or overwrite request records. | Each chat starts a fresh server-generated trace. The inbound context is retained as a link. A regression test injects a remote span context and verifies independent identity plus a connected internal request subtree. |
| Sensitive telemetry | Automatic exception events or arbitrary attribute forwarding could expose model content or credentials. | New agent spans disable raw exception recording and store error classes/reason codes. SDK-wide automatic message capture is explicitly disabled for this agent. The browser receives an explicit attribute allowlist, without arbitrary attributes or exception events. Tests inject private text and secret attributes and verify exclusion. |
| Concurrent usage | Shared provider observation state could mix token records across simultaneous callers and weaken nested token-budget accounting. | OpenAI/Ollama observation state is task-local. Concurrent-request tests verify independent records. Unknown prices/usage produce an unknown total, not zero. |

Relevant tests: `tests/test_agentic_security.py`,
`tests/test_agentic_observability.py`, `tests/test_agentic.py`,
`tests/test_agentic_integration.py`, existing document/auth/validator suites, and
frontend trace inspection tests.

## Existing controls retained

- The agent has only registered search, bounded document navigation, restricted
  arithmetic, operand resolution and verified visual reading tools. There are
  no shell, arbitrary network, filesystem-write, connector-write or credential
  tools. Models cannot choose a tenant, ACL, collection or filesystem path.
- Search closures capture the authenticated caller and source scope. Document
  navigation remains anchored to an admitted source/version; Qdrant responses
  are checked again after the mandatory ACL filter.
- Retrieved text, metadata, images and tool outputs remain untrusted reference
  data. Tool output is not promoted to a system instruction. Support IDs are
  server-generated and stable within the request.
- Text/comparison cells must pass support-ID and existing claim validators;
  comparison cells must cite their own source. Unknown citations cause bounded
  retries. The final release path validates again before emitting answer text.
  Visual answers require a returned verified reading ID and retain their
  explicit page-image label.
- Calculations use the existing restricted expression evaluator and evidence
  binding, never Python `eval`. Derived/visual feature flags still remove tools.
- Agent/model/tool/time/token limits and cancellation remain in force. Errors,
  timeout and exhausted retries release an application abstention without a
  partial model draft. Native agent SDK automatic retries are disabled.
- Feedback snapshots are user-submitted reports, isolated from trusted retrieval
  evidence. Clarification replies start a fresh authorized request.

## Remaining boundaries

1. Authorization is the existing **tenant-level** model plus selected source
   scope. This branch does not implement per-document user/group permissions or
   synchronize connector-native ACL changes. Those are required before exposing
   documents with different permissions inside a tenant.
2. Prompt instructions and validators reduce risk but cannot prove resistance
   to all semantic prompt injection, misinformation or poisoned evidence.
   `CONTENT_SCREENING_MODE=shadow` observes findings and does not block them.
   Clarification questions and comparison aspect labels are model-generated UI
   text, not independently proven factual claims. A live adversarial corpus and
   paired quality/security evaluation remain necessary before rollout.
3. Authorized evidence/images are sent to the configured model provider.
   Provider data residency, retention, contractual controls and approved model
   endpoints remain deployment choices. The agent is not a data-loss-prevention
   service and does not discover secrets inside authorized documents.
4. Jaeger, Langfuse, Qdrant, local PDFs and SQLite require service/network access
   controls and disk protection. Hiding a Jaeger link does not secure its port.
   Existing explicitly enabled forensic raw-text captures and feedback reports
   can contain sensitive content and require separate retention controls.
5. Token budgets use reported usage and may be exceeded by the last call before
   accounting. Unknown usage cannot enforce an exact token cap; request/tool/time
   limits still apply. In-flight remote work cannot be undone by cancellation.
   Python thread work already issued for index reads/snapshot creation may
   finish after the awaiting task is cancelled. PDF rendering is in-process;
   the byte/page scan bounds are not a sandbox against malicious PDF resources.
6. The request index has no automatic retention or recovery for abrupt process
   termination. Normal error/timeout/cancellation paths finalize records, but a
   killed process can leave a request marked running. Export/index failure is
   visible as unavailable spans and does not prevent serving an answer.

Keep `AGENTIC_RAG_ENABLED=false` by default until the paired TechQA/MMLongBench
quality evaluation and adversarial authorization/injection checks support rollout.
