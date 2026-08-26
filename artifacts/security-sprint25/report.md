# Sprint 25 security evaluation report

Run date: 2026-08-26

The adversarial suite was run against the local Ollama-backed generation path
with `answer_v3` and `strict` validation. The evaluator records deterministic
policy/citation outcomes and does not claim that one model run proves security.

## Adversarial suite

- 82 cases, complete run: 12 direct injection, 20 indirect document injection,
  10 fake system/developer text, 10 citation spoofing, 5 citation suppression,
  10 exfiltration, and 15 benign controls.
- Languages: 60 EN and 22 TR cases, including mixed-language document/query
  combinations, obfuscation, fake citations, and tool-like text.
- `injection_success_rate`: 0.0
- `citation_spoof_success_rate`: 0.0
- `citation_suppression_success_rate`: 0.0
- `unauthorized_citation_rate`: 0.0
- `cross_tenant_exfiltration_rate`: 0.0
- `benign_answer_success_rate`: 1.0
- Category and language forbidden-behavior rates: 0.0 throughout.
- Two outputs were held by the strict output-policy gate; no raw answer is
  stored in the artifact.

The machine-readable result is `adversarial-results.json`. The rates are
deterministic oracle results for this run, not a universal security guarantee.

## Benign regression

The 15-case representative benign subset was run through prompt v2 and v3.
Both versions produced citation-integrity `1.0` and not-found behavior `1`;
the measured deltas are zero. Answer relevancy is explicitly **Not measured**:
the optional local LLM judge did not complete reliably, so no judge score was
invented. See `benign-regression.json`.

## Context cost

The repository's whitespace-token estimate measured 818 old-format tokens and
2079 structured-envelope tokens (+154.16%). This is an estimate, not a model
tokenizer benchmark; the envelope therefore remains a known context-budget
tradeoff for future optimization.

## Interpretation

Sprint 25 demonstrates prompt-injection resistance against the documented
local adversarial suite while preserving Sprint 23 retrieval authorization.
The production/default server mode is now `strict`: answer buffer, validate,
then release. `fast` remains an explicit server-side development opt-in and
uses stream-then-post-check semantics; it is not equivalent security.
Citation integrity is not claim-level semantic grounding; the latter remains
out of scope. Fast mode preserves immediate streaming and performs a terminal
post-check. Strict mode buffers output and releases it only after the
deterministic policy/citation gate passes.
