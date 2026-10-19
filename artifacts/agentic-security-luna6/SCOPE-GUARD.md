# Scope guard follow-up — 2026-10-18

The answer agent's prompt and existing deterministic validators were retained.
A reusable stateless scope verifier was added, with exact-witness validation,
server-owned release receipts and repair feedback. No product names, fixture
answers or benchmark-specific scope vocabulary were added to the answer prompt.

## Reproduction of the observed ambiguity

The prior pilot used `The service uses TLS.` while asking about the backup
service; retrieval could supply `The backup service uses SSH.` All four relevant
pilot runs answered TLS without searching and passed release validation.

The same two scenarios, with the same question/evidence, were repeated twice
with the new scope guard: **4/4 returned the correct cited SSH answer**.
Each run first received `SCOPE_NOT_ESTABLISHED`, then searched and passed a new
scope check using the newly cited evidence. Both ordinary and poisoned follow-up
search results were exercised. Each repair used five model calls (three answer
agent calls and two verifier calls), within the production request budget of six.
The old smoke harness used a cap of four; the harness now uses six to include the
new verifier/repair work. No failed answer was concealed by editing the fixture.

Local raw outputs: `scope-guard-ambiguous-20261018/results.json` and
`scope-guard-ambiguous-20261018/spans.json` (ignored by Git).
The small [usage summary](scope-guard-ambiguous-20261018/summary.json) remains versioned.

## Regression and additional scope probes

A separate 17-case live run passed **17/17** security/answer checks, without
infrastructure failures or unexercised follow-up scenarios. It includes the prior
12 explicit-scope controls and five probes: version, environment, period,
established alias and Turkish evidence for an English question. All 14 answerable
cases produced the expected answer; the three unsupported/unauthorized questions
abstained. The scope checks did not reject those final supported candidates.
No attack/canary marker was released or sent in a search query.

Local raw outputs: `scope-guard-regression-20261018/results.json` and
`scope-guard-regression-20261018/spans.json` (ignored by Git).
The small [usage summary](scope-guard-regression-20261018/summary.json) remains versioned.

Combined follow-up usage: **21 runs, 62 actual model calls, 51848 input and 2583
output tokens**. Both exports contain `agent` and `scope_validator` model roles;
actual `llm.request` span counts match the recorded usage. The API credential was
checked absent from saved JSON. Only synthetic content was used.

```sh
.venv/bin/python -m scripts.experiments.run_agentic_security_smoke --ambiguous-base --case benign_search --case tool_result_poison --repeats 2 --output artifacts/agentic-security-luna6/new-ambiguity-run
.venv/bin/python -m scripts.experiments.run_agentic_security_smoke --scope-probes --output artifacts/agentic-security-luna6/new-probe-run
```

These are explicit live commands; they refuse to overwrite an output directory.
The provider is `gpt-6-luna`, reasoning none, temperature zero, store false and
SDK automatic retries disabled. The original pilot/output fixtures remain in
the preceding report and their own directories.

## Limits and local regression coverage

This is a small synthetic, development-visible test set. The four-case repair is
a regression check after observing a failure, not a blind evaluation or a
randomized benchmark. The grader checks expected answer substrings and attack
markers, plus application validation/authorization results. Released answers,
queries and scope rejection telemetry were reviewed. There is no independent
semantic evaluation judge, and the checker uses the same model family as the
answerer; correlated semantic errors remain possible. No TechQA/MMLongBench
performance or universal prompt-injection resistance is claimed.

Retrieval is injected, so the live runs do not validate production Qdrant,
connector-native ACL sync, HTTP authentication or visual inference. Document
permissions were separately exercised with authenticated API tests, persistent
SQLite, real in-memory Qdrant filters, ledger admission/revocation, metadata
isolation, role/group boundaries, stale writes, and in-flight answer withholding.
The scope contract tests cover incomplete/fabricated witnesses, replay against
changed questions/claims/evidence/provenance, shared budgets, timeout, bounded
verifier payloads and the final release gate.

Validation: **1856 backend tests passed**, 4 skipped, 5 live-service tests
excluded from normal pytest. Mypy checked 137 modules; Ruff passed. Frontend:
**111 tests passed**, ESLint, TypeScript and production build passed. The live
commands above are never invoked by the default unit test suite. Browser visual
QA remains a manual deployment check.

Application-managed user/group grants are now implemented with default deny and
an ADMIN editor in Knowledge. Existing documents require explicit grants.
Connector-native permissions and IdP memberships are not synchronized
automatically; see [deployment instructions](../../docs/document-permissions.md).
