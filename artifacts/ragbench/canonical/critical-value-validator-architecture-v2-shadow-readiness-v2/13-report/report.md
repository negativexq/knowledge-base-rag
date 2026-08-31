# Critical Value Validator Architecture V2 — Shadow Readiness V2

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_SHADOW_READINESS_V2_PASSED`

Runtime status: `LOCAL_SHADOW_RUNTIME_VERIFIED`.

The six frozen primary cases were run through the real local frontend, API,
retrieval/evidence, generation, support-ID path, baseline validator,
Architecture V2 shadow, citation resolution, and UI. All six were
validator-capable. Baseline was authoritative in 6/6 cases; Architecture V2
shadow executed in 6/6 cases, giving 100% coverage. No unresolved
`ARCHV2_UNSAFE_SUSPECT` disagreement occurred.

## Frozen history

Architecture V2 ID:
`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1`.

Semantic/source digest:
`09d94bb7c9d1769bd79e18c0beaa75c653477d3127605fdbcaddc5e9cf7ed33b`.

Raw freeze-manifest SHA256:
`c797556bff29669cdafdb165646b601e94ce4a1573969dd69b9e452f2d080d23`.

Shadow Readiness V1 remains `FAILED` for telemetry coverage and browser E2E.
Remediation V1 remains `PASSED`. Neither historical result was rewritten.

## Runtime

Environment was LOCAL. Frontend was `127.0.0.1:5174`, API
`127.0.0.1:8001`, Qdrant `127.0.0.1:6333`, Jaeger `127.0.0.1:16686`, and
Chrome was controlled directly through CDP at `127.0.0.1:9222`.

Effective configuration was:

```text
CRITICAL_VALIDATOR_VERSION=baseline
CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=true
CRITICAL_VALIDATOR_V3_SHADOW_ENABLED=false
RAG_PIPELINE_V2=true
SUPPORT_IDS_ENABLED=true
RAG_FORENSIC_CAPTURE_ENABLED=false
RAG_FORENSIC_CAPTURE_RAW_TEXT=false
```

Provider was Ollama, model `qwen3.5:4b`. No second generation was performed
for the shadow; both validator paths used the same generated request state and
authorized evidence boundary.

## Primary matrix

| Case | Class | HTTP/UI | Baseline | V2 shadow | Disagreement | Occurrences (V/S/A) |
|---|---|---|---|---|---|---|
| UI-01 | straightforward grounded fact | 200 / rendered | PASS | PASS | SAME | 1 / 1 / 0 |
| UI-02 | corrective wrong premise | 200 / rendered | PASS | PASS | SAME | 1 / 1 / 0 |
| UI-03 | multi-occurrence sibling | 200 / rendered | MIXED | MIXED | SAME | 2 / 0 / 0 |
| UI-04 | signed/identifier value | 200 / rendered | MIXED | MIXED | SAME | 1 / 1 / 0 |
| UI-05 | ambiguous/conservative | 200 / rendered | INDETERMINATE | INDETERMINATE | SAME | 1 / 1 / 0 |
| UI-06 | insufficient evidence | 200 / rendered | PASS | PASS | SAME | 1 / 1 / 0 |

The tuple in the final column is `occurrence_count / validate_count /
ambiguous_count`; all six cases had zero skipped rejected-premise occurrences
in the observed runtime traces. Full trace records, including skip counts and
trace IDs, are in the aggregate summary artifact.

All six UI runs had completed SSE/UI state, zero fatal console errors, zero
resource failures, and one observed `POST /chat` HTTP 200. Citation mutation,
support-ID mutation, visible mutation, and forced-abstain mutation were all
zero. No citation signal was present in the bounded browser smoke summary;
this is not a semantic citation-quality score.

## Jaeger and privacy

Required aggregate metadata coverage was 100% for all six shadow executions:
architecture ID, executed flag, normalized outcome, disagreement, duration,
error flag, occurrence count, and all role counters. `executed=false` remains
distinct from `executed=true` with zero occurrences, and observed role counts
obey the runtime accounting contract.

The actual Jaeger payload contained zero raw query, answer, evidence, source,
critical literal, occurrence text, secret, occurrence-ID, span-coordinate, or
other forbidden high-cardinality leaks. Only bounded enums, booleans, counts,
and durations were observed.

## Forensic and failure contracts

Focused tests verified metadata-only forensic capture, controlled raw local
forensic capture, shadow exception isolation, and Architecture V2 authoritative
infrastructure failure as fail-closed. Forensic ledger/role/filter/V3 details
remain local-only and are not promoted to OTel. Clean forensic defaults remain
disabled.

The primary matrix had no shadow errors. The injected shadow-error test left
the baseline response, support IDs, citations, forced-abstain decision, and
visible result unchanged. The authoritative exception test produced the
existing infrastructure-failure/abstention behavior and did not fail open.

## Performance and stack

Actual six-request shadow durations were 0.765, 2.506, 2.676, 2.983, 4.003,
and 8.720 ms: local p50 approximately 2.676 ms, p95 approximately 7.541 ms,
maximum 8.720 ms. This is a small local observation, not a production
benchmark, and is not a material blocker. Browser request latency was not used
to attribute cost to the sub-millisecond validator path.

Qdrant, Jaeger, API, frontend, and CDP health checks passed. Three transient
`/health/ready` HTTP 500 polls were caused by an environment-dependent Qdrant
alias inspection timeout; subsequent readiness polls were HTTP 200, all six
`/chat` requests were HTTP 200, and no task-caused critical stack failure was
observed.

## Gates

SR1–SR21 all pass. SR17 is recorded as
`PASS_ENVIRONMENTAL_HEALTH_POLL_ONLY` because of the documented transient
readiness health-poll condition; it was not a task-caused browser/API/shadow
failure.

No semantic source, runtime configuration, telemetry schema, or CDP tooling
was modified in this verification task. No API, SSE, support-ID, citation,
database, Qdrant, index, or embedding contract changed.

## Final runtime state

Production shadow remains disabled. Architecture V2 remains non-authoritative.
Canary and primary promotion remain disabled. The result authorizes no
automatic production activation; it closes local shadow-readiness verification
only.
